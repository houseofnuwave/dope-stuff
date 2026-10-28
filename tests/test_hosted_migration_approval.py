"""Hosted schema mutations require explicit operator approval, before DB access.

All targets and credentials here are synthetic. No hosted services are contacted.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import sys

import pytest

from tools import migrate


@pytest.mark.parametrize("environment", ["staging", "production"])
@pytest.mark.parametrize("flag,acknowledgement", [
    (False, None),
    (True, None),
    (False, migrate.HOSTED_APPROVAL),
    (True, "NO"),
])
def test_hosted_apply_refuses_without_both_confirmations(
    monkeypatch, capsys, environment, flag, acknowledgement
):
    monkeypatch.setenv("FORM_ENV", environment)
    monkeypatch.setenv("FORM_DATABASE_URL", "postgresql://user:private-marker@example.invalid/db")
    if acknowledgement is None:
        monkeypatch.delenv("FORM_MIGRATION_CONFIRM", raising=False)
    else:
        monkeypatch.setenv("FORM_MIGRATION_CONFIRM", acknowledgement)
    # Even backend selection must not happen before authorization.
    monkeypatch.setattr(migrate.db, "postgres_enabled",
                        lambda: pytest.fail("must reject before DB backend selection"))
    monkeypatch.setattr(migrate.db, "connect",
                        lambda: pytest.fail("must not connect to database"))
    argv = ["migrate", "--apply"]
    if flag:
        argv.append("--confirm-hosted-maintenance")
    monkeypatch.setattr(sys, "argv", argv)
    assert migrate.main() == 2
    output = capsys.readouterr().out
    assert json.loads(output)["ready"] is False
    assert "private-marker" not in output
    assert "example.invalid" not in output


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_approved_hosted_apply_runs_only_explicit_migrator(monkeypatch, capsys, environment):
    monkeypatch.setenv("FORM_ENV", environment)
    monkeypatch.setenv("FORM_MIGRATION_CONFIRM", migrate.HOSTED_APPROVAL)
    monkeypatch.setattr(sys, "argv", ["migrate", "--apply", "--confirm-hosted-maintenance"])
    monkeypatch.setattr(migrate.db, "postgres_enabled", lambda: True)
    target = object()
    calls = []

    @contextmanager
    def connection():
        calls.append("connect")
        yield target

    monkeypatch.setattr(migrate.db, "connect", connection)
    def apply(connection, backend):
        assert connection is target and backend == "postgres"
        calls.append("migrate")
        return {"ready": True, "applied": 0}
    monkeypatch.setattr(migrate.schema_migrations, "migrate", apply)
    assert migrate.main() == 0
    assert calls == ["connect", "migrate"]
    assert json.loads(capsys.readouterr().out)["ready"] is True


def test_read_only_inspection_still_requires_no_approval(monkeypatch, capsys):
    monkeypatch.setenv("FORM_ENV", "production")
    monkeypatch.delenv("FORM_MIGRATION_CONFIRM", raising=False)
    monkeypatch.setattr(sys, "argv", ["migrate"])
    monkeypatch.setattr(migrate.db, "postgres_enabled", lambda: True)

    @contextmanager
    def inspection():
        yield object()

    monkeypatch.setattr(migrate, "inspection_connection", inspection)
    monkeypatch.setattr(migrate.schema_migrations, "check_current",
                        lambda connection, backend: {"ready": True})
    assert migrate.main() == 0
    assert json.loads(capsys.readouterr().out)["ready"] is True


def test_local_development_apply_remains_usable(monkeypatch):
    monkeypatch.setenv("FORM_ENV", "development")
    monkeypatch.delenv("FORM_MIGRATION_CONFIRM", raising=False)
    migrate.authorize_apply(apply=True, confirmed=False)
    monkeypatch.setenv("FORM_ENV", "test")
    migrate.authorize_apply(apply=True, confirmed=False)


@pytest.mark.parametrize("environment", ["prod", "preview", "", "PRODUCTION "])
def test_unrecognized_environment_refused_except_canonical_production(monkeypatch, environment):
    monkeypatch.setenv("FORM_ENV", environment)
    if environment == "PRODUCTION ":
        with pytest.raises(PermissionError):
            migrate.authorize_apply(apply=True, confirmed=False)
    else:
        with pytest.raises(ValueError):
            migrate.authorize_apply(apply=True, confirmed=False)


def test_confirmation_flag_cannot_be_used_with_read_only_inspection(monkeypatch):
    monkeypatch.setenv("FORM_ENV", "staging")
    with pytest.raises(ValueError):
        migrate.authorize_apply(apply=False, confirmed=True)
