"""Inspect schema without changing it; explicitly --apply only during maintenance."""
import argparse
from contextlib import contextmanager
import json
import sqlite3
from urllib.parse import quote

from app import db, schema_migrations


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
    args = parser.parse_args()
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
