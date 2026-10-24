"""One-time schema bootstrap for a NEW, disposable Render free-preview database.

This deliberately is not a general hosted migration mechanism. Existing databases
must already be fully migrated; upgrades require the separate operator procedure.
"""
from __future__ import annotations

import os

from app import db, schema_migrations


def _require_disposable_preview() -> None:
    expected = {
        "FORM_FREE_PREVIEW_BOOTSTRAP": "YES_FRESH_FREE_PREVIEW_ONLY",
        "FORM_ENV": "staging",
        "FORM_CLOUD_MODE": "true",
        "FORM_PHOTO_STORAGE": "s3",
        "FORM_S3_PREFIX": "preview",
    }
    if any(os.getenv(key) != value for key, value in expected.items()):
        raise RuntimeError("Refusing bootstrap outside the explicitly isolated, disposable staging preview")
    if not db.postgres_enabled():
        raise RuntimeError("Free preview requires a managed PostgreSQL database")


def _existing_user_tables() -> int:
    # Read-only inspection must not create or mutate any database objects.
    with db.connect() as connection:
        connection.execute("BEGIN READ ONLY")
        try:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'"
            ).fetchone()
            return int(row["total"])
        finally:
            connection.execute("ROLLBACK")


def bootstrap() -> dict:
    _require_disposable_preview()
    if _existing_user_tables() == 0:
        # Only initialize a completely empty preview database. The migrator
        # performs all revisions atomically using a PostgreSQL advisory lock.
        with db.connect() as connection:
            return schema_migrations.migrate(connection, "postgres")
    # An existing database may NOT be upgraded automatically during startup.
    with db.connect() as connection:
        return schema_migrations.check_current(connection, "postgres")


def main() -> int:
    try:
        result = bootstrap()
    except Exception:
        # Avoid printing potentially sensitive driver/connection details to logs.
        print("Free preview schema check failed. Investigate without bypassing history or copying customer data.")
        return 1
    print("Free preview schema ready:", result.get("ready", False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
