import pytest
from fastapi.testclient import TestClient
from app import db
from app import main

@pytest.fixture
def client(tmp_path, monkeypatch):
    # Per-test test server/client IP must not share in-memory rate limits.
    main.failed_attempts.clear()
    monkeypatch.setattr(db, 'DATA_DIR',tmp_path)
    monkeypatch.setattr(db, 'DB_PATH',tmp_path/'test.db')
    monkeypatch.setattr(main, 'DATA_DIR',tmp_path)
    with TestClient(main.app) as c:
        yield c

@pytest.fixture
def seller(client):
    r=client.post('/api/auth/register',json={'name':'Demo Seller','email':'seller@example.com','password':'longPassword123'})
    assert r.status_code == 200, r.text
    csrf=client.get('/api/session').json()['csrf']
    return {'client':client,'csrf':{'x-csrf-token':csrf}}

@pytest.fixture
def item_input():
    return dict(sku='TEST-001',title='Black leather boots',brand='Sample',category='Footwear',size='EU 39',
        color='Black',condition='Like new',price_cents=42000,cost_cents=12000,shipping_cents=800,
        quantity=1,description='Genuine listing test sample, not real merchandise.',notes='Private note')
