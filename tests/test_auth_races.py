import io
import csv
import json
import time
import zipfile
from unittest.mock import patch
import pytest

from app import db, main
from tools.auth_race_checks import (assert_revoked_inflight_write_rejected, assert_password_changes_serialized,
    assert_password_change_revokes_waiting_reset, assert_one_reset_winner,
    assert_concurrent_requests_leave_one_reset, assert_recovery_during_account_deletion_is_generic, reset_token)
from tools.auth_race_checks import assert_login_then_change_revokes_login_cookie, assert_deletion_revokes_waiting_reset


def test_revoked_session_cannot_finish_a_waiting_content_write(seller, item_input):
    assert_revoked_inflight_write_rejected(seller['client'], seller['csrf'], item_input)


def test_password_changes_do_not_reuse_a_session_version(seller):
    assert_password_changes_serialized(seller['client'], seller['csrf'])


def test_password_change_wins_over_a_waiting_reset_without_deadlock(seller):
    assert_password_change_revokes_waiting_reset(seller['client'], seller['csrf'])


def test_simultaneous_reset_replay_has_one_winner(seller):
    assert_one_reset_winner(seller['client'])


def test_login_racing_password_change_cannot_leave_a_valid_old_cookie(seller):
    assert_login_then_change_revokes_login_cookie(seller['client'], seller['csrf'])


def test_deletion_revokes_reset_waiting_on_the_owner(seller):
    assert_deletion_revokes_waiting_reset(seller['client'], seller['csrf'])


def test_concurrent_recovery_issuance_supersedes_old_token(seller):
    assert_concurrent_requests_leave_one_reset(seller['client'])


def test_request_during_account_deletion_does_not_leak_existence_or_fail(seller):
    assert_recovery_during_account_deletion_is_generic(seller['client'], seller['csrf'])


def test_expiry_is_measured_after_owner_lock_not_before(seller):
    client = seller['client']
    token = reset_token(client)
    now = int(time.time())
    with db.connect() as connection:
        connection.execute('UPDATE password_resets SET expires_at=?', (now + 10,))
    original = main.lock_owner_row
    clock = [now]

    def delayed_lock(*args):
        result = original(*args)
        clock[0] = now + 20  # Emulate elapsed time during a contended lock.
        return result

    with patch.object(main, 'lock_owner_row', side_effect=delayed_lock), \
            patch.object(main.time, 'time', side_effect=lambda: clock[0]):
        response = client.post('/api/auth/recovery/confirm', json={
            'token': token, 'new_password': 'TooLatePassword456'})
    assert response.status_code == 400
    assert client.get('/api/session').json()['authenticated'] is True


def test_authorization_snapshot_never_leaks_into_session_or_backup(seller):
    client = seller['client']
    assert set(client.get('/api/session').json()['user']) == {'id', 'name', 'email'}
    response = client.get('/api/account/export.zip')
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        account = json.loads(archive.read('form_backup.json'))['account']
    assert set(account) == {'id', 'name', 'email'}


def test_missing_authorization_snapshot_fails_closed(seller):
    uid = seller['client'].get('/api/session').json()['user']['id']
    with db.connect() as connection:
        try:
            main.begin_owner_write(connection, {'id': uid})
        except main.HTTPException as error:
            assert error.status_code == 401
        else:
            raise AssertionError('Mutation without the authenticated version was allowed')


@pytest.mark.parametrize('kind', ['duplicate', 'edit', 'archive', 'channel', 'sale', 'csv',
    'feedback', 'upload', 'photo_delete', 'photo_order', 'account_delete'])
def test_revoked_inflight_content_routes_preserve_all_records(seller, item_input, kind):
    from tools.photo_write_checks import image
    client = seller['client']; headers = seller['csrf']
    item = client.post('/api/items', headers=headers, json=item_input).json()
    uploaded = client.post(f"/api/items/{item['id']}/photos", headers=headers,
        files=[('photos', (f'{i}.png', image(), 'image/png')) for i in range(2)])
    assert uploaded.status_code == 200, uploaded.text
    photos = uploaded.json()['item']['photos']
    item_url = f"/api/items/{item['id']}"
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=['sku', 'title', 'price', 'condition'])
    writer.writeheader()
    writer.writerow({'sku': 'MUST-NOT-IMPORT', 'title': item_input['title'], 'price': '42.00', 'condition': 'Good'})

    def mutation(other, token):
        if kind == 'duplicate': return other.post(item_url + '/duplicate', headers=token)
        if kind == 'edit': return other.put(item_url, headers=token, json={**item_input, 'title': 'Must not change'})
        if kind == 'archive': return other.delete(item_url, headers=token)
        if kind == 'channel': return other.put(item_url + '/channels/ebay', headers=token,
            json={'status': 'manually_published', 'listing_url': ''})
        if kind == 'sale': return other.post(item_url + '/sale', headers=token,
            json={'channel': 'other', 'sold_cents': 1000, 'fee_cents': 0, 'ship_cents': 0})
        if kind == 'csv': return other.post('/api/import.csv', headers=token,
            files={'file': ('items.csv', output.getvalue().encode(), 'text/csv')})
        if kind == 'feedback': return other.post('/api/feedback', headers=token,
            json={'rating': 5, 'message': 'Must not insert'})
        if kind == 'upload': return other.post(item_url + '/photos', headers=token,
            files={'photos': ('sample.png', image(), 'image/png')})
        if kind == 'photo_delete': return other.delete(item_url + f"/photos/{photos[0]['id']}", headers=token)
        if kind == 'photo_order': return other.put(item_url + '/photos/order', headers=token,
            json={'photo_ids': [p['id'] for p in reversed(photos)]})
        if kind == 'account_delete': return other.post('/api/account/delete', headers=token,
            json={'password': 'longPassword123', 'confirmation': 'DELETE MY ACCOUNT'})
        raise AssertionError('Unknown route probe')

    def snapshot():
        with db.connect() as connection:
            return {table: [dict(r) for r in connection.execute('SELECT * FROM ' + table + ' ORDER BY id')]
                    for table in ('items', 'item_channels', 'item_photos', 'sales', 'feedback')}

    before = snapshot()
    with patch.object(main.photo_storage, 'save_photo', wraps=main.photo_storage.save_photo) as save:
        assert_revoked_inflight_write_rejected(client, headers, item_input, mutation)
        assert save.call_count == 0
    assert snapshot() == before
    assert main.photo_writes.status()['write_prepared'] == 0


def test_revoked_inflight_restore_writes_no_photos(seller, item_input):
    from test_v04 import register, restore
    from tools.photo_write_checks import image
    client = seller['client']; headers = seller['csrf']
    item = client.post('/api/items', headers=headers, json=item_input).json()
    assert client.post(f"/api/items/{item['id']}/photos", headers=headers,
        files={'photos': ('sample.png', image(), 'image/png')}).status_code == 200
    backup = client.get('/api/account/export.zip').content
    assert client.post('/api/account/delete', headers=headers,
        json={'password': 'longPassword123', 'confirmation': 'DELETE MY ACCOUNT'}).status_code == 200
    headers = register(client)
    with patch.object(main.photo_storage, 'save_photo', wraps=main.photo_storage.save_photo) as save:
        assert_revoked_inflight_write_rejected(client, headers, item_input,
            mutation=lambda c, token: restore(c, token, backup))
        assert save.call_count == 0
    assert client.get('/api/items').json()['total'] == 0
    assert main.photo_writes.status()['write_prepared'] == 0
