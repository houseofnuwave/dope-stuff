"""No external R2 calls: deterministic safety and failure-path tests."""
from __future__ import annotations

import pytest

from tools import staging_storage_probe as probe


@pytest.fixture
def staging(monkeypatch):
    values = {
        "FORM_ENV": "staging",
        "FORM_CLOUD_MODE": "true",
        "FORM_PHOTO_STORAGE": "s3",
        "FORM_S3_PREFIX": "staging",
        "FORM_STORAGE_PROBE_CONFIRM": "YES_PRIVATE_STAGING_R2_ONLY",
        "FORM_S3_ENDPOINT": "https://" + "a" * 32 + ".r2.cloudflarestorage.com",
        "FORM_S3_BUCKET": "synthetic-private-staging",
        "FORM_S3_ACCESS_KEY_ID": "fake-key",
        "FORM_S3_SECRET_ACCESS_KEY": "fake-secret",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values


@pytest.mark.parametrize("key,value", [
    ("FORM_ENV", "production"),
    ("FORM_ENV", "development"),
    ("FORM_CLOUD_MODE", "false"),
    ("FORM_PHOTO_STORAGE", "local"),
    ("FORM_S3_PREFIX", "production"),
    ("FORM_S3_PREFIX", "preview"),
    ("FORM_STORAGE_PROBE_CONFIRM", "NO"),
    ("FORM_S3_BUCKET", ""),
    ("FORM_S3_ACCESS_KEY_ID", ""),
    ("FORM_S3_SECRET_ACCESS_KEY", ""),
])
def test_refuses_unsafe_target_without_storage_calls(staging, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    monkeypatch.setattr(probe.photo_storage, "save_photo",
                        lambda *_: pytest.fail("storage must not be accessed"))
    with pytest.raises(probe.ProbeRefused):
        probe.run_probe()


@pytest.mark.parametrize("endpoint", [
    "http://" + "a" * 32 + ".r2.cloudflarestorage.com",
    "https://localhost:9000",
    "https://evil.example",
    "https://user:password@" + "a" * 32 + ".r2.cloudflarestorage.com",
    "https://" + "a" * 32 + ".r2.cloudflarestorage.com:443",
    "https://" + "a" * 32 + ".r2.cloudflarestorage.com/another/path",
    "https://" + "a" * 32 + ".r2.cloudflarestorage.com?token=leak",
    "https://" + "a" * 32 + ".r2.cloudflarestorage.com#fragment",
])
def test_rejects_nonstandard_or_unsafe_endpoints(staging, monkeypatch, endpoint):
    monkeypatch.setenv("FORM_S3_ENDPOINT", endpoint)
    monkeypatch.setattr(probe.photo_storage, "save_photo",
                        lambda *_: pytest.fail("storage must not be accessed"))
    with pytest.raises(probe.ProbeRefused):
        probe.run_probe()


def fake_store(monkeypatch):
    objects = {}
    calls = []

    def save(name, payload):
        calls.append(("save", name))
        assert name.startswith("ops-probe-") and name.endswith(".webp")
        objects[name] = payload

    def read(name):
        calls.append(("read", name))
        if name not in objects:
            raise FileNotFoundError
        return objects[name]

    def delete(name):
        calls.append(("delete", name))
        objects.pop(name, None)

    monkeypatch.setattr(probe.photo_storage, "save_photo", save)
    monkeypatch.setattr(probe.photo_storage, "read_photo", read)
    monkeypatch.setattr(probe.photo_storage, "delete_photo", delete)
    return objects, calls


def test_round_trip_and_verified_deletion(staging, monkeypatch):
    objects, calls = fake_store(monkeypatch)
    assert probe.run_probe() is True
    assert objects == {}
    assert [operation for operation, _ in calls] == ["save", "read", "delete", "read"]
    assert len({name for _, name in calls}) == 1


def test_read_failure_still_deletes_exact_probe_object(staging, monkeypatch):
    objects, calls = fake_store(monkeypatch)
    def broken_read(_):
        raise OSError("private-secret-do-not-print")
    monkeypatch.setattr(probe.photo_storage, "read_photo", broken_read)
    assert probe.main(["--run"]) == 1
    assert objects == {}
    assert [operation for operation, _ in calls] == ["save", "delete"]


def test_failed_upload_attempts_cleanup(staging, monkeypatch):
    objects, calls = fake_store(monkeypatch)
    def timeout_after_save(name, payload):
        objects[name] = payload
        calls.append(("save", name))
        raise TimeoutError("private-secret-do-not-print")
    monkeypatch.setattr(probe.photo_storage, "save_photo", timeout_after_save)
    assert probe.main(["--run"]) == 1
    assert objects == {}
    assert [operation for operation, _ in calls] == ["save", "delete"]


def test_mismatched_round_trip_fails_and_cleans_up(staging, monkeypatch):
    objects, calls = fake_store(monkeypatch)
    monkeypatch.setattr(probe.photo_storage, "read_photo", lambda _: b"wrong")
    with pytest.raises(RuntimeError, match="did not match"):
        probe.run_probe()
    assert objects == {}
    assert calls[-1][0] == "delete"


def test_delete_failure_is_not_reported_as_success(staging, monkeypatch, capsys):
    objects, calls = fake_store(monkeypatch)
    def bad_delete(_):
        raise OSError("private-secret-do-not-print")
    monkeypatch.setattr(probe.photo_storage, "delete_photo", bad_delete)
    assert probe.main(["--run"]) == 1
    output = capsys.readouterr().out
    assert "FAILED" in output and "private-secret" not in output
    assert objects  # Manual cleanup may be necessary.


def test_delete_success_but_object_still_visible_fails(staging, monkeypatch):
    objects, calls = fake_store(monkeypatch)
    monkeypatch.setattr(probe.photo_storage, "delete_photo", lambda _: None)
    with pytest.raises(RuntimeError, match="remained readable"):
        probe.run_probe()
    assert objects


def test_missing_explicit_run_does_not_access_storage(staging, monkeypatch):
    monkeypatch.setattr(probe.photo_storage, "save_photo",
                        lambda *_: pytest.fail("storage must not be accessed"))
    assert probe.main([]) == 2
