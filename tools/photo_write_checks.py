"""Fault-injection checks for isolated synthetic accounts, never operator tools."""
import io
from contextlib import contextmanager
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from unittest.mock import patch

from PIL import Image


def image():
    output = io.BytesIO()
    Image.new('RGB', (24, 24), 'blue').save(output, 'PNG')
    return output.getvalue()


def new_item(client, headers, payload):
    response = client.post('/api/items', headers=headers,
                           json={**payload, 'sku': 'WRITE-' + secrets.token_hex(6)})
    assert response.status_code == 201, response.text
    return response.json()['id']


def assert_unknown_write_recovery(client, headers, payload):
    from app import db, photo_storage, photo_writes
    item_id = new_item(client, headers, payload)
    saved = []
    original = photo_storage.save_photo

    def timeout(name, raw):
        original(name, raw)
        saved.append((name, raw))
        raise OSError('synthetic private provider error')

    with patch.object(photo_storage, 'save_photo', side_effect=timeout):
        response = client.post(f'/api/items/{item_id}/photos', headers=headers,
                               files={'photos': ('test.png', image(), 'image/png')})
    assert response.status_code == 503, response.text
    assert 'private provider' not in response.text
    assert client.get(f'/api/items/{item_id}').json()['photo_count'] == 0
    name, raw = saved[0]
    with db.connect() as connection:
        row = connection.execute('SELECT phase FROM photo_write_intents WHERE file_path=?', (name,)).fetchone()
        assert row and row['phase'] == 'cleanup'
    try:
        photo_storage.read_photo(name)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError('Initial recovery did not delete unregistered write')
    # Emulate an accepted write becoming visible AFTER cleanup succeeded.
    original(name, raw)
    assert photo_writes.reconcile(names=[name], now=int(time.time()) + 120)['deleted'] == 1
    try:
        photo_storage.read_photo(name)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError('Late unacknowledged write escaped its recovery watch')
    with db.connect() as connection:
        assert connection.execute('SELECT 1 FROM photo_write_intents WHERE file_path=?', (name,)).fetchone()


def assert_active_write_protected(client, headers, payload):
    from app import photo_storage, photo_writes
    item_id = new_item(client, headers, payload)
    accepted, release = threading.Event(), threading.Event()
    original = photo_storage.save_photo
    names = []

    def held_write(name, raw):
        original(name, raw)
        names.append(name)
        accepted.set()
        assert release.wait(10), 'Upload test gate was not released'

    with patch.object(photo_storage, 'save_photo', side_effect=held_write):
        with ThreadPoolExecutor(max_workers=2) as pool:
            upload = pool.submit(client.post, f'/api/items/{item_id}/photos', headers=headers,
                                 files={'photos': ('test.png', image(), 'image/png')})
            try:
                assert accepted.wait(5), 'Upload never reached storage'
                recovery = pool.submit(photo_writes.reconcile, names=names,
                                       now=int(time.time()) + photo_writes.GRACE_SECONDS + 60)
                try:
                    # PostgreSQL skips the locked intent; SQLite waits for its
                    # writer. Neither may delete it while registration is live.
                    assert recovery.result(timeout=0.5)['deleted'] == 0
                except TimeoutError:
                    pass
            finally:
                release.set()
            assert upload.result(timeout=10).status_code == 200
            assert recovery.result(timeout=10)['deleted'] == 0
    response = client.get(f'/api/items/{item_id}/photo')
    assert response.status_code == 200 and response.content[:4] == b'RIFF'


def assert_commit_acknowledgement_safe(client, headers, payload):
    from app import main, photo_writes
    item_id = new_item(client, headers, payload)
    original = main.connect

    class LostCommitAck:
        def __init__(self, connection): self.connection = connection
        def execute(self, query, params=()):
            result = self.connection.execute(query, params)
            if query == 'COMMIT':
                raise RuntimeError('synthetic commit response lost')
            return result

    @contextmanager
    def ambiguous_connection():
        with original() as connection:
            yield LostCommitAck(connection)

    with patch.object(main, 'connect', ambiguous_connection):
        try:
            client.post(f'/api/items/{item_id}/photos', headers=headers,
                        files={'photos': ('test.png', image(), 'image/png')})
        except RuntimeError as error:
            assert str(error) == 'synthetic commit response lost'
        else:
            raise AssertionError('Commit acknowledgement fault was not injected')
    assert client.get(f'/api/items/{item_id}').json()['photo_count'] == 1
    assert client.get(f'/api/items/{item_id}/photo').status_code == 200
    assert photo_writes.status()['write_prepared'] == 0
    return item_id


def assert_upload_account_delete_serialized(client, headers, payload, password):
    """Destroys ONLY this supplied synthetic account; caller must opt in."""
    from app import db, photo_storage, photo_cleanup, photo_writes
    from app.main import app
    from fastapi.testclient import TestClient
    item_id = new_item(client, headers, payload)
    accepted, release, deletion_started = threading.Event(), threading.Event(), threading.Event()
    original = photo_storage.save_photo
    names = []

    def held_write(name, raw):
        original(name, raw)
        names.append(name)
        accepted.set()
        assert release.wait(10), 'Account race gate was not released'

    def delete_account(other):
        deletion_started.set()
        return other.post('/api/account/delete', headers=headers,
                           json={'password': password, 'confirmation': 'DELETE MY ACCOUNT'})

    # Separate ASGI event loops model different app workers. A synchronous
    # provider call in the upload route must not itself serialize this test.
    with TestClient(app, cookies=dict(client.cookies)) as other, patch.object(photo_storage, 'save_photo', side_effect=held_write):
        with ThreadPoolExecutor(max_workers=2) as pool:
            upload = pool.submit(client.post, f'/api/items/{item_id}/photos', headers=headers,
                                 files={'photos': ('test.png', image(), 'image/png')})
            try:
                assert accepted.wait(5)
                deletion = pool.submit(delete_account, other)
                assert deletion_started.wait(5)
                try:
                    deletion.result(timeout=0.5)
                    raise AssertionError('Account deletion passed an active photo registration')
                except TimeoutError:
                    pass
            finally:
                release.set()
            assert upload.result(timeout=10).status_code == 200
            assert deletion.result(timeout=10).status_code == 200
    assert photo_cleanup.pending(names)==0
    assert photo_writes.reconcile(names=names, now=int(time.time()) + 2000)['deleted'] == 0
    with db.connect() as connection:
        assert connection.execute('SELECT COUNT(*) FROM items WHERE id=?', (item_id,)).fetchone()[0] == 0
    for name in names:
        try:
            photo_storage.read_photo(name)
        except FileNotFoundError:
            pass
        else:
            raise AssertionError('Account deletion missed the concurrently accepted photo')


def assert_double_restore_serialized(client, auth, payload):
    """Delete/recreate ONLY this synthetic account; preserve it after the probe."""
    from app import main, photo_storage, photo_writes
    from fastapi.testclient import TestClient
    headers = {'x-csrf-token': client.get('/api/session').json()['csrf']}
    item_id = new_item(client, headers, payload)
    uploaded = client.post(f'/api/items/{item_id}/photos', headers=headers,
                           files={'photos': ('test.png', image(), 'image/png')})
    assert uploaded.status_code == 200, uploaded.text
    backup = client.get('/api/account/export.zip')
    assert backup.status_code == 200, backup.text
    response = client.post('/api/account/delete', headers=headers,
        json={'password': auth['password'], 'confirmation': 'DELETE MY ACCOUNT'})
    assert response.status_code == 200, response.text
    response = client.post('/api/auth/register', json=auth)
    assert response.status_code == 200, response.text
    headers = {'x-csrf-token': client.get('/api/session').json()['csrf']}
    inserted, release, second_started = threading.Event(), threading.Event(), threading.Event()
    original_create = main.create_item
    original_save = photo_storage.save_photo
    saved = []

    def held_create(*args, **kwargs):
        result = original_create(*args, **kwargs)
        inserted.set()
        assert release.wait(10), 'Restore gate was not released'
        return result

    def record_save(name, raw):
        saved.append(name)
        return original_save(name, raw)

    def restore(other, second=False):
        if second:
            second_started.set()
        return other.post('/api/account/restore', headers=headers,
            data={'password': auth['password'], 'confirmation': 'RESTORE MY DATA'},
            files={'file': ('backup.zip', backup.content, 'application/zip')})

    with TestClient(main.app, cookies=dict(client.cookies)) as other, \
            patch.object(main, 'create_item', side_effect=held_create), \
            patch.object(photo_storage, 'save_photo', side_effect=record_save):
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(restore, client)
            try:
                assert inserted.wait(5)
                second = pool.submit(restore, other, True)
                assert second_started.wait(5)
                try:
                    response = second.result(timeout=0.5)
                    assert response.status_code == 409, response.text
                except TimeoutError:
                    pass
            finally:
                release.set()
            assert first.result(timeout=10).status_code == 200
            assert second.result(timeout=10).status_code == 409
    assert len(saved) == 1, 'Conflicting restore wrote private photos before checking the blank account'
    assert client.get('/api/items').json()['total'] == 1
    assert photo_writes.status()['write_prepared'] == 0
