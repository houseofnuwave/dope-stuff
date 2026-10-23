"""State-invariant probes for isolated test accounts, not production tooling."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import secrets
import threading
from unittest.mock import patch


def _item(client, headers, payload):
    created = client.post('/api/items', headers=headers,
                          json={**payload, 'sku': 'RACE-' + secrets.token_hex(6)})
    assert created.status_code == 201, created.text
    return created.json()['id']


def assert_publish_sale_integrity(client, headers, payload):
    from app import main

    item_id = _item(client, headers, payload)
    first_read = threading.Event()
    release = threading.Event()
    claim = threading.Lock()
    original = main.user_item
    held = False

    def gated_read(connection, uid, current_id, **kwargs):
        nonlocal held
        snapshot = original(connection, uid, current_id, **kwargs)
        with claim:
            pause = current_id == item_id and not held
            if pause:
                held = True
        if pause:
            first_read.set()
            assert release.wait(10), 'Test did not release publication request'
        return snapshot

    with patch.object(main, 'user_item', side_effect=gated_read):
        with ThreadPoolExecutor(max_workers=2) as pool:
            publication = pool.submit(client.put, f'/api/items/{item_id}/channels/ebay',
                headers=headers, json={'status': 'manually_published', 'listing_url': ''})
            assert first_read.wait(5), 'Publication never reached its item precondition'
            sale = pool.submit(client.post, f'/api/items/{item_id}/sale', headers=headers,
                json={'channel': 'other', 'sold_cents': 1000, 'fee_cents': 0, 'ship_cents': 0})
            try:
                # Baseline: sale commits while publication holds a stale draft
                # snapshot. Fixed code: sale waits for the publication lock.
                sale.result(timeout=1)
            except TimeoutError:
                pass
            finally:
                release.set()
            assert publication.result(timeout=10).status_code == 200
            assert sale.result(timeout=10).status_code == 200
    final = client.get(f'/api/items/{item_id}').json()
    assert final['status'] == 'sold', 'Publication resurrected a sold item'
    assert final['quantity'] == 0
    assert final['channels']['ebay']['status'] == 'delist_required'


def assert_double_sale_integrity(client, headers, payload):
    item_id = _item(client, headers, payload)
    start = threading.Barrier(2)

    def sell():
        start.wait(timeout=5)
        return client.post(f'/api/items/{item_id}/sale', headers=headers,
            json={'channel': 'other', 'sold_cents': 1000, 'fee_cents': 0, 'ship_cents': 0})

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = [pool.submit(sell) for _ in range(2)]
        assert sorted(future.result(timeout=10).status_code for future in responses) == [200, 409]
    final = client.get(f'/api/items/{item_id}').json()
    assert final['status'] == 'sold' and final['quantity'] == 0
    sales = client.get('/api/sales').json()['sales']
    assert sum(sale['item_id'] == item_id for sale in sales) == 1
