"""Staging/production PostgreSQL must not silently fall back to plaintext."""
from __future__ import annotations

import psycopg
import pytest

from app import db


class FakeConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def spy_connect(monkeypatch):
    captured = []
    def fake_connect(conninfo, **kwargs):
        connection = FakeConnection()
        captured.append((conninfo, kwargs, connection))
        return connection
    monkeypatch.setattr(psycopg, 'connect', fake_connect)
    return captured


@pytest.mark.parametrize('environment', ['staging', 'production'])
def test_hosted_postgres_enforces_tls_by_default(monkeypatch, environment):
    monkeypatch.setenv('FORM_ENV', environment)
    monkeypatch.setenv('FORM_DATABASE_URL', 'postgresql://user:private-marker@example.invalid/db')
    monkeypatch.delenv('FORM_DATABASE_SSLMODE', raising=False)
    captured = spy_connect(monkeypatch)
    with db.connect() as connection:
        assert isinstance(connection, db.PostgresConnection)
    assert len(captured) == 1
    assert captured[0][1]['sslmode'] == 'require'
    assert captured[0][1]['connect_timeout'] == 8
    assert captured[0][2].closed


@pytest.mark.parametrize('mode', ['verify-ca', 'verify-full'])
def test_preserves_stronger_sslmode_from_database_url(monkeypatch, mode):
    monkeypatch.setenv('FORM_ENV', 'staging')
    monkeypatch.setenv('FORM_DATABASE_URL',
                       f'postgresql://user:pass@example.invalid/db?sslmode={mode}')
    monkeypatch.delenv('FORM_DATABASE_SSLMODE', raising=False)
    captured = spy_connect(monkeypatch)
    with db.connect():
        pass
    assert captured[0][1]['sslmode'] == mode


def test_stronger_environment_mode_is_not_downgraded(monkeypatch):
    monkeypatch.setenv('FORM_ENV', 'production')
    monkeypatch.setenv('FORM_DATABASE_URL',
                       'postgresql://user:pass@example.invalid/db?sslmode=verify-full')
    monkeypatch.setenv('FORM_DATABASE_SSLMODE', 'verify-ca')
    captured = spy_connect(monkeypatch)
    with db.connect():
        pass
    assert captured[0][1]['sslmode'] == 'verify-full'


@pytest.mark.parametrize('mode', ['disable', 'allow', 'prefer', 'invalid'])
@pytest.mark.parametrize('source', ['url', 'environment'])
def test_insecure_sslmode_fails_closed_without_network(monkeypatch, mode, source):
    monkeypatch.setenv('FORM_ENV', 'staging')
    monkeypatch.setenv('FORM_DATABASE_URL', 'postgresql://user:private-marker@example.invalid/db')
    monkeypatch.delenv('FORM_DATABASE_SSLMODE', raising=False)
    if source == 'url':
        monkeypatch.setenv('FORM_DATABASE_URL',
                           f'postgresql://user:private-marker@example.invalid/db?sslmode={mode}')
    else:
        monkeypatch.setenv('FORM_DATABASE_SSLMODE', mode)
    captured = spy_connect(monkeypatch)
    with pytest.raises(RuntimeError, match='Hosted PostgreSQL requires TLS') as exc:
        with db.connect():
            pass
    assert not captured
    assert 'private-marker' not in str(exc.value)


def test_test_environment_keeps_plaintext_local_postgres_available(monkeypatch):
    monkeypatch.setenv('FORM_ENV', 'test')
    monkeypatch.setenv('FORM_DATABASE_URL', 'postgresql://test:test@localhost/test')
    monkeypatch.delenv('FORM_DATABASE_SSLMODE', raising=False)
    captured = spy_connect(monkeypatch)
    with db.connect():
        pass
    assert 'sslmode' not in captured[0][1]


def test_hosted_malformed_conninfo_does_not_echo_credentials(monkeypatch):
    monkeypatch.setenv('FORM_ENV', 'staging')
    monkeypatch.setenv('FORM_DATABASE_URL', 'postgresql://user:private-marker@bad host/db')
    monkeypatch.delenv('FORM_DATABASE_SSLMODE', raising=False)
    captured = spy_connect(monkeypatch)
    with pytest.raises(RuntimeError) as exc:
        with db.connect():
            pass
    assert not captured
    assert 'private-marker' not in str(exc.value)
