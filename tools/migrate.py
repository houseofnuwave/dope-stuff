"""Inspect schema without changing it; explicitly --apply only during maintenance."""
import argparse
from contextlib import contextmanager
import json
import os
import sqlite3
from urllib.parse import quote

from app import db, schema_migrations


HOSTED_APPROVAL = 'YES_BACKUP_VERIFIED_AND_WRITES_STOPPED'


def authorize_apply(*, apply: bool, confirmed: bool) -> None:
    """Require an explicit second approval before a hosted schema mutation.

    This is an operator acknowledgement, NOT proof that backups or write drains
    actually happened. Never inspect or log the database URL or credentials.
    """
    if confirmed and not apply:
        raise ValueError('Maintenance confirmation requires --apply')
    if not apply:
        return
    environment = os.getenv('FORM_ENV', 'development').strip().lower()
    if environment not in {'development', 'test', 'staging', 'production'}:
        raise ValueError('Unsupported migration environment')
    if environment in {'staging', 'production'}:
        if not confirmed or os.getenv('FORM_MIGRATION_CONFIRM') != HOSTED_APPROVAL:
            raise PermissionError('Hosted migration approval required')


@contextmanager
def inspection_connection():
    if db.postgres_enabled():
        with db.connect() as connection:
            connection.execute('BEGIN READ ONLY')
            try:
                yield connection
            finally:
                connection.execute('ROLLBACK')
    else:
        # mode=ro avoids creating a missing DB or switching its journal mode.
        connection = sqlite3.connect('file:' + quote(str(db.DB_PATH.resolve())) + '?mode=ro', uri=True)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='apply all pending revisions atomically')
    parser.add_argument('--confirm-hosted-maintenance', action='store_true',
                        help='acknowledge independently verified backups and stopped writes for hosted --apply')
    args = parser.parse_args()
    try:
        authorize_apply(apply=args.apply, confirmed=args.confirm_hosted_maintenance)
    except (PermissionError, ValueError):
        # Approval errors must not print environment values, connection strings,
        # provider details or other secrets. No database connection was opened.
        print(json.dumps({'ready': False, 'error': 'Migration approval missing or invalid; see MIGRATIONS.md.'}))
        return 2
    backend = 'postgres' if db.postgres_enabled() else 'sqlite'
    try:
        if args.apply:
            with db.connect() as connection:
                result = schema_migrations.migrate(connection, backend)
        else:
            with inspection_connection() as connection:
                result = schema_migrations.check_current(connection, backend)
    except Exception:
        # Driver errors may contain connection details, SQL or private values.
        print(json.dumps({'ready': False, 'error': 'Schema check/upgrade failed. Preserve backups and investigate; no history bypass is offered.'}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
