"""Inventory aging is a read-only snapshot, never external marketplace age."""
from datetime import datetime, timedelta, timezone

from app import db


def days_ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days, minutes=5)).strftime('%Y-%m-%d %H:%M:%S')


def insert(connection, user_id, number, days, cost, *, status='draft'):
    connection.execute("""INSERT INTO items
        (user_id,sku,title,created_at,updated_at,cost_cents,price_cents,quantity,status)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (user_id, f'AGE-{user_id}-{number}', f'Synthetic garment {number}',
         days_ago(days), days_ago(days), cost, 15000, 1 if status != 'sold' else 0, status))


def test_aging_empty_and_requires_login(client):
    assert client.get('/api/inventory-aging').status_code == 401
    created = client.post('/api/auth/register', json={
        'name': 'Synthetic Seller', 'email':'one@example.com','password':'ExamplePassword123'})
    assert created.status_code == 200
    r=client.get('/api/inventory-aging')
    assert r.status_code == 200
    data=r.json()
    assert data['available_count']==0
    assert data['recorded_cost_cents']==0
    assert data['aging_30_plus_count']==0
    assert data['oldest']==[]
    assert [x['count'] for x in data['buckets']]==[0,0,0,0]


def test_aging_owner_scope_excluded_status_and_recorded_cost(seller):
    c=seller['client']
    uid=c.get('/api/session').json()['user']['id']
    with db.connect() as connection:
        for number,days,cost,status in (
            (1,10,1000,'draft'),(2,45,2000,'active'),
            (3,75,3000,'draft'),(4,120,4000,'active'),
            (5,200,5000,'sold'),(6,300,6000,'archived')
        ):
            insert(connection,uid,number,days,cost,status=status)
        connection.execute("INSERT INTO users(name,email,password_hash) VALUES ('Other','other@example.com','placeholder')")
        other_id=connection.execute("SELECT id FROM users WHERE email='other@example.com'").fetchone()[0]
        insert(connection,other_id,7,500,999999,status='active')

    r=c.get('/api/inventory-aging')
    assert r.status_code==200
    data=r.json()
    assert data['available_count']==4
    assert data['recorded_cost_cents']==10000
    assert data['aging_30_plus_count']==3
    assert data['aging_30_plus_cost_cents']==9000
    assert [b['count'] for b in data['buckets']]==[1,1,1,1]
    assert [b['cost_cents'] for b in data['buckets']]==[1000,2000,3000,4000]
    assert [x['sku'] for x in data['oldest']]==[
        f'AGE-{uid}-4',f'AGE-{uid}-3',f'AGE-{uid}-2']
    assert 'other@example.com' not in r.text
    assert '999999' not in r.text
    assert all('user_id' not in x and 'notes' not in x and 'photo_path' not in x for x in data['oldest'])
    assert 'not original acquisition' in data['notice']


def test_aging_is_full_account_not_paginated_and_not_mutating(seller):
    c=seller['client']
    uid=c.get('/api/session').json()['user']['id']
    with db.connect() as connection:
        for n in range(225):
            insert(connection,uid,n,120,1250,status='draft')
        before=connection.execute("SELECT COUNT(*) FROM items WHERE user_id=?",(uid,)).fetchone()[0]
    data=c.get('/api/inventory-aging').json()
    assert data['available_count']==225
    assert data['aging_30_plus_count']==225
    assert data['aging_30_plus_cost_cents']==225*1250
    assert data['buckets'][3]['count']==225
    assert len(data['oldest'])==5
    assert c.get('/api/items',params={'limit':1}).json()['total']==225
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM items WHERE user_id=?",(uid,)).fetchone()[0]==before
        assert connection.execute("SELECT COUNT(*) FROM sales WHERE user_id=?",(uid,)).fetchone()[0]==0
