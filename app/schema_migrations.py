"""Small, immutable, transactional SQL migration ledger for both app backends."""
from __future__ import annotations

import hashlib
import inspect
import json
import sqlite3
import time
from dataclasses import dataclass
from contextlib import closing
from functools import lru_cache
from pathlib import Path

SQL_DIR = Path(__file__).with_name('migration_sql')
LEDGER_SQL = '''CREATE TABLE IF NOT EXISTS schema_migrations (
 version INTEGER PRIMARY KEY, name TEXT NOT NULL, checksum TEXT NOT NULL,
 applied_at BIGINT NOT NULL
)'''


class MigrationError(RuntimeError):
    pass


def _ensure_session_version(connection, backend):
    if backend == 'postgres':
        connection.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS session_version INTEGER NOT NULL DEFAULT 0')
    else:
        columns = {r['name'] for r in connection.execute('PRAGMA table_info(users)')}
        if 'session_version' not in columns:
            connection.execute('ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0')


def _backfill_legacy_covers(connection, backend):
    # Retained compatibility repair for v0.1 cover-only rows, including rows
    # inserted by old import workflows after the ledger was first introduced.
    connection.execute('''INSERT INTO item_photos(item_id,file_path,position)
        SELECT id,photo_path,0 FROM items WHERE photo_path IS NOT NULL AND photo_path<>''
        ON CONFLICT (item_id,file_path) DO NOTHING''')


@dataclass(frozen=True)
class Revision:
    version: int
    name: str
    sqlite_file: str
    postgres_file: str

    def sql(self, backend):
        return (SQL_DIR / (self.postgres_file if backend == 'postgres' else self.sqlite_file)).read_text()

    def checksum(self, backend):
        callbacks = (inspect.getsource(_ensure_session_version) + inspect.getsource(_backfill_legacy_covers)
                     if self.version == 1 else '')
        payload = json.dumps([self.version, self.name, backend, self.sql(backend), callbacks], separators=(',', ':'))
        return hashlib.sha256(payload.encode()).hexdigest()


REVISIONS = (
    Revision(1, 'legacy_v07', '001_legacy_sqlite.sql', '001_legacy_postgres.sql'),
    Revision(2, 'durable_photo_deletions', '002_photo_deletions.sql', '002_photo_deletions.sql'),
    Revision(3, 'durable_photo_writes', '003_photo_writes.sql', '003_photo_writes.sql'),
)


def statements(sql):
    """Static SQL only; quoted semicolons are not statement boundaries."""
    pending = ''
    for char in sql:
        pending += char
        if char == ';' and sqlite3.complete_statement(pending):
            if pending.strip():
                yield pending.strip()
            pending = ''
    if pending.strip():
        raise MigrationError('Migration SQL must contain complete semicolon-terminated statements')


def _exists(connection, backend):
    if backend == 'postgres':
        return bool(connection.execute('''SELECT 1 FROM information_schema.tables
            WHERE table_schema=current_schema() AND table_name='schema_migrations' ''').fetchone())
    return bool(connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone())


def history(connection, backend):
    if not _exists(connection, backend):
        return []
    rows = connection.execute('SELECT version,name,checksum FROM schema_migrations ORDER BY version').fetchall()
    if len(rows) > len(REVISIONS):
        raise MigrationError('Database migration history is newer than this application')
    for row, expected in zip(rows, REVISIONS):
        if row['version'] != expected.version or row['name'] != expected.name:
            raise MigrationError('Database migration history is unknown or has a gap')
        if row['checksum'] != expected.checksum(backend):
            raise MigrationError('Applied migration checksum does not match this application')
    return rows


def _sqlite_catalog(connection, tables):
    result = {}
    for table in tables:
        columns = connection.execute(f'PRAGMA table_info({table})').fetchall()
        unique = {tuple(sorted(r['name'] for r in columns if r['pk']))} - {()}
        for index in connection.execute(f'PRAGMA index_list({table})'):
            if index['unique'] and not index['partial']:
                # Generated/internal names come only from the SQLite catalog.
                name = index['name'].replace('"', '""')
                unique.add(tuple(sorted(r['name'] for r in connection.execute(f'PRAGMA index_info("{name}")'))))
        foreign = set()
        grouped = {}
        for row in connection.execute(f'PRAGMA foreign_key_list({table})'):
            grouped.setdefault(row['id'], []).append(row)
        for rows in grouped.values():
            rows.sort(key=lambda r: r['seq'])
            foreign.add((tuple(r['from'] for r in rows), rows[0]['table'],
                         tuple(r['to'] for r in rows), rows[0]['on_delete'].upper()))
        result[table] = {
            'columns': {r['name']: ('integer' if 'INT' in r['type'].upper() else r['type'].lower(),
                                    bool(r['notnull'] or r['pk'])) for r in columns},
            'unique': unique, 'foreign': foreign}
    return result


@lru_cache(maxsize=1)
def expected_catalog():
    with closing(sqlite3.connect(':memory:')) as connection:
        connection.row_factory = sqlite3.Row
        for revision in REVISIONS:
            for sql in statements(revision.sql('sqlite')):
                connection.execute(sql)
        tables = [r['name'] for r in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return _sqlite_catalog(connection, tables)


def validate_catalog(connection, backend, *, validate_data=False):
    """Check required columns/types/nullability, unique keys and ownership FKs.

    This is not an exhaustive CHECK/default/trigger/performance-index drift audit.
    Table identifiers originate in the immutable expected catalog, not input.
    """
    expected = expected_catalog()
    if backend == 'sqlite':
        actual = _sqlite_catalog(connection, expected)
    else:
        actual = {table: {'columns': {}, 'unique': set(), 'foreign': set()} for table in expected}
        for row in connection.execute('''SELECT table_name,column_name,data_type,is_nullable
            FROM information_schema.columns WHERE table_schema=current_schema()'''):
            if row['table_name'] in actual:
                kind = 'integer' if row['data_type'] in ('integer', 'bigint', 'smallint') else row['data_type']
                actual[row['table_name']]['columns'][row['column_name']] = (kind, row['is_nullable'] == 'NO')
        for row in connection.execute('''SELECT t.relname AS table_name,
            array_agg(a.attname ORDER BY k.ordinality) AS columns
            FROM pg_index i JOIN pg_class t ON t.oid=i.indrelid
            JOIN pg_namespace n ON n.oid=t.relnamespace
            CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY k(attnum,ordinality)
            JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=k.attnum
            WHERE n.nspname=current_schema() AND i.indisunique AND i.indisvalid AND i.indisready AND i.indpred IS NULL
                AND i.indexprs IS NULL AND k.ordinality<=i.indnkeyatts
            GROUP BY t.relname,i.indexrelid'''):
            if row['table_name'] in actual:
                actual[row['table_name']]['unique'].add(tuple(sorted(row['columns'])))
        for row in connection.execute('''SELECT t.relname AS table_name,r.relname AS ref_table,c.confdeltype,
            ARRAY(SELECT a.attname FROM unnest(c.conkey) WITH ORDINALITY k(num,ord)
                JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.num ORDER BY k.ord) AS columns,
            ARRAY(SELECT a.attname FROM unnest(c.confkey) WITH ORDINALITY k(num,ord)
                JOIN pg_attribute a ON a.attrelid=c.confrelid AND a.attnum=k.num ORDER BY k.ord) AS ref_columns
            FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid
            JOIN pg_class r ON r.oid=c.confrelid JOIN pg_namespace n ON n.oid=t.relnamespace
            WHERE c.contype='f' AND n.nspname=current_schema()'''):
            if row['table_name'] in actual:
                delete = {'a': 'NO ACTION', 'r': 'RESTRICT', 'c': 'CASCADE', 'n': 'SET NULL', 'd': 'SET DEFAULT'}[row['confdeltype']]
                actual[row['table_name']]['foreign'].add((tuple(row['columns']), row['ref_table'],
                                                        tuple(row['ref_columns']), delete))
    if actual != expected:
        raise MigrationError('Database structure differs from the supported schema; investigate without stamping history')
    if validate_data:
        if backend == 'sqlite':
            invalid = connection.execute('PRAGMA foreign_key_check').fetchone()
        else:
            invalid = connection.execute('''SELECT 1 FROM pg_constraint c
                JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace
                WHERE n.nspname=current_schema() AND NOT c.convalidated LIMIT 1''').fetchone()
        if invalid:
            raise MigrationError('Existing data/constraints require investigation before schema adoption')


def check_current(connection, backend):
    rows = history(connection, backend)
    if len(rows) != len(REVISIONS):
        raise MigrationError('Database upgrade required: run python -m tools.migrate --apply during maintenance')
    validate_catalog(connection, backend)
    return {'current': len(rows), 'required': len(REVISIONS), 'ready': True}


def migrate(connection, backend):
    """Own one transaction for the entire pending batch, including its ledger."""
    if backend not in ('sqlite', 'postgres'):
        raise MigrationError('Unsupported database backend')
    connection.execute('BEGIN IMMEDIATE')
    try:
        if backend == 'postgres':
            connection.execute("SET LOCAL lock_timeout='15s'")
            connection.execute("SET LOCAL statement_timeout='120s'")
            connection.execute('SELECT pg_advisory_xact_lock(6182006)')
        connection.execute(LEDGER_SQL)
        rows = history(connection, backend)
        pending = REVISIONS[len(rows):]
        for revision in pending:
            for sql in statements(revision.sql(backend)):
                # Never permit an embedded COMMIT/PRAGMA/VACUUM or other
                # transaction escape in a future revision file.
                if not sql.upper().startswith(('CREATE TABLE ', 'CREATE INDEX ', 'CREATE UNIQUE INDEX ',
                                               'ALTER TABLE ', 'INSERT INTO ', 'UPDATE ', 'DELETE FROM ')):
                    raise MigrationError('Unsupported migration statement; atomic SQL only')
                connection.execute(sql)
            if revision.version == 1:
                _ensure_session_version(connection, backend)
        validate_catalog(connection, backend, validate_data=True)
        _backfill_legacy_covers(connection, backend)
        for revision in pending:
            connection.execute('INSERT INTO schema_migrations(version,name,checksum,applied_at) VALUES (?,?,?,?)',
                               (revision.version, revision.name, revision.checksum(backend), int(time.time())))
        connection.execute('COMMIT')
    except BaseException:
        try:
            connection.execute('ROLLBACK')
        except Exception:
            # A lost connection is closed by its owner; do not replace the
            # original failure with a second driver error containing details.
            pass
        raise
    return {'applied': len(pending), 'current': len(REVISIONS), 'ready': True}
