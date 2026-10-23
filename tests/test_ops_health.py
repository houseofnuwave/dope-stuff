"""Operational diagnostics must be redacted, non-mutating, and actionable."""
from app import db, photo_cleanup
from tools import ops_health


def test_empty_queue_is_healthy_and_read_only(client):
    before = photo_cleanup.status()
    values = ops_health.snapshot(now=2000)
    assert values["deletion_pending"] == 0
    assert values["write_prepared"] == 0
    assert ops_health.evaluate(values)["status"] == "ok"
    assert photo_cleanup.status() == before


def test_failed_and_overdue_deletions_alert_without_exposing_paths(client):
    with db.connect() as connection:
        connection.execute("""INSERT INTO photo_deletions
            (target_key,file_path,created_at,last_attempt_at,attempts,last_error)
            VALUES (?,?,?,?,?,?)""",
            (photo_cleanup.target_key(), "private-object.webp", 100, 101, 3, "storage_unavailable"))
    result = ops_health.evaluate(ops_health.snapshot(now=4000))
    assert result["status"] == "alert"
    assert "deletion_overdue" in result["reason_codes"]
    assert "deletion_retry_failures" in result["reason_codes"]
    assert "private-object" not in str(result)


def test_abandoned_prepared_write_and_foreign_target_alert(client):
    with db.connect() as connection:
        connection.execute("""INSERT INTO photo_write_intents
            (target_key,file_path,operation_id,phase,created_at,next_attempt_at)
            VALUES (?,?,?,?,?,?)""", (photo_cleanup.target_key(), "prepared.webp", "operation", "staging", 1, 901))
        connection.execute("""INSERT INTO photo_deletions (target_key,file_path,created_at)
            VALUES (?,?,?)""", ("old-target", "foreign.webp", 1))
    result = ops_health.evaluate(ops_health.snapshot(now=3000))
    assert "prepared_write_overdue" in result["reason_codes"]
    assert "storage_target_mismatch" in result["reason_codes"]
    assert result["counts"]["deletion_other_storage"] == 1


def test_healthy_indefinite_watches_do_not_create_false_overdue_alert(client):
    with db.connect() as connection:
        connection.execute("""INSERT INTO photo_write_intents
            (target_key,file_path,operation_id,phase,created_at,next_attempt_at,attempts,last_error)
            VALUES (?,?,?,?,?,?,?,?)""",
            (photo_cleanup.target_key(), "unknown.webp", "operation", "cleanup", 1, 10000, 5, ""))
    result = ops_health.evaluate(ops_health.snapshot(now=100000))
    assert result["status"] == "ok"
    assert result["counts"]["write_recovery_watches"] == 1


def test_unavailable_database_fails_closed_without_private_error(monkeypatch, capsys):
    monkeypatch.setattr(ops_health, "snapshot", lambda: (_ for _ in ()).throw(
        RuntimeError("postgresql://private:secret@host/db")))
    assert ops_health.main([]) == 1
    output = capsys.readouterr().out
    assert "secret" not in output
    assert "monitor_unavailable" in output
