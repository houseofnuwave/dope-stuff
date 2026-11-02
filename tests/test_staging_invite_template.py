"""Self-hosted staging must not silently omit the private registration gate.

This is a deployment-template contract; runtime length validation lives in the
application (see the hosted-invite gate PR). No deployment is performed here.
"""
from pathlib import Path
import os
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_staging_template_requires_invite_without_a_shipped_default():
    compose = (ROOT / "compose.staging.yaml").read_text()
    example = (ROOT / ".env.staging.example").read_text()
    assert "FORM_PILOT_INVITE_CODE: ${FORM_PILOT_INVITE_CODE:?" in compose
    assert "FORM_PILOT_INVITE_CODE=\n" in example
    assert "FORM_PILOT_INVITE_CODE=REPLACE" not in example


@pytest.mark.parametrize("invite, expected_success", [
    (None, False),
    ("", False),
    ("synthetic-private-invite-code-for-ci", True),
])
def test_compose_config_fails_closed_on_missing_invite(invite, expected_success):
    if not shutil.which("docker"):
        pytest.skip("Docker Compose CLI unavailable")
    version = subprocess.run(["docker", "compose", "version"],
                             capture_output=True, text=True, timeout=10)
    if version.returncode:
        pytest.skip("Docker Compose plugin unavailable")

    # Never inherit a real seller secret or staging hostname from the runner.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("FORM_")}
    env.update({
        "FORM_STAGE_DOMAIN": "stage.example.test",
        "FORM_SESSION_SECRET": "synthetic-session-secret-for-ci-only",
        "FORM_PILOT_ACCESS_HASH": "synthetic-access-hash-for-ci-only",
    })
    if invite is not None:
        env["FORM_PILOT_INVITE_CODE"] = invite
    result = subprocess.run(
        ["docker", "compose", "-f", "compose.staging.yaml", "config", "--quiet"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=20,
    )
    if expected_success:
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0
        assert "FORM_PILOT_INVITE_CODE" in result.stderr
