"""Atomic publication regressions for encrypted local recovery points.

All tests use disposable SQLite data and synthetic keys; no provider services.
"""
import base64
import secrets

import pytest

from tools import ops_backup


@pytest.fixture
def backup_key(seller, monkeypatch):
    monkeypatch.setenv(
        "FORM_BACKUP_KEY", base64.b64encode(secrets.token_bytes(32)).decode()
    )


def test_competing_backup_cannot_be_overwritten(backup_key, monkeypatch, tmp_path):
    destination = tmp_path / "recovery.formbak"
    competing_bytes = b"another operator's recovery point"
    original_verify = ops_backup.verify_backup

    def competing_writer(pending):
        result = original_verify(pending)
        # A second writer creates the destination after our early existence
        # check but before publication. This must never be overwritten.
        destination.write_bytes(competing_bytes)
        return result

    monkeypatch.setattr(ops_backup, "verify_backup", competing_writer)
    with pytest.raises(ops_backup.BackupError, match="Refusing to overwrite"):
        ops_backup.create_backup(destination)

    assert destination.read_bytes() == competing_bytes
    assert not list(tmp_path.glob(".form-backup-*"))


def test_dangling_symlink_destination_is_not_followed(backup_key, tmp_path):
    destination = tmp_path / "recovery.formbak"
    unexpected_target = tmp_path / "elsewhere.formbak"
    destination.symlink_to(unexpected_target)

    with pytest.raises(ops_backup.BackupError, match="Refusing to overwrite"):
        ops_backup.create_backup(destination)

    assert destination.is_symlink()
    assert not unexpected_target.exists()
    assert not list(tmp_path.glob(".form-backup-*"))


def test_failed_verification_never_publishes_or_leaves_pending(
    backup_key, monkeypatch, tmp_path
):
    destination = tmp_path / "recovery.formbak"

    def fail_validation(_pending):
        raise ops_backup.BackupError("synthetic verification failure")

    monkeypatch.setattr(ops_backup, "verify_backup", fail_validation)
    with pytest.raises(ops_backup.BackupError, match="verification failure"):
        ops_backup.create_backup(destination)

    assert not destination.exists()
    assert not list(tmp_path.glob(".form-backup-*"))


def test_successful_publication_remains_private_and_verifiable(
    backup_key, tmp_path
):
    destination = tmp_path / "recovery.formbak"
    result = ops_backup.create_backup(destination)

    assert result["encrypted"] is True
    assert destination.stat().st_mode & 0o777 == 0o600
    assert ops_backup.verify_backup(destination)["files"] >= 1
    assert not list(tmp_path.glob(".form-backup-*"))
