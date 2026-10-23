import base64
import hashlib
import os
import secrets
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from app import db, schema_migrations as migrations
from tools.migration_checks import assert_atomic_upgrade, seed_legacy, snapshot, table_names, legacy_sql


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(db, 'DB_PATH', tmp_path / 'form.db')
    return tmp_path


def test_original_v07_upgrade_failure_and_competing_startups(database):
    assert_atomic_upgrade(db.connect, 'sqlite')


def test_empty_database_upgrade_failure_rolls_back_all_ddl(database):
    class Failed:
        def __init__(self, connection): self.connection = connection
        def execute(self, query, params=()):
            result = self.connection.execute(query, params)
            if query.startswith('CREATE TABLE IF NOT EXISTS photo_write_intents'):
                raise RuntimeError('synthetic failure')
            return result

    with db.connect() as connection:
        with pytest.raises(RuntimeError, match='synthetic failure'):
            migrations.migrate(Failed(connection), 'sqlite')
        assert not table_names(connection, 'sqlite')
        assert migrations.migrate(connection, 'sqlite')['applied'] == 3


def test_existing_hardening_cleanup_work_survives_ledger_adoption(database):
    with db.connect() as connection:
        seed_legacy(connection, 'sqlite')
        for revision in migrations.REVISIONS[1:]:
            for sql in migrations.statements(revision.sql('sqlite')): connection.execute(sql)
        connection.execute("INSERT INTO photo_deletions(target_key,file_path,created_at) VALUES ('synthetic-target','pending.webp',1)")
        connection.execute('''INSERT INTO photo_write_intents
            (target_key,file_path,operation_id,phase,created_at,next_attempt_at,attempts,last_error)
            VALUES ('synthetic-target','uncertain.webp','synthetic-operation','cleanup',1,2,3,'storage_unavailable')''')
        before = {table: [dict(r) for r in connection.execute('SELECT * FROM ' + table)]
                  for table in ('photo_deletions', 'photo_write_intents')}
        migrations.migrate(connection, 'sqlite')
        assert {table: [dict(r) for r in connection.execute('SELECT * FROM ' + table)] for table in before} == before


def test_changed_revision_file_is_detected_without_restamping(database, monkeypatch, tmp_path):
    db.init_db()
    modified = tmp_path / 'modified-revisions'
    modified.mkdir()
    for name in ('001_legacy.sqlite.sql', '001_legacy.postgres.sql', '002_photo_deletions.sql', '003_photo_writes.sql'):
        (modified / name).write_text((migrations.SQL_DIR / name).read_text() + '\n')
    monkeypatch.setattr(migrations, 'SQL_DIR', modified)
    with db.connect() as connection:
        with pytest.raises(migrations.MigrationError, match='checksum'): migrations.migrate(connection, 'sqlite')


def test_revision_cannot_embed_a_commit_that_escapes_the_batch(database, monkeypatch):
    original = migrations.Revision.sql

    def unsafe(self, backend):
        return original(self, backend) + '\nCOMMIT;\n' if self.version == 2 else original(self, backend)

    monkeypatch.setattr(migrations.Revision, 'sql', unsafe)
    with db.connect() as connection:
        with pytest.raises(migrations.MigrationError, match='Unsupported migration statement'):
            migrations.migrate(connection, 'sqlite')
        assert not table_names(connection, 'sqlite')


def test_inspection_of_legacy_db_does_not_stamp_or_change_it(database):
    with db.connect() as connection:
        seed_legacy(connection, 'sqlite')
        before = snapshot(connection)
    env = {**os.environ, 'FORM_DATA_DIR': str(database), 'FORM_ENV': 'test'}
    result = subprocess.run([sys.executable, '-m', 'tools.migrate'], env=env, capture_output=True, timeout=10)
    assert result.returncode == 1
    with db.connect() as connection:
        assert snapshot(connection) == before
        assert 'schema_migrations' not in table_names(connection, 'sqlite')


@pytest.mark.parametrize('change', ['checksum', 'gap', 'future', 'name'])
def test_history_drift_and_newer_database_fail_closed(database, change):
    db.init_db()
    with db.connect() as connection:
        if change == 'checksum': connection.execute("UPDATE schema_migrations SET checksum='changed' WHERE version=1")
        if change == 'gap': connection.execute('DELETE FROM schema_migrations WHERE version=2')
        if change == 'future': connection.execute("INSERT INTO schema_migrations VALUES (99,'future','unknown',0)")
        if change == 'name': connection.execute("UPDATE schema_migrations SET name='unknown' WHERE version=1")
        before = [dict(row) for row in connection.execute('SELECT * FROM schema_migrations ORDER BY version')]
        with pytest.raises(migrations.MigrationError): migrations.migrate(connection, 'sqlite')
        with pytest.raises(migrations.MigrationError): migrations.check_current(connection, 'sqlite')
        assert [dict(row) for row in connection.execute('SELECT * FROM schema_migrations ORDER BY version')] == before


@pytest.mark.parametrize('change', ['column', 'unique', 'foreign'])
def test_unsupported_legacy_structure_is_not_stamped(database, change):
    sql = legacy_sql('sqlite')
    if change == 'column': sql = sql.replace(' name TEXT NOT NULL,', ' alias TEXT NOT NULL,', 1)
    if change == 'unique': sql = sql.replace('email TEXT NOT NULL UNIQUE', 'email TEXT NOT NULL', 1)
    if change == 'foreign': sql = sql.replace('REFERENCES users(id) ON DELETE CASCADE', '', 1)
    with db.connect() as connection:
        for statement in migrations.statements(sql): connection.execute(statement)
        with pytest.raises(migrations.MigrationError): migrations.migrate(connection, 'sqlite')
        assert 'schema_migrations' not in table_names(connection, 'sqlite')


def test_older_missing_session_column_is_adopted_without_losing_owner(database):
    sql = legacy_sql('sqlite').replace(' session_version INTEGER NOT NULL DEFAULT 0,\n', '')
    with db.connect() as connection:
        for statement in migrations.statements(sql): connection.execute(statement)
        connection.execute("INSERT INTO users(name,email,password_hash) VALUES ('Synthetic','old@example.com','fake')")
        migrations.migrate(connection, 'sqlite')
        owner = connection.execute('SELECT * FROM users').fetchone()
        assert owner['name'] == 'Synthetic' and owner['session_version'] == 0


def test_legacy_orphan_rows_are_not_silently_adopted_or_deleted(database):
    with db.connect() as connection:
        seed_legacy(connection, 'sqlite')
        connection.execute('PRAGMA foreign_keys=OFF')
        connection.execute('UPDATE items SET user_id=999')
        connection.execute('PRAGMA foreign_keys=ON')
        before = snapshot(connection)
        with pytest.raises(migrations.MigrationError, match='Existing data'):
            migrations.migrate(connection, 'sqlite')
        assert 'schema_migrations' not in table_names(connection, 'sqlite')
        assert snapshot(connection) == before


def test_hosted_startup_requires_an_explicit_upgrade(database, monkeypatch):
    with db.connect() as connection: seed_legacy(connection, 'sqlite')
    monkeypatch.setenv('FORM_ENV', 'staging')
    with pytest.raises(migrations.MigrationError, match='upgrade required'): db.init_db()
    with db.connect() as connection:
        assert 'schema_migrations' not in table_names(connection, 'sqlite')
        migrations.migrate(connection, 'sqlite')
    db.init_db()


def test_readiness_does_not_serve_unknown_schema_history(client):
    assert client.get('/readyz').status_code == 200
    with db.connect() as connection: connection.execute("UPDATE schema_migrations SET checksum='invalid' WHERE version=3")
    assert client.get('/readyz').status_code == 503
    assert client.get('/livez').status_code == 200


def test_sqlite_real_process_crash_rolls_back_uncommitted_upgrade(database):
    with db.connect() as connection:
        seed_legacy(connection, 'sqlite')
        before = snapshot(connection)
    script = '''
import os
from app import db, schema_migrations as m
class Crash:
    def __init__(self, c): self.c = c
    def execute(self, q, p=()):
        result = self.c.execute(q,p)
        if q.startswith('CREATE TABLE IF NOT EXISTS photo_write_intents'):
            os._exit(74)
        return result
with db.connect() as c:
    m.migrate(Crash(c),'sqlite')
'''
    env = {**os.environ, 'FORM_DATA_DIR': str(database), 'FORM_ENV': 'test'}
    result = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True, timeout=10)
    assert result.returncode == 74, result.stderr.decode()
    with db.connect() as connection:
        assert snapshot(connection) == before
        assert 'photo_deletions' not in table_names(connection, 'sqlite')
        assert 'schema_migrations' not in table_names(connection, 'sqlite')
        migrations.migrate(connection, 'sqlite')


def test_cli_inspection_does_not_create_a_missing_database(tmp_path):
    missing = tmp_path / 'not-created'
    env = {**os.environ, 'FORM_DATA_DIR': str(missing), 'FORM_ENV': 'test'}
    result = subprocess.run([sys.executable, '-m', 'tools.migrate'], env=env, capture_output=True, timeout=10)
    assert result.returncode == 1
    assert not missing.exists()


def test_cli_explicit_apply_then_readonly_check(database):
    env = {**os.environ, 'FORM_DATA_DIR': str(database), 'FORM_ENV': 'test'}
    applied = subprocess.run([sys.executable, '-m', 'tools.migrate', '--apply'], env=env, capture_output=True, timeout=10)
    assert applied.returncode == 0, applied.stdout.decode()
    inspected = subprocess.run([sys.executable, '-m', 'tools.migrate'], env=env, capture_output=True, timeout=10)
    assert inspected.returncode == 0 and b'"ready": true' in inspected.stdout


def test_sql_parser_keeps_quoted_semicolons_inside_one_statement():
    assert list(migrations.statements("INSERT INTO example VALUES ('a;b'); SELECT 1;")) == [
        "INSERT INTO example VALUES ('a;b');", 'SELECT 1;']
    with pytest.raises(migrations.MigrationError): list(migrations.statements('SELECT 1'))


def test_preupgrade_encrypted_restore_rehearsal_preserves_data_and_photos(database, monkeypatch):
    from app import photo_storage, main
    from tools.photo_write_checks import image
    from tools import ops_backup
    with db.connect() as connection:
        seed_legacy(connection, 'sqlite')
        before = snapshot(connection)
    photo_storage.save_photo('legacy-cover.webp', main.encode_photo(image()))
    photo_storage.save_photo('legacy-gallery.webp', main.encode_photo(image()))
    original = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (database / 'photos').iterdir()}
    monkeypatch.setenv('FORM_BACKUP_KEY', base64.b64encode(secrets.token_bytes(32)).decode())
    backup = database / 'pre-upgrade.formbak'
    assert ops_backup.create_backup(backup)['photo_count'] == 2
    db.init_db()
    with db.connect() as connection:
        connection.execute("UPDATE items SET notes='post-upgrade change' WHERE sku='LEGACY-ONE'")
    restored = database / 'isolated-rollback-rehearsal'
    ops_backup.extract_rehearsal(backup, restored)
    with sqlite3.connect(restored / 'database' / 'form.db') as connection:
        connection.row_factory = sqlite3.Row
        assert snapshot(connection) == before
        assert 'schema_migrations' not in table_names(connection, 'sqlite')
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (restored / 'photos').iterdir()} == original
    # This restores pre-upgrade DATA into an isolated folder. It is not a claim
    # that an old app binary or a real hosted deployment has been rolled back.
