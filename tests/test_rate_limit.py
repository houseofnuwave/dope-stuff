"""Bounded, thread-safe regression tests for process-local pilot throttling."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import main


@pytest.fixture(autouse=True)
def clear_rate_limit_state():
    with main.failed_attempts_lock:
        main.failed_attempts.clear()
    yield
    with main.failed_attempts_lock:
        main.failed_attempts.clear()


def request_for(host: str):
    return SimpleNamespace(client=SimpleNamespace(host=host))


def test_limiter_prunes_expired_buckets_and_retains_recent_activity(monkeypatch):
    monkeypatch.setattr(main, "time", SimpleNamespace(monotonic=lambda: 1000.0))
    with main.failed_attempts_lock:
        main.failed_attempts["login:expired"] = [50.0]
        main.failed_attempts["login:recent"] = [950.0]

    main.limiter(request_for("203.0.113.8"), "register", max_requests=8)

    assert "login:expired" not in main.failed_attempts
    assert main.failed_attempts["login:recent"] == [950.0]
    assert "register:203.0.113.8" in main.failed_attempts


def test_limiter_caps_distinct_client_buckets(monkeypatch):
    monkeypatch.setattr(main, "time", SimpleNamespace(monotonic=lambda: 1000.0))
    monkeypatch.setattr(main, "RATE_LIMIT_BUCKET_LIMIT", 2)
    with main.failed_attempts_lock:
        main.failed_attempts["login:first"] = [999.0]
        main.failed_attempts["login:second"] = [999.0]

    main.limiter(request_for("203.0.113.9"), "login", max_requests=5)

    assert len(main.failed_attempts) == 2
    assert "login:first" not in main.failed_attempts
    assert "login:second" in main.failed_attempts
    assert "login:203.0.113.9" in main.failed_attempts


def test_limiter_serializes_concurrent_attempts_for_one_client():
    request = request_for("198.51.100.42")

    def attempt(_):
        try:
            main.limiter(request, "login", max_requests=5)
            return "allowed"
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(attempt, range(24)))

    assert results.count("allowed") == 5
    assert results.count(429) == 19
    assert len(main.failed_attempts["login:198.51.100.42"]) == 5
