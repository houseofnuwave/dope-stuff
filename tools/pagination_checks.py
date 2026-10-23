"""Synthetic pagination fixtures for isolated tests; no production CLI."""
import secrets
from contextlib import contextmanager
from unittest.mock import patch

from app import db, main


def seed_records(user_id, count, kind):
    prefix = secrets.token_hex(6)
    ids = []
    with db.connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        for number in range(count):
            item_id = main.create_item(connection, user_id, main.ItemInput(
                sku=f'PAGE-{prefix}-{number:04}', title=f'Paging item {number:04}',
                price_cents=1000, cost_cents=100, quantity=1))
            ids.append(item_id)
            if kind in ('actions', 'sales'):
                connection.execute("UPDATE items SET status='sold',quantity=0 WHERE id=?", (item_id,))
                connection.execute('''INSERT INTO sales(item_id,user_id,channel,sold_cents,fee_cents,ship_cents,cost_cents)
                    VALUES (?,?,?,?,?,?,?)''', (item_id, user_id, 'other', 1000, 50, 50, 100))
            if kind == 'actions':
                connection.execute("UPDATE item_channels SET status='delist_required' WHERE item_id=? AND channel='ebay'",
                                   (item_id,))
        connection.execute('COMMIT')
    return ids


def assert_pagination_boundaries(client):
    """Reach every synthetic fixture across old caps on the configured backend."""
    uid = client.get('/api/session').json()['user']['id']
    for kind, count, key, cap in [('inventory', 201, 'items', 200),
                                  ('actions', 201, 'actions', 200),
                                  ('sales', 501, 'sales', 500)]:
        expected = set(seed_records(uid, count, kind))
        endpoint = '/api/items' if kind == 'inventory' else '/api/' + kind
        found = []
        offset = 0
        while True:
            response = client.get(endpoint, params={'limit': cap, 'offset': offset})
            assert response.status_code == 200, response.text
            page = response.json()
            rows = page[key]
            found.extend(row['id' if kind == 'inventory' else 'item_id'] for row in rows)
            assert page['offset'] == offset
            if not page['has_more']:
                assert len(found) == page['total']
                break
            assert len(rows) == cap
            offset += len(rows)
        assert len(found) == len(set(found)), 'Duplicate records across stable test pages'
        assert expected.issubset(found), f'{kind} records beyond the old cap were inaccessible'


def assert_live_count_snapshot(client, kind):
    """Insert new work after COUNT but before rows; one page must stay coherent."""
    uid = client.get('/api/session').json()['user']['id']
    seed_records(uid, 1, kind)
    endpoint = '/api/' + kind
    total = client.get(endpoint).json()['total']
    params = {'offset': total - 1 if kind == 'actions' else 0, 'limit': 2}
    baseline = client.get(endpoint, params=params).json()
    injected = False
    prefix = 'SELECT COUNT(*) FROM item_channels' if kind == 'actions' else 'SELECT COUNT(*) FROM sales'

    class CountResult:
        def __init__(self, result):
            self.result = result

        def fetchone(self):
            nonlocal injected
            count = self.result.fetchone()
            if not injected:
                injected = True
                seed_records(uid, 1, kind)
            return count

    class Connection:
        def __init__(self, connection):
            self.connection = connection

        def execute(self, query, params=()):
            result = self.connection.execute(query, params)
            return CountResult(result) if query.startswith(prefix) else result

    @contextmanager
    def connect():
        with db.connect() as connection:
            yield Connection(connection)

    with patch.object(main, 'connect', connect):
        snapshot = client.get(endpoint, params=params).json()
    assert injected
    assert snapshot['total'] == total
    assert [row['item_id'] for row in snapshot[kind]] == [row['item_id'] for row in baseline[kind]]
    assert client.get(endpoint).json()['total'] == total + 1
