"""Portable recovery assertions for isolated backend/cloud fixtures only."""
import io
import json
import secrets
import zipfile
from contextlib import contextmanager
from unittest.mock import patch


def metadata(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        return json.loads(archive.read('form_backup.json'))


def canonical_records(raw):
    """Compare meaningful records while allowing IDs/private storage names to change."""
    data = metadata(raw)
    skus = {item['id']: item['sku'] for item in data['items']}

    def clean(row, excluded):
        return {key: value for key, value in row.items() if key not in excluded}

    return {
        # Inventory recovery verifies mailbox identity but deliberately keeps
        # the current account's chosen display name and new database identity.
        'account': {'email': data['account']['email']},
        'items': {item['sku']: clean(item, {'id', 'user_id', 'photo_path'}) for item in data['items']},
        'channels': {(skus[row['item_id']], row['channel']): clean(row, {'id', 'item_id'})
                     for row in data['item_channels']},
        'photos': {(skus[row['item_id']], row['position']): clean(row, {'id', 'item_id', 'file_path'})
                   for row in data['item_photos']},
        'sales': {skus[row['item_id']]: clean(row, {'id', 'item_id', 'user_id'}) for row in data['sales']},
        'feedback': sorted(json.dumps(clean(row, {'id', 'user_id'}), sort_keys=True) for row in data['feedback']),
    }


def restore_after_deletion(client, auth, raw):
    """Caller has already deleted its disposable account; restore and compare all records."""
    assert len(metadata(raw)['items']) > 500
    registered = client.post('/api/auth/register', json=auth)
    assert registered.status_code == 200, registered.text
    headers = {'x-csrf-token': client.get('/api/session').json()['csrf']}
    preview = client.post('/api/account/restore-preview', headers=headers,
                          files={'file': ('recovery.zip', raw, 'application/zip')})
    assert preview.status_code == 200, preview.text
    completed = client.post('/api/account/restore', headers=headers,
        data={'password': auth['password'], 'confirmation': 'RESTORE MY DATA'},
        files={'file': ('recovery.zip', raw, 'application/zip')})
    assert completed.status_code == 200, completed.text
    exported = client.get('/api/account/export.zip')
    assert exported.status_code == 200, exported.text
    assert canonical_records(raw) == canonical_records(exported.content), 'Records changed during large recovery'
    return headers


def assert_export_snapshot(client, headers, payload):
    """A sale committed mid-export must not mix old item state with new sales."""
    from app import db, main

    created = client.post('/api/items', headers=headers,
                          json={**payload, 'sku': 'BACKUP-' + secrets.token_hex(6)})
    assert created.status_code == 201, created.text
    item_id = created.json()['id']
    triggered = False

    class ItemRows:
        def __init__(self, result):
            self.result = result

        def __iter__(self):
            nonlocal triggered
            rows = list(self.result)
            if not triggered:
                triggered = True
                sale = client.post(f'/api/items/{item_id}/sale', headers=headers, json={
                    'channel': 'other', 'sold_cents': 1000, 'fee_cents': 0, 'ship_cents': 0})
                assert sale.status_code == 200, sale.text
            return iter(rows)

    class Connection:
        def __init__(self, connection):
            self.connection = connection

        def execute(self, query, params=()):
            result = self.connection.execute(query, params)
            return ItemRows(result) if query.startswith('SELECT * FROM items WHERE user_id=?') else result

    @contextmanager
    def connect():
        with db.connect() as connection:
            yield Connection(connection)

    with patch.object(main, 'connect', connect):
        exported = client.get('/api/account/export.zip')
    assert triggered
    assert exported.status_code == 200, exported.text
    snapshot = metadata(exported.content)
    old_item = next(item for item in snapshot['items'] if item['id'] == item_id)
    assert old_item['status'] == 'draft'
    assert all(sale['item_id'] != item_id for sale in snapshot['sales'])
    assert client.get(f'/api/items/{item_id}').json()['status'] == 'sold'
