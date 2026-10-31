"""Hosted invitation safety checks run in fresh processes to test import-time gates."""

import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def import_with_config(tmp_path, environment, invite=None):
    # Isolate from CI or developer credentials and provider settings.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('FORM_', 'RENDER'))}
    env.update({
        'FORM_ENV': environment,
        'FORM_SESSION_SECRET': 'synthetic-session-secret-for-isolated-tests-123',
        'FORM_COOKIE_SECURE': 'true',
        'FORM_ALLOWED_HOSTS': 'pilot.example',
        'FORM_PUBLIC_ORIGIN': 'https://pilot.example',
        'FORM_DATA_DIR': str(tmp_path),
        'FORM_CLOUD_MODE': 'false',
        'FORM_RECOVERY_MODE': 'disabled',
    })
    if invite is not None:
        env['FORM_PILOT_INVITE_CODE'] = invite
    return subprocess.run(
        [sys.executable, '-c', 'from app import main; assert main.ENVIRONMENT'],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=15,
    )


@pytest.mark.parametrize('environment', ['staging', 'production'])
@pytest.mark.parametrize('invite', [None, '', 'too-short', ' ' * 20])
def test_hosted_rejects_missing_or_short_invite(tmp_path, environment, invite):
    result = import_with_config(tmp_path, environment, invite)
    assert result.returncode != 0
    assert 'Hosted mode requires a 16+ character pilot invite code' in result.stderr
    assert 'too-short' not in result.stderr


@pytest.mark.parametrize('environment', ['staging', 'production'])
def test_hosted_accepts_valid_invite_with_self_hosted_storage(tmp_path, environment):
    result = import_with_config(tmp_path, environment, 'synthetic-invite-code-for-test')
    assert result.returncode == 0, result.stderr


def test_local_development_does_not_require_invite(tmp_path):
    result = import_with_config(tmp_path, 'development')
    assert result.returncode == 0, result.stderr
