"""SQLite persistence; replace behind this boundary for hosted multi-instance deployments."""
from __future__ import annotations
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(os.getenv("FORM_DATA_DIR", "data"))
DB_PATH = DATA_DIR / "form.db"

# Compatibility schema snapshots for tools/tests. Runtime changes are made only
# through immutable migration SQL and its checksummed ledger.
_SQL = Path(__file__).with_name('migration_sql')
PHOTO_CLEANUP_SCHEMA = (_SQL / '002_photo_deletions.sql').read_text() + '\n' + (_SQL / '003_photo_writes.sql').read_text()
SCHEMA = 'PRAGMA foreign_keys = ON;\n' + (_SQL / '001_legacy_sqlite.sql').read_text() + '\n' + PHOTO_CLEANUP_SCHEMA
PG_SCHEMA = (_SQL / '001_legacy_postgres.sql').read_text() + '\n' + PHOTO_CLEANUP_SCHEMA


def postgres_enabled() -> bool:
    return bool(os.getenv('FORM_DATABASE_URL', '').strip())


def postgres_sql(sql: str) -> str:
    """Normalize the narrow SQLite SQL subset used by FORM's existing API.

    Callers never interpolate user-supplied SQL identifiers; values remain bound
    parameters. Keep all new SQL in this supported subset or use backend-specific
    queries explicitly.
    """
    if sql.strip().upper() == 'BEGIN IMMEDIATE':
        return 'BEGIN'
    sql = sql.replace("datetime('now')", "to_char(now() at time zone 'UTC','YYYY-MM-DD HH24:MI:SS')")
    sql = sql.replace('INSERT OR IGNORE INTO pilot_requests(email) VALUES (?)',
                      'INSERT INTO pilot_requests(email) VALUES (?) ON CONFLICT (email) DO NOTHING')
    return sql.replace(' LIKE ', ' ILIKE ').replace('?', '%s')


class HybridRow(dict):
    """Preserve sqlite3.Row's numeric and named indexing across DB backends."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class PostgresResult:
    def __init__(self, cursor): self.cursor = cursor
    def fetchone(self):
        item = self.cursor.fetchone()
        return HybridRow(item) if item is not None else None
    def fetchall(self):
        return [HybridRow(x) for x in self.cursor.fetchall()]
    def __iter__(self):
        return (HybridRow(x) for x in self.cursor)


class PostgresConnection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, params=()):
        import psycopg
        try:
            return PostgresResult(self.connection.execute(postgres_sql(query), params))
        except psycopg.IntegrityError as exc:
            # Preserve the stable endpoint-level duplicate and conflict handling
            # during the backend transition. A failed explicit transaction is
            # rolled back when the connection closes.
            raise sqlite3.IntegrityError(str(exc)) from exc

    def close(self):
        self.connection.close()


def init_db():
    from . import schema_migrations
    backend = 'postgres' if postgres_enabled() else 'sqlite'
    with connect() as connection:
        if os.getenv('FORM_ENV', 'development').lower().strip() in {'staging', 'production'}:
            schema_migrations.check_current(connection, backend)
        else:
            schema_migrations.migrate(connection, backend)


def hosted_postgres_sslmode(conninfo: str) -> str:
    """Require encrypted PostgreSQL transport in staging and production.

    libpq defaults to sslmode=prefer, which can silently fall back to
    plaintext. Preserve stronger certificate checks requested in either the
    connection string or FORM_DATABASE_SSLMODE. Reject insecure settings
    rather than silently overriding them. Local/test PostgreSQL is unchanged.
    """
    from psycopg.conninfo import conninfo_to_dict

    try:
        requested = str(conninfo_to_dict(conninfo).get('sslmode') or '').strip().lower()
    except Exception:
        # libpq parsing errors may contain credentials from the connection URL.
        raise RuntimeError('Invalid hosted PostgreSQL connection settings') from None
    configured = os.getenv('FORM_DATABASE_SSLMODE', '').strip().lower()
    strength = {'require': 1, 'verify-ca': 2, 'verify-full': 3}
    if (requested and requested not in strength) or (configured and configured not in strength):
        raise RuntimeError('Hosted PostgreSQL requires TLS: use require, verify-ca or verify-full')
    return max((requested or 'require', configured or 'require'),
               key=strength.__getitem__)


@contextmanager
def connect():
    if postgres_enabled():
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError('Postgres requires installing psycopg[binary] from requirements.txt') from exc
        # Single-connection, autocommit mode mirrors FORM's SQLite semantics.
        # Explicit BEGIN/COMMIT used by multi-step writes remain transactional.
        conninfo = os.environ['FORM_DATABASE_URL']
        ssl_kwargs = {}
        if os.getenv('FORM_ENV', 'development').strip().lower() in {'staging', 'production'}:
            ssl_kwargs['sslmode'] = hosted_postgres_sslmode(conninfo)
        conn = psycopg.connect(conninfo, row_factory=dict_row, autocommit=True,
                               connect_timeout=8, **ssl_kwargs)
        try:
            yield PostgresConnection(conn)
        finally:
            conn.close()
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=15, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    db.execute('PRAGMA journal_mode = WAL')
    db.execute('PRAGMA busy_timeout = 5000')
    try:
        yield db
    finally:
        db.close()


def rowdict(row):
    return dict(row) if row is not None else None
