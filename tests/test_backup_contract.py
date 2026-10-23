"""A successful portable export must satisfy the actual restore contract."""
import io
import json
import zipfile

import pytest

from app import backup, db, main, photo_storage
from test_v03 import add_with_images
from test_v04 import backup_file, register, restore
from tools.pagination_checks import seed_records
from tools.backup_checks import canonical_records, assert_export_snapshot


def test_large_history_round_trip_preserves_all_records_and_photos(seller, item_input):
    client = seller['client']; headers = seller['csrf']
    photographed = add_with_images(seller, item_input)
    uid = client.get('/api/session').json()['user']['id']
    seed_records(uid, 500, 'sales')
    original = client.get('/api/account/export.zip')
    assert original.status_code == 200, original.text
    with zipfile.ZipFile(io.BytesIO(original.content)) as archive:
        metadata = json.loads(archive.read('form_backup.json'))
        assert len(metadata['items']) == 501 and len(metadata['sales']) == 500
        assert len(metadata['item_photos']) == 2
    assert client.post('/api/account/delete', headers=headers, json={
        'password': 'longPassword123', 'confirmation': 'DELETE MY ACCOUNT'}).status_code == 200
    headers = register(client)
    preview = client.post('/api/account/restore-preview', headers=headers, files=backup_file(original.content))
    assert preview.status_code == 200, preview.text
    assert preview.json()['summary']['items'] == 501
    completed = restore(client, headers, original.content)
    assert completed.status_code == 200, completed.text
    assert client.get('/api/items').json()['total'] == 501
    assert client.get('/api/sales').json()['total'] == 500
    recovered = client.get('/api/items', params={'q': photographed['sku']}).json()['items'][0]
    assert recovered['photo_count'] == 2
    assert client.get(f"/api/items/{recovered['id']}/photo").status_code == 200
    assert client.get('/api/insights').json()['totals']['profit_cents'] == 500 * 800
    repeated = client.get('/api/account/export.zip')
    assert repeated.status_code == 200
    assert canonical_records(original.content) == canonical_records(repeated.content)


def test_missing_photo_blocks_export_instead_of_producing_an_invalid_archive(seller, item_input):
    item = add_with_images(seller, item_input)
    with db.connect() as connection:
        name = connection.execute('SELECT file_path FROM item_photos WHERE item_id=? ORDER BY id DESC', (item['id'],)).fetchone()[0]
    photo_storage.delete_photo(name)
    response = seller['client'].get('/api/account/export.zip')
    assert response.status_code == 409
    assert 'missing' in response.json()['detail'].lower()
    assert 'content-disposition' not in response.headers
    assert seller['client'].get('/api/items').json()['total'] == 1


def test_corrupt_photo_is_rejected_before_download_headers(seller, item_input, monkeypatch):
    add_with_images(seller, item_input)
    monkeypatch.setattr(photo_storage, 'read_photo', lambda name: b'not a photograph')
    response = seller['client'].get('/api/account/export.zip')
    assert response.status_code == 409
    assert 'content-disposition' not in response.headers


def test_storage_outage_does_not_leak_provider_details_or_return_a_zip(seller, item_input, monkeypatch):
    add_with_images(seller, item_input)

    def unavailable(name):
        raise OSError('private-provider.example/private-account-key')

    monkeypatch.setattr(photo_storage, 'read_photo', unavailable)
    response = seller['client'].get('/api/account/export.zip')
    assert response.status_code == 503
    assert 'private-provider' not in response.text and 'private-account-key' not in response.text
    assert 'content-disposition' not in response.headers


@pytest.mark.parametrize('limit', ['MAX_RESTORE_ITEMS', 'MAX_RESTORE_PHOTOS', 'MAX_ARCHIVE_FILES',
                                 'MAX_JSON_BYTES', 'MAX_ZIP_BYTES', 'MAX_UNCOMPRESSED_BYTES',
                                 'MAX_PHOTO_FILE_BYTES', 'MAX_RESTORE_FEEDBACK'])
def test_export_enforces_the_same_resource_limits_as_restore(seller, item_input, monkeypatch, limit):
    add_with_images(seller, item_input)
    seller['client'].post('/api/feedback', headers=seller['csrf'],
                          json={'rating': 4, 'message': 'Synthetic feedback'})
    monkeypatch.setattr(backup, limit, 0)
    response = seller['client'].get('/api/account/export.zip')
    assert response.status_code == 413, response.text
    assert 'content-disposition' not in response.headers
    assert seller['client'].get('/api/items').json()['total'] == 1


def test_temporary_export_files_close_after_success_and_failure(seller, item_input, monkeypatch):
    add_with_images(seller, item_input)
    original = backup.tempfile.SpooledTemporaryFile
    opened = []

    def tracked(*args, **kwargs):
        stream = original(*args, **kwargs)
        opened.append(stream)
        return stream

    monkeypatch.setattr(backup.tempfile, 'SpooledTemporaryFile', tracked)
    completed = seller['client'].get('/api/account/export.zip')
    assert completed.status_code == 200
    assert int(completed.headers['content-length']) == len(completed.content)
    assert opened and all(stream.closed for stream in opened)
    monkeypatch.setattr(photo_storage, 'read_photo', lambda name: b'invalid stored image')
    assert seller['client'].get('/api/account/export.zip').status_code == 409
    assert len(opened) == 2 and all(stream.closed for stream in opened)


def test_invalid_record_state_cannot_be_downloaded_as_a_valid_backup(seller, item_input):
    item = seller['client'].post('/api/items', headers=seller['csrf'], json=item_input).json()
    with db.connect() as connection:
        # Model a bad legacy/migration state, not a supported API transition.
        connection.execute("UPDATE items SET status='sold',quantity=0 WHERE id=?", (item['id'],))
    response = seller['client'].get('/api/account/export.zip')
    assert response.status_code == 409
    assert 'content-disposition' not in response.headers


def test_oversized_local_photo_is_read_with_a_bound_and_export_is_rejected(seller, item_input, monkeypatch):
    item = add_with_images(seller, item_input)
    with db.connect() as connection:
        name = connection.execute('SELECT file_path FROM item_photos WHERE item_id=?', (item['id'],)).fetchone()[0]
    monkeypatch.setattr(photo_storage, 'MAX_STORED_PHOTO_BYTES', 16)
    with pytest.raises(photo_storage.PhotoTooLarge):
        photo_storage.read_photo(name)
    response = seller['client'].get('/api/account/export.zip')
    assert response.status_code == 413
    assert 'content-disposition' not in response.headers


def test_concurrent_sale_cannot_make_export_internally_inconsistent(seller, item_input):
    assert_export_snapshot(seller['client'], seller['csrf'], item_input)


def test_expanded_budget_counts_metadata_and_all_photos_together(seller, item_input, monkeypatch):
    add_with_images(seller, item_input)
    valid = seller['client'].get('/api/account/export.zip')
    assert valid.status_code == 200
    with zipfile.ZipFile(io.BytesIO(valid.content)) as archive:
        expanded = sum(entry.file_size for entry in archive.infolist())
        assert archive.getinfo('form_backup.json').file_size < expanded - 1
    monkeypatch.setattr(backup, 'MAX_UNCOMPRESSED_BYTES', expanded - 1)
    rejected = seller['client'].get('/api/account/export.zip')
    assert rejected.status_code == 413
    assert 'content-disposition' not in rejected.headers


def test_zip_budget_includes_the_finished_archive_directory(seller, item_input, monkeypatch):
    add_with_images(seller, item_input)
    valid = seller['client'].get('/api/account/export.zip')
    assert valid.status_code == 200
    monkeypatch.setattr(backup, 'MAX_ZIP_BYTES', len(valid.content) - 1)
    rejected = seller['client'].get('/api/account/export.zip')
    assert rejected.status_code == 413
    assert 'content-disposition' not in rejected.headers


def test_temporary_storage_failure_is_a_sanitized_error(seller, item_input, monkeypatch):
    add_with_images(seller, item_input)

    def unavailable(*args, **kwargs):
        raise OSError('private-disk-location/customer-data')

    monkeypatch.setattr(backup.tempfile, 'SpooledTemporaryFile', unavailable)
    response = seller['client'].get('/api/account/export.zip')
    assert response.status_code == 503
    assert 'private-disk-location' not in response.text
    assert 'content-disposition' not in response.headers
