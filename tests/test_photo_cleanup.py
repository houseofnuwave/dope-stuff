"""Storage outages must not turn account/photo deletion into lost cleanup work."""
import io
import subprocess
import sys
import os
import json

from PIL import Image

from app import db, photo_storage, photo_cleanup


def upload(seller, item_input):
    client = seller['client']
    item = client.post('/api/items', headers=seller['csrf'], json=item_input).json()
    image = io.BytesIO()
    Image.new('RGB', (24, 24), 'blue').save(image, 'PNG')
    response = client.post(f"/api/items/{item['id']}/photos", headers=seller['csrf'],
                           files={'photos': ('sample.png', image.getvalue(), 'image/png')})
    assert response.status_code == 200
    return response.json()['item']


def unavailable(name):
    raise OSError('simulated private storage outage')


def test_account_delete_retains_retry_work_during_storage_outage(seller, item_input, monkeypatch):
    upload(seller, item_input)
    monkeypatch.setattr(photo_storage, 'delete_photo', unavailable)
    response = seller['client'].post('/api/account/delete', headers=seller['csrf'], json={
        'password': 'longPassword123', 'confirmation': 'DELETE MY ACCOUNT'})
    assert response.status_code == 202, response.text
    assert response.json()['photo_cleanup_pending'] == 1
    assert seller['client'].get('/api/session').json()['authenticated'] is False
    with db.connect() as connection:
        assert connection.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0
        task = connection.execute('SELECT * FROM photo_deletions').fetchone()
        assert task['attempts'] == 1
        assert task['last_error'] == 'storage_unavailable'


def test_gallery_delete_retains_retry_work_during_storage_outage(seller, item_input, monkeypatch):
    item = upload(seller, item_input)
    monkeypatch.setattr(photo_storage, 'delete_photo', unavailable)
    response = seller['client'].delete(
        f"/api/items/{item['id']}/photos/{item['photos'][0]['id']}", headers=seller['csrf'])
    assert response.status_code == 202, response.text
    assert response.json()['photo_cleanup_pending'] == 1
    assert response.json()['item']['photo_count'] == 0
    assert seller['client'].get(f"/api/items/{item['id']}/photo").status_code == 404


def test_retry_survives_account_and_database_reinitialization(seller, item_input, monkeypatch, tmp_path):
    upload(seller, item_input)
    original_delete = photo_storage.delete_photo
    monkeypatch.setattr(photo_storage, 'delete_photo', unavailable)
    response = seller['client'].post('/api/account/delete', headers=seller['csrf'], json={
        'password': 'longPassword123', 'confirmation': 'DELETE MY ACCOUNT'})
    assert response.status_code == 202
    assert list((tmp_path / 'photos').glob('*.webp'))
    monkeypatch.setattr(photo_storage, 'delete_photo', original_delete)
    # A new interpreter has no request/session/in-memory worker state.
    script = '''import json, sys
from pathlib import Path
from app import db, photo_cleanup
db.DATA_DIR = Path(sys.argv[1])
db.DB_PATH = db.DATA_DIR / 'test.db'
db.init_db()
print(json.dumps(photo_cleanup.process_pending()))
'''
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)],
                            check=True, capture_output=True, text=True,
                            env={**os.environ, 'FORM_PHOTO_STORAGE': 'local', 'FORM_DATABASE_URL': ''})
    assert json.loads(result.stdout) == {'completed': 1, 'pending': 0}
    assert not list((tmp_path / 'photos').glob('*.webp'))
    assert photo_cleanup.process_pending() == {'completed': 0, 'pending': 0}


def test_cleanup_and_record_deletion_roll_back_together(seller, item_input):
    item = upload(seller, item_input)
    with db.connect() as connection:
        name = connection.execute('SELECT file_path FROM item_photos WHERE item_id=?',
                                  (item['id'],)).fetchone()[0]
        connection.execute('BEGIN IMMEDIATE')
        photo_cleanup.enqueue(connection, [name])
        connection.execute('DELETE FROM item_photos WHERE item_id=?', (item['id'],))
        connection.execute('ROLLBACK')
    assert photo_cleanup.pending() == 0
    assert seller['client'].get(f"/api/items/{item['id']}/photo").status_code == 200


def test_cleanup_never_retargets_another_storage_location(client, monkeypatch, tmp_path):
    with db.connect() as connection:
        photo_cleanup.enqueue(connection, ['unique.webp'])
    monkeypatch.setattr(db, 'DATA_DIR', tmp_path / 'another-storage-location')
    attempted = []
    monkeypatch.setattr(photo_storage, 'delete_photo', attempted.append)
    assert photo_cleanup.process_pending() == {'completed': 0, 'pending': 0}
    assert attempted == []
    assert photo_cleanup.status()['other_storage_pending'] == 1


def test_duplicate_tasks_and_crash_after_storage_delete_are_safe(client, monkeypatch):
    with db.connect() as connection:
        photo_cleanup.enqueue(connection, ['unique.webp', 'unique.webp'])
    assert photo_cleanup.pending() == 1
    # Missing local object models storage deletion completed before a worker
    # crashed without acknowledging its DB task. Retrying is still successful.
    assert photo_cleanup.process_pending() == {'completed': 1, 'pending': 0}


def test_failures_rotate_and_batches_are_bounded(client, monkeypatch):
    with db.connect() as connection:
        photo_cleanup.enqueue(connection, ['a.webp', 'b.webp', 'c.webp'])
    attempted = []

    def fail_first(name):
        attempted.append(name)
        if name == 'a.webp':
            raise OSError('private-key-example-do-not-log')

    monkeypatch.setattr(photo_storage, 'delete_photo', fail_first)
    assert photo_cleanup.process_pending(limit=1) == {'completed': 0, 'pending': 3}
    assert photo_cleanup.process_pending(limit=1) == {'completed': 1, 'pending': 2}
    assert attempted == ['a.webp', 'b.webp']
    with db.connect() as connection:
        assert 'private-key' not in str(dict(connection.execute(
            'SELECT * FROM photo_deletions WHERE file_path=?', ('a.webp',)).fetchone()))
