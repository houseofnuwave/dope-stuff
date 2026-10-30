"""Operator recovery archives must contain exactly the referenced inventory photos.

These checks use disposable SQLite records and synthetic photo bytes. They do
not contact any external storage provider or use customer data.
"""
import hashlib
import json
import sqlite3
import zipfile

import pytest

from app import db
from tools import ops_backup


def _archive(tmp_path, photos):
    snapshot = tmp_path / "snapshot.db"
    with db.connect() as source, sqlite3.connect(snapshot) as target:
        source.backup(target)

    files = {"database/form.db": snapshot.read_bytes()}
    files.update({f"photos/{name}": data for name, data in photos.items()})
    manifest = {
        "format": "FORM Seller OS operations backup",
        "version": 1,
        "created_at": "2026-10-30T00:00:00+00:00",
        "files": {
            name: {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
            for name, data in files.items()
        },
    }
    archive_path = tmp_path / "recovery-payload.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
        archive.writestr("manifest.json", json.dumps(manifest))
    return archive_path


def _item(seller, item_input):
    response = seller["client"].post(
        "/api/items", headers=seller["csrf"], json=item_input
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.parametrize("reference", ["cover", "gallery"])
def test_recovery_rejects_missing_referenced_photo(seller, item_input, tmp_path, reference):
    item_id = _item(seller, item_input)
    with db.connect() as connection:
        if reference == "cover":
            connection.execute(
                "UPDATE items SET photo_path=? WHERE id=?", ("missing.webp", item_id)
            )
        else:
            connection.execute(
                "INSERT INTO item_photos (item_id, file_path) VALUES (?, ?)",
                (item_id, "missing.webp"),
            )

    archive = _archive(tmp_path, {})
    with pytest.raises(ops_backup.BackupError, match="do not match database references"):
        ops_backup.validate_zip(archive)


def test_recovery_rejects_unreferenced_photo(seller, tmp_path):
    archive = _archive(tmp_path, {"orphan.webp": b"synthetic orphan bytes"})
    with pytest.raises(ops_backup.BackupError, match="do not match database references"):
        ops_backup.validate_zip(archive)


def test_recovery_accepts_matching_cover_and_gallery(seller, item_input, tmp_path):
    item_id = _item(seller, item_input)
    with db.connect() as connection:
        connection.execute(
            "UPDATE items SET photo_path=? WHERE id=?", ("cover.webp", item_id)
        )
        connection.execute(
            "INSERT INTO item_photos (item_id, file_path) VALUES (?, ?)",
            (item_id, "gallery.webp"),
        )

    archive = _archive(tmp_path, {
        "cover.webp": b"synthetic cover bytes",
        "gallery.webp": b"synthetic gallery bytes",
    })
    assert ops_backup.validate_zip(archive)["photos"] == 2
