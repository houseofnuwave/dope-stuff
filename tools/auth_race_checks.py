"""Deterministic auth race probes for synthetic test accounts only."""
import secrets
import hashlib
import itertools
import threading
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from unittest.mock import patch

_peer_ids = itertools.count(1)


def peer(client):
    from fastapi.testclient import TestClient
    from app import main
    # Reserved documentation addresses isolate these probes' rate-limit buckets.
    # Preserve domain/path so a replacement session actually replaces the old
    # cookie, rather than creating a second domainless cookie in the test jar.
    return TestClient(main.app, cookies=client.cookies,
                      client=(f'192.0.2.{next(_peer_ids) % 254 + 1}', 50000))


def version(client):
    from app import db
    uid = client.get('/api/session').json()['user']['id']
    with db.connect() as connection:
        return connection.execute('SELECT session_version FROM users WHERE id=?', (uid,)).fetchone()[0]


def reset_token(client, email='seller@example.com'):
    from app import main
    sent = []
    with patch.object(main, 'send_recovery_email', side_effect=lambda address, token: sent.append(token)):
        response = client.post('/api/auth/recovery/request', json={'email': email})
    assert response.status_code == 200, response.text
    assert len(sent) == 1
    return sent[0]


@contextmanager
def verified_pause():
    """Pause after the first real password verification, not a fake auth result."""
    from app import main
    entered, release, claim = threading.Event(), threading.Event(), threading.Lock()
    original = main.ph
    held = False

    class Hasher:
        def __getattr__(self, name): return getattr(original, name)
        def verify(self, *args, **kwargs):
            nonlocal held
            result = original.verify(*args, **kwargs)
            with claim:
                pause = not held
                held = True
            if pause:
                entered.set()
                assert release.wait(10), 'Verified-password gate was not released'
            return result

    with patch.object(main, 'ph', Hasher()):
        try:
            yield entered, release
        finally:
            release.set()


def race_after_verified(client, first_call, second_call):
    with peer(client) as other, verified_pause() as (entered, release):
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(first_call, client)
            try:
                assert entered.wait(5)
                second = pool.submit(second_call, other)
                try:
                    second.result(timeout=0.5)
                except TimeoutError:
                    pass
            finally:
                release.set()
            return first.result(timeout=10), second.result(timeout=10), other


def assert_revoked_inflight_write_rejected(client, headers, payload, mutation=None):
    """Reproduces authorization checked before a concurrent password revocation."""
    from app import main

    authorized, release = threading.Event(), threading.Event()
    claim = threading.Lock()
    original = main.begin_owner_write
    held = False
    sku = 'REVOKE-' + secrets.token_hex(6)

    def gate(*args, **kwargs):
        nonlocal held
        with claim:
            pause = not held
            held = True
        if pause:
            authorized.set()
            assert release.wait(10), 'Auth race gate was not released'
        return original(*args, **kwargs)

    # A second event loop models a different app worker, not accidental ASGI
    # serialization caused by a synchronous call in an async route.
    with peer(client) as other, \
            patch.object(main, 'begin_owner_write', side_effect=gate):
        with ThreadPoolExecutor(max_workers=2) as pool:
            write = (pool.submit(mutation, other, headers) if mutation else
                     pool.submit(other.post, '/api/items', headers=headers, json={**payload, 'sku': sku}))
            try:
                if not authorized.wait(5):
                    if write.done():
                        response = write.result()
                        raise AssertionError(f'Probe stopped before its write gate: {response.status_code} {response.text}')
                    raise AssertionError('Write never reached its authorization gate')
                changed = client.post('/api/account/password', headers=headers,
                    json={'current_password': 'longPassword123', 'new_password': 'ReplacedPassword456'})
                assert changed.status_code == 200, changed.text
            finally:
                release.set()
            response = write.result(timeout=10)
            assert response.status_code == 401, 'An already-revoked session committed a mutation'
    assert not client.get('/api/items', params={'q': sku}).json()['items']


def assert_password_changes_serialized(client, headers):
    before = version(client)
    first, second, other = race_after_verified(client,
        lambda c: c.post('/api/account/password', headers=headers, json={
            'current_password': 'longPassword123', 'new_password': 'FirstNewPassword456'}),
        lambda c: c.post('/api/account/password', headers=headers, json={
            'current_password': 'longPassword123', 'new_password': 'SecondNewPassword456'}))
    assert first.status_code == 200, first.text
    assert second.status_code == 401, 'Two concurrent changes accepted the same old credential/session'
    assert version(client) == before + 1
    # Do not use the closed peer transport; inspect its stale cookie in a new client.
    with peer(other) as stale:
        assert stale.get('/api/session').json()['authenticated'] is False


def assert_password_change_revokes_waiting_reset(client, headers, email='seller@example.com'):
    token = reset_token(client, email)
    before = version(client)
    first, second, _ = race_after_verified(client,
        lambda c: c.post('/api/account/password', headers=headers, json={
            'current_password': 'longPassword123', 'new_password': 'ChangedBeforeReset456'}),
        lambda c: c.post('/api/auth/recovery/confirm', json={
            'token': token, 'new_password': 'MustNotWinReset456'}))
    assert first.status_code == 200, first.text
    assert second.status_code == 400, 'Reset token survived a completed password change'
    assert version(client) == before + 1


def assert_login_then_change_revokes_login_cookie(client, headers, email='seller@example.com'):
    before = version(client)
    first, second, other = race_after_verified(client,
        lambda c: c.post('/api/auth/login', json={'email': email, 'password': 'longPassword123'}),
        lambda c: c.post('/api/account/password', headers=headers, json={
            'current_password': 'longPassword123', 'new_password': 'ChangedDuringLogin456'}))
    assert first.status_code == 200 and second.status_code == 200
    assert not client.get('/api/session').json()['authenticated']
    with peer(other) as current:
        assert version(current) == before + 1


def assert_deletion_revokes_waiting_reset(client, headers, email='seller@example.com'):
    """Deliberately deletes ONLY the supplied synthetic test account."""
    token = reset_token(client, email)
    first, second, _ = race_after_verified(client,
        lambda c: c.post('/api/account/delete', headers=headers, json={
            'password': 'longPassword123', 'confirmation': 'DELETE MY ACCOUNT'}),
        lambda c: c.post('/api/auth/recovery/confirm', json={
            'token': token, 'new_password': 'DeletedOwnerReset456'}))
    assert first.status_code == 200, first.text
    assert second.status_code == 400, second.text
    assert not client.get('/api/session').json()['authenticated']


def assert_one_reset_winner(client, email='seller@example.com'):
    token = reset_token(client, email)
    before = version(client)
    start = threading.Barrier(2)

    def confirm(other):
        start.wait(timeout=5)
        return other.post('/api/auth/recovery/confirm', json={
            'token': token, 'new_password': 'ConcurrentResetPassword456'})

    with peer(client) as other:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = [pool.submit(confirm, c) for c in (client, other)]
            assert sorted(result.result(timeout=10).status_code for result in responses) == [200, 400]
        assert not other.get('/api/session').json()['authenticated']
    assert not client.get('/api/session').json()['authenticated']
    from app import db
    with db.connect() as connection:
        row = connection.execute('SELECT session_version FROM users WHERE email=?', (email,)).fetchone()
        assert row[0] == before + 1
        assert not connection.execute('SELECT 1 FROM password_resets WHERE token_hash=?',
                                      (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()


def assert_recovery_during_account_deletion_is_generic(client, headers, email='seller@example.com'):
    """Deliberately deletes ONLY the supplied synthetic test account."""
    from app import main
    sent = []
    with patch.object(main, 'send_recovery_email', side_effect=lambda *args: sent.append(args)):
        first, second, _ = race_after_verified(client,
            lambda c: c.post('/api/account/delete', headers=headers, json={
                'password': 'longPassword123', 'confirmation': 'DELETE MY ACCOUNT'}),
            lambda c: c.post('/api/auth/recovery/request', json={'email': email}))
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert not sent, 'A recovery token was issued after owner deletion'
    generic = client.post('/api/auth/recovery/request', json={'email': 'never-existed@example.com'})
    assert generic.status_code == 200 and second.json() == generic.json()


def assert_concurrent_requests_leave_one_reset(client, email='seller@example.com'):
    from app import main, db
    entered, release, claim = threading.Event(), threading.Event(), threading.Lock()
    original = main.connect
    held = False
    sent = []

    class Gate:
        def __init__(self, connection): self.connection = connection
        def execute(self, query, params=()):
            nonlocal held
            result = self.connection.execute(query, params)
            if query.startswith('DELETE FROM password_resets WHERE user_id='):
                with claim:
                    pause = not held
                    held = True
                if pause:
                    entered.set()
                    assert release.wait(10), 'Issuance gate was not released'
            return result

    @contextmanager
    def connection():
        with original() as raw:
            yield Gate(raw)

    with peer(client) as other, patch.object(main, 'connect', connection), \
            patch.object(main, 'send_recovery_email', side_effect=lambda address, token: sent.append(token)):
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(client.post, '/api/auth/recovery/request', json={'email': email})
            try:
                assert entered.wait(5)
                second = pool.submit(other.post, '/api/auth/recovery/request', json={'email': email})
                try:
                    second.result(timeout=0.5)
                except TimeoutError:
                    pass
            finally:
                release.set()
            assert first.result(timeout=10).status_code == 200
            assert second.result(timeout=10).status_code == 200
    with db.connect() as connection:
        rows = connection.execute('''SELECT token_hash FROM password_resets
            WHERE user_id=(SELECT id FROM users WHERE email=?)''', (email,)).fetchall()
    assert len(sent) == 2 and len(rows) == 1, 'Concurrent issuance left multiple active links'
    live = rows[0]['token_hash']
    superseded = next(token for token in sent if hashlib.sha256(token.encode()).hexdigest() != live)
    rejected = client.post('/api/auth/recovery/confirm', json={
        'token': superseded, 'new_password': 'MustNotUseOldToken456'})
    assert rejected.status_code == 400


def run_cloud_auth_checks(payload):
    """Disposable CI only: create isolated synthetic principals for each probe."""
    import os
    from fastapi.testclient import TestClient
    from app.main import app
    probes = [
        lambda c, h, email: assert_revoked_inflight_write_rejected(c, h, payload),
        lambda c, h, email: assert_password_changes_serialized(c, h),
        lambda c, h, email: assert_password_change_revokes_waiting_reset(c, h, email),
        lambda c, h, email: assert_one_reset_winner(c, email),
        lambda c, h, email: assert_concurrent_requests_leave_one_reset(c, email),
        lambda c, h, email: assert_recovery_during_account_deletion_is_generic(c, h, email),
        lambda c, h, email: assert_login_then_change_revokes_login_cookie(c, h, email),
        lambda c, h, email: assert_deletion_revokes_waiting_reset(c, h, email),
    ]
    for index, probe in enumerate(probes):
        email = f'ci-auth-race-{index}@example.com'
        with TestClient(app, client=(f'198.51.100.{index + 1}', 50000)) as client:
            registered = client.post('/api/auth/register', json={
                'name': 'Synthetic auth fixture', 'email': email, 'password': 'longPassword123',
                'invite_code': os.getenv('FORM_PILOT_INVITE_CODE', '')})
            assert registered.status_code == 200, registered.text
            headers = {'x-csrf-token': client.get('/api/session').json()['csrf']}
            probe(client, headers, email)

