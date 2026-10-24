"""The disposable preview must not auto-upgrade or silently use local SQLite."""
from contextlib import contextmanager

import pytest

from tools import free_preview_bootstrap as preview


class InspectionConnection:
    def __init__(self, table_count):
        self.table_count = table_count
        self.statements = []

    def execute(self, sql):
        self.statements.append(sql)
        if "COUNT(*)" in sql:
            class Result:
                def fetchone(_self):
                    return {"total": self.table_count}
            return Result()


@contextmanager
def connection_factory(table_count, all_connections):
    c = InspectionConnection(table_count)
    all_connections.append(c)
    yield c


def configure(monkeypatch):
    for name, value in {
        "FORM_FREE_PREVIEW_BOOTSTRAP": "YES_FRESH_FREE_PREVIEW_ONLY",
        "FORM_ENV": "staging",
        "FORM_CLOUD_MODE": "true",
        "FORM_PHOTO_STORAGE": "s3",
        "FORM_S3_PREFIX": "preview",
        "FORM_DATABASE_URL": "postgresql://not-a-real-db",
    }.items():
        monkeypatch.setenv(name, value)


def test_rejects_production_even_with_preview_flag(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv("FORM_ENV", "production")
    with pytest.raises(RuntimeError, match="Refusing bootstrap"):
        preview.bootstrap()


def test_rejects_sqlite_or_non_preview_prefix(monkeypatch):
    configure(monkeypatch)
    monkeypatch.delenv("FORM_DATABASE_URL")
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        preview.bootstrap()
    monkeypatch.setenv("FORM_DATABASE_URL", "postgresql://not-a-real-db")
    monkeypatch.setenv("FORM_S3_PREFIX", "staging")
    with pytest.raises(RuntimeError, match="Refusing bootstrap"):
        preview.bootstrap()


def test_initializes_only_empty_preview(monkeypatch):
    configure(monkeypatch)
    conns = []
    monkeypatch.setattr(preview.db, "connect", lambda: connection_factory(0, conns))
    calls = []
    monkeypatch.setattr(preview.schema_migrations, "migrate",
                        lambda conn, kind: calls.append(("migrate", kind)) or {"ready": True})
    monkeypatch.setattr(preview.schema_migrations, "check_current",
                        lambda conn, kind: calls.append(("check", kind)) or {"ready": True})
    assert preview.bootstrap()["ready"]
    assert calls == [("migrate", "postgres")]
    assert conns[0].statements == ["BEGIN READ ONLY", 
                                  "SELECT COUNT(*) AS total FROM information_schema.tables WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'",
                                  "ROLLBACK"]


def test_existing_preview_checks_only_and_rejects_outdated_schema(monkeypatch):
    configure(monkeypatch)
    conns = []
    monkeypatch.setattr(preview.db, "connect", lambda: connection_factory(1, conns))
    monkeypatch.setattr(preview.schema_migrations, "migrate",
                        lambda *_: pytest.fail("existing database must never be migrated at startup"))
    def out_of_date(*_):
        raise RuntimeError("Schema upgrade required")
    monkeypatch.setattr(preview.schema_migrations, "check_current", out_of_date)
    with pytest.raises(RuntimeError, match="upgrade required"):
        preview.bootstrap()
