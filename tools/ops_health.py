"""Read-only, redacted diagnostics for durable private-photo cleanup work.

Exit 0: within thresholds. Exit 2: actionable alert. Exit 1: unavailable.
Safe to run from a scheduled monitor without printing filenames or credentials.
Never automatically discard uncertain-write watches.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from app import db, photo_cleanup


def nonnegative(value):
    try:
        number = int(value)
        if number < 0:
            raise ValueError()
        return number
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Must be a nonnegative integer") from exc


def snapshot(*, now=None):
    """Only aggregate data crosses the database boundary; no private object names."""
    if not db.postgres_enabled() and not db.DB_PATH.is_file():
        raise RuntimeError("database unavailable")
    now = int(time.time() if now is None else now)
    key = photo_cleanup.target_key()
    with db.connect() as connection:
        connection.execute("BEGIN")
        try:
            deletions = connection.execute("""
                SELECT COUNT(*) AS total,
                    COALESCE(SUM(CASE WHEN target_key=? THEN 1 ELSE 0 END),0) AS current_count,
                    COALESCE(SUM(CASE WHEN target_key=? AND attempts>0 THEN 1 ELSE 0 END),0) AS failed_count,
                    MIN(CASE WHEN target_key=? THEN created_at ELSE NULL END) AS oldest_created
                FROM photo_deletions
                """, (key, key, key)).fetchone()
            writes = connection.execute("""
                SELECT COUNT(*) AS total,
                    COALESCE(SUM(CASE WHEN target_key=? AND phase='staging' THEN 1 ELSE 0 END),0) AS staging_count,
                    COALESCE(SUM(CASE WHEN target_key=? AND phase='cleanup' THEN 1 ELSE 0 END),0) AS watch_count,
                    COALESCE(SUM(CASE WHEN target_key=? AND last_error<>'' THEN 1 ELSE 0 END),0) AS failed_count,
                    MIN(CASE WHEN target_key=? AND phase='staging' THEN created_at ELSE NULL END) AS oldest_staging,
                    MIN(CASE WHEN target_key=? AND phase='cleanup' THEN created_at ELSE NULL END) AS oldest_watch,
                    COALESCE(SUM(CASE WHEN target_key<>? THEN 1 ELSE 0 END),0) AS other_count
                FROM photo_write_intents
                """, (key, key, key, key, key, key)).fetchone()
        finally:
            connection.execute("ROLLBACK")

    def age(created):
        return max(0, now - int(created)) if created is not None else 0

    return {
        "deletion_pending": int(deletions["current_count"]),
        "deletion_retry_failures": int(deletions["failed_count"]),
        "deletion_oldest_seconds": age(deletions["oldest_created"]),
        "deletion_other_storage": int(deletions["total"]) - int(deletions["current_count"]),
        "write_prepared": int(writes["staging_count"]),
        "write_prepared_oldest_seconds": age(writes["oldest_staging"]),
        "write_recovery_watches": int(writes["watch_count"]),
        "write_recovery_oldest_seconds": age(writes["oldest_watch"]),
        "write_recovery_failures": int(writes["failed_count"]),
        "write_other_storage": int(writes["other_count"]),
    }


def evaluate(values, *, max_pending=100, max_delete_age_seconds=3600,
             max_delete_failures=0, max_staging_age_seconds=1800, max_write_failures=0):
    reasons = []
    if values["deletion_pending"] > max_pending:
        reasons.append("deletion_backlog")
    if values["deletion_pending"] and values["deletion_oldest_seconds"] > max_delete_age_seconds:
        reasons.append("deletion_overdue")
    if values["deletion_retry_failures"] > max_delete_failures:
        reasons.append("deletion_retry_failures")
    if values["write_prepared"] and values["write_prepared_oldest_seconds"] > max_staging_age_seconds:
        reasons.append("prepared_write_overdue")
    if values["write_recovery_failures"] > max_write_failures:
        reasons.append("write_recovery_failures")
    if values["deletion_other_storage"] or values["write_other_storage"]:
        reasons.append("storage_target_mismatch")
    # Watches are intentionally indefinite; age/count alone must NOT cause
    # deletion, pruning, or an incident-level alarm.
    return {"status": "alert" if reasons else "ok", "reason_codes": reasons, "counts": values}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-pending", type=nonnegative, default=100)
    parser.add_argument("--max-delete-age-seconds", type=nonnegative, default=3600)
    parser.add_argument("--max-delete-failures", type=nonnegative, default=0)
    parser.add_argument("--max-staging-age-seconds", type=nonnegative, default=1800)
    parser.add_argument("--max-write-failures", type=nonnegative, default=0)
    args = parser.parse_args(argv)
    try:
        result = evaluate(snapshot(), **vars(args))
    except Exception:
        # DB exceptions may contain connection strings or private object names.
        print(json.dumps({"status": "unavailable", "reason_codes": ["monitor_unavailable"]}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 2 if result["status"] == "alert" else 0


if __name__ == "__main__":
    sys.exit(main())
