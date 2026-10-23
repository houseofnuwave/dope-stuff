"""Records beyond old list caps must remain reachable and owner-scoped."""
import pytest

from app import db
from tools.pagination_checks import seed_records, assert_live_count_snapshot


@pytest.mark.parametrize('kind,count,key,cap', [
    ('inventory', 201, 'items', 200),
    ('actions', 201, 'actions', 200),
    ('sales', 501, 'sales', 500),
])
def test_every_record_is_reachable_across_old_caps(seller, kind, count, key, cap):
    client = seller['client']
    uid = client.get('/api/session').json()['user']['id']
    expected = seed_records(uid, count, kind)
    endpoint = '/api/items' if kind == 'inventory' else '/api/' + kind
    first = client.get(endpoint, params={'limit': cap, 'offset': 0}).json()
    last = client.get(endpoint, params={'limit': cap, 'offset': cap}).json()
    assert first['total'] == last['total'] == count
    assert first['has_more'] is True
    assert last['has_more'] is False
    assert first['offset'] == 0 and last['offset'] == cap
    assert len(first[key]) == cap and len(last[key]) == 1
    ids = [record['id' if kind == 'inventory' else 'item_id'] for record in first[key] + last[key]]
    assert len(ids) == len(set(ids)) == count
    assert set(ids) == set(expected)


@pytest.mark.parametrize('endpoint,key', [('/api/items', 'items'), ('/api/actions', 'actions'), ('/api/sales', 'sales')])
def test_empty_and_out_of_range_pages_are_explicit(seller, endpoint, key):
    client = seller['client']
    empty = client.get(endpoint, params={'limit': 10, 'offset': 5000}).json()
    assert empty[key] == [] and empty['total'] == 0 and empty['has_more'] is False
    normalized = client.get(endpoint, params={'limit': 0, 'offset': -20}).json()
    assert normalized['limit'] == 1 and normalized['offset'] == 0


def test_inventory_filter_search_and_totals_stay_owner_scoped(seller):
    client = seller['client']
    uid = client.get('/api/session').json()['user']['id']
    seed_records(uid, 201, 'inventory')
    with db.connect() as connection:
        # A second identity has matching search text but must not affect counts.
        connection.execute('''INSERT INTO users(name,email,password_hash)
            VALUES (?,?,?)''', ('Other Seller', 'private@example.com', 'not-a-login-hash'))
        other_id = connection.execute('SELECT id FROM users WHERE email=?', ('private@example.com',)).fetchone()[0]
    seed_records(other_id, 2, 'inventory')
    page = client.get('/api/items', params={'q': 'Paging item 0000', 'limit': 1}).json()
    assert page['total'] == 1 and page['has_more'] is False
    assert client.get('/api/items', params={'status': 'sold'}).json()['total'] == 0
    assert client.get('/api/items').json()['total'] == 201


@pytest.mark.parametrize('kind,key', [('actions', 'actions'), ('sales', 'sales')])
def test_action_and_sales_pages_do_not_disclose_other_sellers(seller, kind, key):
    client = seller['client']
    uid = client.get('/api/session').json()['user']['id']
    expected = seed_records(uid, 3, kind)
    with db.connect() as connection:
        connection.execute('INSERT INTO users(name,email,password_hash) VALUES (?,?,?)',
                           ('Other Seller', 'private@example.com', 'not-a-login-hash'))
        other_id = connection.execute('SELECT id FROM users WHERE email=?', ('private@example.com',)).fetchone()[0]
    seed_records(other_id, 4, kind)
    page = client.get('/api/' + kind, params={'limit': 2, 'offset': 2}).json()
    assert page['total'] == 3 and page['has_more'] is False
    assert len(page[key]) == 1 and page[key][0]['item_id'] in expected


@pytest.mark.parametrize('kind', ['actions', 'sales'])
def test_page_count_and_rows_share_a_snapshot_during_new_sales(seller, kind):
    assert_live_count_snapshot(seller['client'], kind)
