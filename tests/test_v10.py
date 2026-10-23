"""v1.0 founder-beta release gates: account security and sell-through fundamentals."""
import csv
import io
import zipfile
from fastapi.testclient import TestClient
from app import main, db


def test_change_password_revokes_other_sessions(client, seller):
    c=seller['client'];h=seller['csrf']
    other=TestClient(main.app)
    r=other.post('/api/auth/login',json={'email':'seller@example.com','password':'longPassword123'})
    assert r.status_code==200
    assert other.get('/api/session').json()['authenticated'] is True
    assert c.post('/api/account/password',headers=h,json={
        'current_password':'wrongpassword12','new_password':'newLongPassword123!'}).status_code==401
    assert other.get('/api/session').json()['authenticated'] is True
    r=c.post('/api/account/password',headers=h,json={
        'current_password':'longPassword123','new_password':'newLongPassword123!'})
    assert r.status_code==200,r.text
    assert c.get('/api/session').json()['authenticated'] is True
    assert other.get('/api/session').json()['authenticated'] is False
    assert other.get('/api/items').status_code==401
    assert c.get('/api/items').status_code==200
    assert c.post('/api/auth/logout',headers={'x-csrf-token':c.get('/api/session').json()['csrf']}).status_code==200
    assert c.post('/api/auth/login',json={'email':'seller@example.com','password':'longPassword123'}).status_code==401
    assert c.post('/api/auth/login',json={'email':'seller@example.com','password':'newLongPassword123!'}).status_code==200
    other.close()


def test_duplicate_is_independent_and_private(seller,item_input,client):
    c=seller['client'];h=seller['csrf']
    item=c.post('/api/items',json=item_input,headers=h).json();iid=item['id']
    assert c.put(f'/api/items/{iid}/channels/depop',json={'status':'manually_published','listing_url':''},headers=h).status_code==200
    copy=c.post(f'/api/items/{iid}/duplicate',headers=h)
    assert copy.status_code==201, copy.text
    duplicated=copy.json()['item']
    assert duplicated['id']!=iid
    assert duplicated['sku']!=item_input['sku']
    assert duplicated['status']=='draft'
    assert duplicated['quantity']==1
    assert duplicated['photo_count']==0
    assert duplicated['channels']['depop']['status']=='not_started'
    assert duplicated['channels']['depop']['listing_url']==''
    assert duplicated['cost_cents']==item_input['cost_cents']
    assert c.get('/api/items').json()['total']==2
    c.post('/api/auth/logout',headers=h)
    c.post('/api/auth/register',json={'name':'Second Person','email':'two@example.com','password':'longPassword123'})
    secret={'x-csrf-token':c.get('/api/session').json()['csrf']}
    assert c.post(f'/api/items/{iid}/duplicate',headers=secret).status_code==404
    assert c.get(f'/api/items/{duplicated["id"]}').status_code==404


def test_insights_and_sales_export_are_realized(seller,item_input):
    c=seller['client'];h=seller['csrf']
    empty=c.get('/api/insights').json()
    assert empty['totals']['margin_pct'] is None
    i=c.post('/api/items',headers=h,json=item_input).json()['id']
    assert c.get('/api/insights').json()['available_inventory']['count']==1
    sale=c.post(f'/api/items/{i}/sale',json={'channel':'depop','sold_cents':40000,'fee_cents':3200,'ship_cents':600},headers=h)
    assert sale.status_code==200
    info=c.get('/api/insights').json()
    assert info['totals']=={'sales':1,'gross_cents':40000,'profit_cents':24200,'margin_pct':60.5}
    assert info['channels'][0]['display_name']=='Depop'
    assert info['channels'][0]['acquisition_cents']==12000
    assert info['available_inventory']['count']==0
    data=c.get('/api/sales-export.csv')
    assert data.status_code==200
    rows=list(csv.DictReader(io.StringIO(data.text)))
    assert len(rows)==1
    assert rows[0]['net_profit_usd']=='242.00'
    assert rows[0]['title']=='Black leather boots'
    assert 'user-entered costs' in info['disclaimer']


def test_sales_csv_prevents_formula_injection(seller,item_input):
    c=seller['client'];h=seller['csrf'];data={**item_input,'title':'=HYPERLINK("http://bad")'}
    i=c.post('/api/items',headers=h,json=data).json()['id']
    c.post(f'/api/items/{i}/sale',headers=h,json={'channel':'other','sold_cents':25000})
    rows=list(csv.DictReader(io.StringIO(c.get('/api/sales-export.csv').text)))
    assert rows[0]['title'].startswith("'=")


def test_legacy_database_migrates_non_destructively(client,seller):
    with db.connect() as con:
        row=con.execute('SELECT session_version FROM users WHERE email=?',('seller@example.com',)).fetchone()
        assert row['session_version']==0
    # Schema initializer is safe on a migrated db.
    db.init_db()
    assert client.get('/api/session').json()['authenticated'] is True


def test_backup_still_restores_after_v10_schema(seller,item_input):
    c=seller['client'];h=seller['csrf']
    c.post('/api/items',json=item_input,headers=h)
    blob=c.get('/api/account/export.zip').content
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        assert 'form_backup.json' in z.namelist()
    assert c.get('/api/account/export.zip').status_code==200


def test_action_center_only_after_real_sale(seller,item_input):
    c=seller['client'];h=seller['csrf']
    i=c.post('/api/items',json=item_input,headers=h).json()['id']
    assert c.get('/api/actions').json()['total']==0
    for channel in ('grailed','depop'):
        c.put(f'/api/items/{i}/channels/{channel}',headers=h,json={
            'status':'manually_published',
            'listing_url':'https://www.grailed.com/listings/1234' if channel=='grailed' else 'https://www.depop.com/products/test-seller-test/'})
    # Merely publishing does not imply pending removal: the sale triggers reminders.
    assert c.get('/api/actions').json()['actions']==[]
    assert c.post(f'/api/items/{i}/sale',headers=h,json={'channel':'grailed','sold_cents':39000}).status_code==200
    tasks=c.get('/api/actions').json()
    assert tasks['total']==1 and len(tasks['actions'])==1
    task=tasks['actions'][0]
    assert task['display_name']=='Depop'
    assert task['item_id']==i
    assert task['listing_url'].startswith('https://www.depop.com/')
    assert c.put(f'/api/items/{i}/channels/depop',headers=h,json={
        'status':'delisted','listing_url':task['listing_url']}).status_code==200
    assert c.get('/api/actions').json()['total']==0


def test_action_center_isolation(seller,item_input):
    c=seller['client'];h=seller['csrf']
    i=c.post('/api/items',json=item_input,headers=h).json()['id']
    c.put(f'/api/items/{i}/channels/depop',json={'status':'manually_published','listing_url':''},headers=h)
    c.post(f'/api/items/{i}/sale',headers=h,json={'channel':'other','sold_cents':16000})
    assert c.get('/api/actions').json()['total']==1
    c.post('/api/auth/logout',headers=h)
    c.post('/api/auth/register',json={'name':'Another Seller','email':'another@example.com','password':'anotherLongPassword42'})
    assert c.get('/api/actions').json()['total']==0
    assert c.get('/api/insights').json()['totals']['sales']==0


def test_local_live_status_does_not_linger_when_all_listings_removed(seller,item_input):
    c=seller['client'];h=seller['csrf']
    i=c.post('/api/items',json=item_input,headers=h).json()['id']
    for ch in ('grailed','depop'):
        c.put(f'/api/items/{i}/channels/{ch}',headers=h,json={'status':'manually_published','listing_url':''})
    assert c.get(f'/api/items/{i}').json()['status']=='active'
    c.put(f'/api/items/{i}/channels/depop',headers=h,json={'status':'delisted','listing_url':''})
    assert c.get(f'/api/items/{i}').json()['status']=='active'
    c.put(f'/api/items/{i}/channels/grailed',headers=h,json={'status':'delisted','listing_url':''})
    assert c.get(f'/api/items/{i}').json()['status']=='draft'
    assert c.get('/api/overview').json()['stats']['active']==0
    # Archival is now possible without falsely treating the item as live.
    assert c.delete(f'/api/items/{i}',headers=h).status_code==200
