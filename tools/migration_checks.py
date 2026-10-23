"""Migration fault probes for disposable databases only, not an operator CLI."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import os
from pathlib import Path
import re
import secrets
import threading
from urllib.parse import urlparse

from app import db, schema_migrations as migrations

TABLES = ('users', 'items', 'item_channels', 'item_photos', 'sales', 'feedback', 'password_resets', 'pilot_requests')


def legacy_sql(backend):
    name = 'v07_postgres.sql' if backend == 'postgres' else 'v07_sqlite.sql'
    return (Path(__file__).resolve().parents[1] / 'tests' / 'fixtures' / name).read_text()


def seed_legacy(connection, backend):
    for statement in migrations.statements(legacy_sql(backend)):
        connection.execute(statement)
    uid = connection.execute('''INSERT INTO users(name,email,password_hash,created_at)
        VALUES ('Synthetic migration owner','migration@example.com','synthetic-noncredential','2020-01-01 00:00:00')
        RETURNING id''').fetchone()[0]
    first = connection.execute('''INSERT INTO items(user_id,sku,title,photo_path,notes,created_at,updated_at)
        VALUES (?,'LEGACY-ONE','Synthetic legacy garment','legacy-cover.webp','Synthetic private note',
        '2020-01-02 00:00:00','2020-01-03 00:00:00') RETURNING id''', (uid,)).fetchone()[0]
    second = connection.execute('''INSERT INTO items(user_id,sku,title,status,quantity,created_at)
        VALUES (?,'LEGACY-SOLD','Synthetic sold garment','sold',0,'2020-01-04 00:00:00') RETURNING id''', (uid,)).fetchone()[0]
    connection.execute('''INSERT INTO item_channels(item_id,channel,status,listing_url,updated_at)
        VALUES (?,'ebay','manually_published','https://www.ebay.com/itm/synthetic','2020-01-05 00:00:00')''', (first,))
    connection.execute("INSERT INTO item_photos(item_id,file_path,position,created_at) VALUES (?,'legacy-gallery.webp',1,'2020-01-06 00:00:00')", (first,))
    connection.execute('''INSERT INTO sales(item_id,user_id,channel,sold_cents,fee_cents,ship_cents,cost_cents,created_at)
        VALUES (?,?,'other',5000,100,200,1000,'2020-01-07 00:00:00')''', (second, uid))
    connection.execute("INSERT INTO feedback(user_id,rating,message,created_at) VALUES (?,4,'Synthetic feedback','2020-01-08 00:00:00')", (uid,))
    connection.execute("INSERT INTO password_resets(user_id,token_hash,expires_at,created_at) VALUES (?,'synthetic-digest',1,0)", (uid,))
    connection.execute("INSERT INTO pilot_requests(email,created_at) VALUES ('synthetic-interest@example.com','2020-01-09 00:00:00')")


def snapshot(connection):
    return {table: [dict(row) for row in connection.execute('SELECT * FROM ' + table + ' ORDER BY id')]
            for table in TABLES}


def assert_preserved(before, after):
    for table in TABLES:
        if table == 'item_photos':
            prior = {row['id']: row for row in after[table]}
            assert all(prior.get(row['id']) == row for row in before[table])
            assert len(after[table]) == len(before[table]) + 1
            covers = [row for row in after[table] if row['file_path'] == 'legacy-cover.webp']
            assert len(covers) == 1 and covers[0]['position'] == 0
        else:
            assert before[table] == after[table], 'Migration changed legacy records: ' + table


def table_names(connection, backend):
    query = ("SELECT table_name AS name FROM information_schema.tables WHERE table_schema=current_schema()"
             if backend == 'postgres' else "SELECT name FROM sqlite_master WHERE type='table'")
    return {row['name'] for row in connection.execute(query)}


def assert_atomic_upgrade(factory, backend):
    with factory() as connection:
        seed_legacy(connection, backend)
        before = snapshot(connection)

    class Failed:
        def __init__(self, connection): self.connection = connection
        def execute(self, query, params=()):
            result = self.connection.execute(query, params)
            if query.startswith('CREATE TABLE IF NOT EXISTS photo_write_intents'):
                raise RuntimeError('synthetic failed upgrade after DDL')
            return result

    with factory() as connection:
        try:
            migrations.migrate(Failed(connection), backend)
        except RuntimeError as error:
            assert str(error) == 'synthetic failed upgrade after DDL'
        else:
            raise AssertionError('Migration failure was not injected')
        assert not {'photo_deletions', 'photo_write_intents', 'schema_migrations'} & table_names(connection, backend)
        assert snapshot(connection) == before

    entered, release = threading.Event(), threading.Event()

    class Held:
        def __init__(self, connection): self.connection = connection
        def execute(self, query, params=()):
            result = self.connection.execute(query, params)
            if query.startswith('CREATE TABLE IF NOT EXISTS photo_deletions'):
                entered.set()
                assert release.wait(10), 'Migration startup gate was not released'
            return result

    def apply(held=False):
        with factory() as connection:
            return migrations.migrate(Held(connection) if held else connection, backend)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(apply, True)
        try:
            assert entered.wait(5)
            second = pool.submit(apply)
            try:
                second.result(timeout=0.5)
                raise AssertionError('Competing migration passed the active startup lock')
            except TimeoutError:
                pass
        finally:
            release.set()
        assert first.result(timeout=10)['applied'] == 3
        assert second.result(timeout=10)['applied'] == 0
    with factory() as connection:
        assert migrations.check_current(connection, backend)['ready']
        assert_preserved(before, snapshot(connection))
        history = migrations.history(connection, backend)
        assert [row['version'] for row in history] == [1, 2, 3]
    return {'atomic_failure': True, 'concurrent_upgrade': True, 'legacy_records_preserved': True}


def run_postgres_checks():
    """Create/drop ONLY a unique generated schema in the disposable CI database."""
    if (not urlparse(os.getenv('FORM_DATABASE_URL', '')).path.endswith('_test')
            or os.getenv('FORM_CLOUD_SMOKE_ALLOW_DELETE') != 'YES_ISOLATED_TEST_ENV'
            or os.getenv('FORM_ENV', 'development') not in ('test', 'development')):
        raise RuntimeError('Refusing migration probes outside an explicitly disposable database')
    name = 'migration_probe_' + secrets.token_hex(8)
    assert re.fullmatch(r'migration_probe_[a-f0-9]{16}', name)
    with db.connect() as connection:
        connection.execute(f'CREATE SCHEMA "{name}"')

    @contextmanager
    def factory():
        with db.connect() as connection:
            connection.execute(f'SET search_path TO "{name}"')
            yield connection

    try:
        result = assert_atomic_upgrade(factory, 'postgres')
    finally:
        with db.connect() as connection:
            connection.execute(f'DROP SCHEMA "{name}" CASCADE')
    print('POSTGRES MIGRATIONS PASSED:', result)
