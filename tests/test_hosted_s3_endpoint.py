"""Hosted storage credentials must never be sent to a plaintext/malformed endpoint."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from app import photo_storage


@pytest.mark.parametrize('endpoint', [
    'http://account.r2.cloudflarestorage.com',
    'https://user:password@account.r2.cloudflarestorage.com',
    'https://account.r2.cloudflarestorage.com/photos',
    'https://account.r2.cloudflarestorage.com?bucket=other',
    'https://account.r2.cloudflarestorage.com#fragment',
    'https://bad host.example',
    'https://account.r2.cloudflarestorage.com:invalid',
    'https://*.example.com',
    'https://account.r2.cloudflarestorage.com\n',
    '',
])
@pytest.mark.parametrize('mode', ['staging', 'production'])
def test_hosted_endpoint_rejects_unsafe_urls(monkeypatch, endpoint, mode):
    monkeypatch.setenv('FORM_ENV', mode)
    with pytest.raises(RuntimeError, match='credential-free HTTPS origin') as exc:
        photo_storage.validate_hosted_s3_endpoint(endpoint)
    # Never echo potentially credential-bearing endpoint data into logs.
    assert endpoint not in str(exc.value) if endpoint else True


def test_hosted_endpoint_accepts_tls_origin(monkeypatch):
    monkeypatch.setenv('FORM_ENV', 'staging')
    photo_storage.validate_hosted_s3_endpoint('https://account.r2.cloudflarestorage.com')
    photo_storage.validate_hosted_s3_endpoint('https://account.r2.cloudflarestorage.com/')


def test_local_minio_http_remains_supported(monkeypatch):
    monkeypatch.setenv('FORM_ENV', 'test')
    photo_storage.validate_hosted_s3_endpoint('http://127.0.0.1:9000')


def test_s3_client_rejects_http_before_constructing_client(monkeypatch):
    monkeypatch.setenv('FORM_ENV', 'staging')
    monkeypatch.setenv('FORM_S3_BUCKET', 'private-test')
    monkeypatch.setenv('FORM_S3_ENDPOINT', 'http://example.invalid')
    monkeypatch.setenv('FORM_S3_ACCESS_KEY_ID', 'fake')
    monkeypatch.setenv('FORM_S3_SECRET_ACCESS_KEY', 'fake')
    with pytest.raises(RuntimeError, match='credential-free HTTPS origin'):
        photo_storage.s3_client()


def test_hosted_cloud_startup_fails_closed_on_http_endpoint(tmp_path):
    # A fresh interpreter verifies the import-time hosted configuration gate.
    env = dict(os.environ)
    env.update(
        FORM_ENV='staging',
        FORM_CLOUD_MODE='true',
        FORM_SESSION_SECRET='A' * 48,
        FORM_COOKIE_SECURE='true',
        FORM_ALLOWED_HOSTS='staging.example.com',
        FORM_PUBLIC_ORIGIN='https://staging.example.com',
        FORM_DATA_DIR=str(tmp_path),
        FORM_DATABASE_URL='postgresql://unused:unused@example.invalid/preview',
        FORM_PHOTO_STORAGE='s3',
        FORM_S3_BUCKET='private-test',
        FORM_S3_ENDPOINT='http://account.r2.cloudflarestorage.com',
        FORM_S3_ACCESS_KEY_ID='fake',
        FORM_S3_SECRET_ACCESS_KEY='fake',
        FORM_PILOT_INVITE_CODE='invite-code-longer-than-16',
    )
    command = [sys.executable, '-c', 'from app import main; print(main.ENVIRONMENT)']
    blocked = subprocess.run(command, env=env, text=True, capture_output=True, timeout=20)
    assert blocked.returncode != 0
    assert 'Hosted S3 endpoint must be a credential-free HTTPS origin' in blocked.stderr
    assert 'fake' not in blocked.stderr

    env['FORM_S3_ENDPOINT'] = 'https://account.r2.cloudflarestorage.com'
    accepted = subprocess.run(command, env=env, text=True, capture_output=True, timeout=20)
    assert accepted.returncode == 0, accepted.stderr
    assert accepted.stdout.strip() == 'staging'
