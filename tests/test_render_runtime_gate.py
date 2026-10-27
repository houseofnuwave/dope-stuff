"""Render must not silently launch insecure dev mode or ephemeral local storage.

Configuration checks run in fresh processes because app.main reads env on import.
No database, object storage or hosted service is contacted by these tests.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
IMPORT = "from app import main; print(main.ENVIRONMENT)"


def config(tmp_path):
    # All values are synthetic; no credentials or live services are used.
    return {
        **os.environ,
        'RENDER': 'true',
        'FORM_ENV': 'staging',
        'FORM_CLOUD_MODE': 'true',
        'FORM_SESSION_SECRET': 'synthetic-test-session-secret-not-for-deployment',
        'FORM_COOKIE_SECURE': 'true',
        'FORM_ALLOWED_HOSTS': 'stage.example.com',
        'FORM_PUBLIC_ORIGIN': 'https://stage.example.com',
        'FORM_DATA_DIR': str(tmp_path),
        'FORM_DATABASE_URL': 'postgresql://synthetic:synthetic@db.example.com/preview',
        'FORM_PHOTO_STORAGE': 's3',
        'FORM_S3_BUCKET': 'synthetic-private-bucket',
        'FORM_S3_ENDPOINT': 'https://r2.example.com',
        'FORM_S3_ACCESS_KEY_ID': 'synthetic',
        'FORM_S3_SECRET_ACCESS_KEY': 'synthetic',
        'FORM_PILOT_INVITE_CODE': 'synthetic-private-invite-code',
        'FORM_RECOVERY_MODE': 'disabled',
    }


def import_with(env):
    return subprocess.run(
        [sys.executable, '-c', IMPORT], cwd=ROOT,
        env=env, capture_output=True, text=True, timeout=20,
    )


@pytest.mark.parametrize('environment', ['development', 'test'])
def test_render_refuses_non_hosted_mode(tmp_path, environment):
    env = config(tmp_path)
    env['FORM_ENV'] = environment
    result = import_with(env)
    assert result.returncode != 0
    assert 'Render hosting requires FORM_ENV=staging or production' in result.stderr


@pytest.mark.parametrize('environment', ['staging', 'production'])
@pytest.mark.parametrize('cloud_mode', [None, '', 'false'])
def test_render_refuses_ephemeral_fallback(tmp_path, environment, cloud_mode):
    env = config(tmp_path)
    env['FORM_ENV'] = environment
    if cloud_mode is None:
        env.pop('FORM_CLOUD_MODE')
    else:
        env['FORM_CLOUD_MODE'] = cloud_mode
    result = import_with(env)
    assert result.returncode != 0
    assert 'Render hosting requires FORM_CLOUD_MODE=true' in result.stderr


@pytest.mark.parametrize('environment', ['staging', 'production'])
def test_render_accepts_complete_cloud_configuration(tmp_path, environment):
    env = config(tmp_path)
    env['FORM_ENV'] = environment
    result = import_with(env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == environment


def test_render_cloud_mode_still_requires_database_and_storage(tmp_path):
    env = config(tmp_path)
    env.pop('FORM_DATABASE_URL')
    result = import_with(env)
    assert result.returncode != 0
    assert 'Cloud mode requires managed PostgreSQL' in result.stderr

    env = config(tmp_path)
    env['FORM_PHOTO_STORAGE'] = 'local'
    result = import_with(env)
    assert result.returncode != 0
    assert 'Cloud mode requires private S3-compatible photo storage' in result.stderr


def test_non_render_persistent_volume_staging_remains_supported(tmp_path):
    env = config(tmp_path)
    env.pop('RENDER')
    env.pop('FORM_CLOUD_MODE')
    env.pop('FORM_DATABASE_URL')
    env['FORM_PHOTO_STORAGE'] = 'local'
    result = import_with(env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'staging'
