"""Unacknowledged writes must be tracked before touching private storage."""
import io
import os
import subprocess
import sys
import time
from contextlib import contextmanager

import pytest
from PIL import Image

from app import db, main, photo_storage, photo_writes
from tools.photo_write_checks import (assert_unknown_write_recovery, assert_active_write_protected,
                                      assert_upload_account_delete_serialized, assert_double_restore_serialized)


def photo():
    output = io.BytesIO()
    Image.new('RGB', (24, 24), 'blue').save(output, 'PNG')
    return output.getvalue()


def test_accepted_write_followed_by_timeout_is_recoverable(seller, item_input, monkeypatch, tmp_path):
    client = seller['client']; headers = seller['csrf']
    item = client.post('/api/items', headers=headers, json=item_input).json()
    original = photo_storage.save_photo
    written = []

    def accepted_then_timeout(name, payload):
        original(name, payload)
        written.append((name, payload))
        raise OSError('private-provider.example/secret-key')

    monkeypatch.setattr(photo_storage, 'save_photo', accepted_then_timeout)
    response = client.post(f"/api/items/{item['id']}/photos", headers=headers,
                           files={'photos': ('sample.png', photo(), 'image/png')})
    assert response.status_code == 503, response.text
    assert 'private-provider' not in response.text and 'secret-key' not in response.text
    assert client.get(f"/api/items/{item['id']}").json()['photo_count'] == 0
    from app import photo_writes
    assert photo_writes.status()['write_recovery_watch'] == 1
    assert not list((tmp_path / 'photos').glob('*.webp'))
    # A provider can make a timed-out write visible even after the first delete.
    name, payload = written[0]
    original(name, payload)
    recovered = photo_writes.reconcile(now=int(time.time()) + 120)
    assert recovered['deleted'] == 1
    assert not list((tmp_path / 'photos').glob('*.webp'))
    assert photo_writes.status()['write_recovery_watch'] == 1


def test_storage_delete_outage_does_not_lose_unknown_write_work(seller, item_input, monkeypatch, tmp_path):
    client = seller['client']; headers = seller['csrf']
    item = client.post('/api/items', headers=headers, json=item_input).json()
    original_save = photo_storage.save_photo

    def accepted_then_timeout(name, payload):
        original_save(name, payload)
        raise OSError('simulated timeout')

    def unavailable(name):
        raise OSError('storage down')

    with monkeypatch.context() as outage:
        outage.setattr(photo_storage, 'save_photo', accepted_then_timeout)
        outage.setattr(photo_storage, 'delete_photo', unavailable)
        response = client.post(f"/api/items/{item['id']}/photos", headers=headers,
                               files={'photos': ('sample.png', photo(), 'image/png')})
        assert response.status_code == 503
    from app import photo_writes
    assert len(list((tmp_path / 'photos').glob('*.webp'))) == 1
    assert photo_writes.status()['write_recovery_watch'] == 1
    assert photo_writes.reconcile(now=int(time.time()) + 120)['deleted'] == 1
    assert not list((tmp_path / 'photos').glob('*.webp'))


def test_reusable_late_write_probe(seller, item_input):
    assert_unknown_write_recovery(seller['client'], seller['csrf'], item_input)


def test_recovery_cannot_delete_active_upload_even_after_grace(seller, item_input):
    assert_active_write_protected(seller['client'], seller['csrf'], item_input)


def test_delete_account_sees_concurrent_upload(seller, item_input):
    assert_upload_account_delete_serialized(seller['client'], seller['csrf'], item_input, 'longPassword123')


def test_double_restore_does_not_stage_conflicting_photos(seller, item_input):
    assert_double_restore_serialized(seller['client'],
        {'name': 'Synthetic Seller', 'email': 'seller@example.com', 'password': 'longPassword123'}, item_input)


def test_successful_upload_has_no_remaining_intent(seller, item_input):
    client = seller['client']; headers = seller['csrf']
    item = client.post('/api/items', headers=headers, json=item_input).json()
    response = client.post(f"/api/items/{item['id']}/photos", headers=headers,
                           files={'photos': ('sample.png', photo(), 'image/png')})
    assert response.status_code == 200
    assert photo_writes.status() == {'write_prepared': 0, 'write_recovery_watch': 0,
                                     'write_recovery_failed': 0, 'write_other_storage': 0}
    assert client.get(f"/api/items/{item['id']}/photo").status_code == 200


def test_unattempted_names_do_not_become_watches(client):
    op = photo_writes.prepare(['untouched.webp'])
    photo_writes.abort(op)
    assert photo_writes.status()['write_prepared'] == 0
    assert photo_writes.status()['write_recovery_watch'] == 0


def test_writes_and_finish_require_locked_complete_operation(client):
    op = photo_writes.prepare(['not-locked.webp'])
    with pytest.raises(ValueError):
        photo_writes.write(op, 'not-locked.webp', b'not allowed')
    with db.connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        photo_writes.lock_operation(connection, op)
        with pytest.raises(RuntimeError, match='incomplete'):
            photo_writes.finish(connection, op)
    photo_writes.abort(op)
    assert photo_writes.status()['write_prepared'] == 0


def test_compensation_database_outage_keeps_original_durable_intent(client, monkeypatch, tmp_path):
    op = photo_writes.prepare(['interrupted-compensation.webp'])
    with db.connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        photo_writes.lock_operation(connection, op)
        photo_writes.write(op, op.names[0], b'synthetic interrupted fixture')
        # Closing without commit rolls back metadata, not the earlier intent.

    @contextmanager
    def unavailable():
        raise OSError('private database endpoint secret')
        yield  # pragma: no cover -- context-manager protocol

    with monkeypatch.context() as failure:
        failure.setattr(db, 'connect', unavailable)
        photo_writes.abort(op)  # Must not replace the caller's original error.
    assert photo_writes.status()['write_prepared'] == 1
    assert (tmp_path / 'photos' / op.names[0]).exists()
    assert photo_writes.reconcile(now=int(time.time()) + 2000)['deleted'] == 1
    assert photo_writes.status()['write_recovery_watch'] == 1


def test_watch_errors_are_sanitized_and_repeated_without_dropping_work(client, monkeypatch):
    op = photo_writes.prepare(['outage-watch.webp'])

    def unavailable(name):
        raise OSError('https://private-provider.example/key?credential=secret')

    now = int(time.time()) + 2000
    with monkeypatch.context() as failure:
        failure.setattr(photo_storage, 'delete_photo', unavailable)
        assert photo_writes.reconcile(now=now)['failed'] == 1
        # Backoff prevents repeatedly hammering an unavailable provider.
        assert photo_writes.reconcile(now=now)['checked'] == 0
    with db.connect() as connection:
        row = connection.execute('SELECT attempts,last_error FROM photo_write_intents').fetchone()
        assert row['attempts'] == 1 and row['last_error'] == 'storage_unavailable'
    assert photo_writes.status()['write_recovery_failed'] == 1
    assert photo_writes.reconcile(now=now + 120)['deleted'] == 1
    assert photo_writes.status()['write_recovery_failed'] == 0
    assert photo_writes.status()['write_recovery_watch'] == 1


def test_before_acceptance_failure_is_still_watched(seller, item_input, monkeypatch):
    client = seller['client']; headers = seller['csrf']
    item = client.post('/api/items', headers=headers, json=item_input).json()

    def unavailable(name, payload):
        raise OSError('synthetic outage')

    monkeypatch.setattr(photo_storage, 'save_photo', unavailable)
    response = client.post(f"/api/items/{item['id']}/photos", headers=headers,
        files=[('photos', ('one.png', photo(), 'image/png')), ('photos', ('two.png', photo(), 'image/png'))])
    assert response.status_code == 503
    assert photo_writes.status()['write_recovery_watch'] == 1
    assert photo_writes.status()['write_prepared'] == 0


def test_partial_batch_cleans_acknowledged_and_watches_unknown(seller, item_input, monkeypatch, tmp_path):
    client = seller['client']; headers = seller['csrf']
    item = client.post('/api/items', headers=headers, json=item_input).json()
    original = photo_storage.save_photo
    calls = []

    def fail_second(name, raw):
        original(name, raw)
        calls.append(name)
        if len(calls) == 2:
            raise OSError('acknowledgement lost')

    monkeypatch.setattr(photo_storage, 'save_photo', fail_second)
    response = client.post(f"/api/items/{item['id']}/photos", headers=headers,
        files=[('photos', (f'{i}.png', photo(), 'image/png')) for i in range(3)])
    assert response.status_code == 503
    assert len(calls) == 2
    assert photo_writes.status()['write_recovery_watch'] == 1
    assert photo_writes.status()['write_prepared'] == 0
    assert not list((tmp_path / 'photos').glob('*.webp'))
    assert client.get(f"/api/items/{item['id']}").json()['photo_count'] == 0


def test_metadata_rollback_queues_known_writes_without_masking_error(seller, item_input, monkeypatch, tmp_path):
    from app import photo_cleanup
    client = seller['client']; headers = seller['csrf']
    item = client.post('/api/items', headers=headers, json=item_input).json()

    def database_failure(*args):
        raise RuntimeError('original metadata error')

    def unavailable(name):
        raise OSError('private storage unavailable')

    with monkeypatch.context() as failure:
        failure.setattr(main, 'serialize_item', database_failure)
        failure.setattr(photo_storage, 'delete_photo', unavailable)
        with pytest.raises(RuntimeError, match='original metadata error'):
            client.post(f"/api/items/{item['id']}/photos", headers=headers,
                        files={'photos': ('sample.png', photo(), 'image/png')})
    assert photo_cleanup.pending() == 1
    assert photo_writes.status()['write_prepared'] == 0
    assert len(list((tmp_path / 'photos').glob('*.webp'))) == 1
    assert client.get(f"/api/items/{item['id']}").json()['photo_count'] == 0
    assert photo_cleanup.process_pending() == {'completed': 1, 'pending': 0}


def test_commit_acknowledgement_loss_never_deletes_registered_photo(seller, item_input, tmp_path):
    from tools.photo_write_checks import assert_commit_acknowledgement_safe
    from app import photo_cleanup
    item_id = assert_commit_acknowledgement_safe(seller['client'], seller['csrf'], item_input)
    assert len(list((tmp_path / 'photos').glob('*.webp'))) == 1
    assert photo_cleanup.pending() == 0
    assert photo_writes.reconcile(now=int(time.time()) + 2000)['deleted'] == 0
    assert seller['client'].get(f'/api/items/{item_id}/photo').status_code == 200


def test_expired_intent_cannot_resume_a_write(client):
    op = photo_writes.prepare(['expired.webp'])
    assert photo_writes.reconcile(now=int(time.time()) + photo_writes.GRACE_SECONDS + 1)['deleted'] == 1
    with db.connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        with pytest.raises(main.HTTPException) as error:
            photo_writes.lock_operation(connection, op)
        assert error.value.status_code == 409
    # A caller aborting after retirement must not discard the worker's watch.
    photo_writes.abort(op)
    assert photo_writes.status()['write_recovery_watch'] == 1


@pytest.mark.parametrize('cover_only', [False, True])
def test_live_references_always_win_over_stale_intent(seller, item_input, cover_only):
    client = seller['client']; headers = seller['csrf']
    item = client.post('/api/items', headers=headers, json=item_input).json()
    op = photo_writes.prepare(['protected.webp'])
    photo_storage.save_photo('protected.webp', main.encode_photo(photo()))
    with db.connect() as connection:
        if cover_only:
            connection.execute('UPDATE items SET photo_path=? WHERE id=?', ('protected.webp', item['id']))
        else:
            connection.execute('INSERT INTO item_photos(item_id,file_path,position) VALUES (?,?,0)',
                               (item['id'], 'protected.webp'))
    result = photo_writes.reconcile(now=int(time.time()) + 2000)
    assert result == {'checked': 1, 'protected': 1, 'deleted': 0, 'failed': 0}
    assert photo_storage.read_photo('protected.webp')[:4] == b'RIFF'
    assert photo_writes.status()['write_prepared'] == 0


def test_storage_target_change_does_not_redirect_recovery(client, monkeypatch, tmp_path):
    photo_writes.prepare(['old-target.webp'])
    monkeypatch.setattr(db, 'DATA_DIR', tmp_path / 'different')
    assert photo_writes.reconcile(now=int(time.time()) + 2000)['checked'] == 0
    assert photo_writes.status()['write_other_storage'] == 1


def test_process_crash_keeps_intent_before_metadata_registration(client, tmp_path):
    # A real interpreter exits without unwinding the transaction/context manager.
    script = '''
import os
from app import db, photo_storage, photo_writes
db.DB_PATH = db.DATA_DIR / 'test.db'
op = photo_writes.prepare(['crashed.webp'])
with db.connect() as connection:
    connection.execute('BEGIN IMMEDIATE')
    photo_writes.lock_operation(connection, op)
    photo_writes.write(op, 'crashed.webp', b'synthetic crash fixture')
    os._exit(73)
'''
    env = {**os.environ, 'FORM_DATA_DIR': str(tmp_path), 'FORM_PHOTO_STORAGE': 'local'}
    result = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True, timeout=10)
    assert result.returncode == 73, result.stderr.decode()
    assert photo_writes.status()['write_prepared'] == 1
    assert (tmp_path / 'photos' / 'crashed.webp').exists()
    assert photo_writes.reconcile(now=int(time.time()) + 2000)['deleted'] == 1
    assert not (tmp_path / 'photos' / 'crashed.webp').exists()
    assert photo_writes.status()['write_recovery_watch'] == 1


@pytest.mark.parametrize('failure_query', ['INSERT INTO photo_write_intents', 'COMMIT'])
def test_intent_persistence_failure_blocks_all_storage_writes(seller, item_input, monkeypatch, failure_query):
    client = seller['client']; headers = seller['csrf']
    item = client.post('/api/items', headers=headers, json=item_input).json()
    original = db.connect
    storage_calls = []

    class FailedPersistence:
        def __init__(self, connection): self.connection = connection
        def execute(self, query, params=()):
            if query.startswith(failure_query):
                raise RuntimeError('intent persistence unavailable')
            return self.connection.execute(query, params)

    @contextmanager
    def failed_connection():
        with original() as connection:
            yield FailedPersistence(connection)

    with monkeypatch.context() as failure:
        failure.setattr(db, 'connect', failed_connection)
        failure.setattr(photo_storage, 'save_photo', lambda *args: storage_calls.append(args))
        with pytest.raises(RuntimeError, match='intent persistence unavailable'):
            client.post(f"/api/items/{item['id']}/photos", headers=headers,
                        files={'photos': ('sample.png', photo(), 'image/png')})
    assert not storage_calls
    assert photo_writes.status()['write_prepared'] == 0


@pytest.mark.parametrize('storage_failure', ['timeout', 'metadata_and_delete'])
def test_restore_staging_failures_are_durably_recoverable(seller, item_input, monkeypatch, tmp_path, storage_failure):
    from test_v04 import restore, register
    from app import photo_cleanup
    client = seller['client']; headers = seller['csrf']
    item = client.post('/api/items', headers=headers, json=item_input).json()
    assert client.post(f"/api/items/{item['id']}/photos", headers=headers,
        files={'photos': ('sample.png', photo(), 'image/png')}).status_code == 200
    backup = client.get('/api/account/export.zip').content
    assert client.post('/api/account/delete', headers=headers,
        json={'password': 'longPassword123', 'confirmation': 'DELETE MY ACCOUNT'}).status_code == 200
    headers = register(client)
    original = photo_storage.save_photo

    def timeout(name, raw):
        original(name, raw)
        raise OSError('private-provider.example/secret')

    def metadata_failure(*args, **kwargs):
        raise RuntimeError('original restore database error')

    def unavailable(name):
        raise OSError('delete outage')

    with monkeypatch.context() as failure:
        failure.setattr(photo_storage, 'delete_photo', unavailable)
        if storage_failure == 'timeout':
            failure.setattr(photo_storage, 'save_photo', timeout)
            response = restore(client, headers, backup)
            assert response.status_code == 503
            assert 'private-provider' not in response.text
        else:
            failure.setattr(main, 'create_item', metadata_failure)
            with pytest.raises(RuntimeError, match='original restore database error'):
                restore(client, headers, backup)
    assert client.get('/api/items').json()['total'] == 0
    assert len(list((tmp_path / 'photos').glob('*.webp'))) == 1
    if storage_failure == 'timeout':
        assert photo_writes.status()['write_recovery_watch'] == 1
        assert photo_writes.reconcile(now=int(time.time()) + 120)['deleted'] == 1
    else:
        assert photo_cleanup.pending() == 1
        assert photo_cleanup.process_pending() == {'completed': 1, 'pending': 0}
    assert not list((tmp_path / 'photos').glob('*.webp'))
