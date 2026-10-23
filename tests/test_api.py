import csv
import io
from PIL import Image


def test_health_and_anon(client):
    assert client.get('/healthz').json()['status']=='ok'
    assert client.get('/api/session').json()['authenticated'] is False
    assert client.get('/api/items').status_code == 401
    assert client.get('/').status_code==200


def test_account_security(client, item_input):
    assert client.post('/api/auth/register',json={'name':'A B','email':'a@b.com','password':'too-short'}).status_code==422
    assert client.post('/api/auth/register',json={'name':'A B','email':'a@b.com','password':'validpasswordabc'}).status_code==200
    assert client.post('/api/items',json=item_input).status_code==403
    token=client.get('/api/session').json()['csrf']
    assert client.post('/api/items',json=item_input,headers={'x-csrf-token':'forged'}).status_code==403
    assert client.post('/api/items',json=item_input,headers={'x-csrf-token':token}).status_code==201
    assert client.post('/api/auth/logout',headers={'x-csrf-token':token}).status_code==200
    assert client.get('/api/items').status_code==401
    assert client.post('/api/auth/login',json={'email':'a@b.com','password':'wrongPassword'}).status_code==401
    assert client.post('/api/auth/login',json={'email':'a@b.com','password':'validpasswordabc'}).status_code==200
    assert client.get('/api/items').json()['total']==1


def test_inventory_ownership(client, item_input):
    client.post('/api/auth/register',json={'name':'First User','email':'first@example.com','password':'longPassword123'})
    token=client.get('/api/session').json()['csrf']
    r=client.post('/api/items',json=item_input,headers={'x-csrf-token':token})
    item_id=r.json()['id'];assert r.status_code==201
    assert client.post('/api/items',json=item_input,headers={'x-csrf-token':token}).status_code==409
    client.post('/api/auth/logout',headers={'x-csrf-token':token})
    client.post('/api/auth/register',json={'name':'Second User','email':'second@example.com','password':'longPassword123'})
    token2=client.get('/api/session').json()['csrf']
    assert client.get(f'/api/items/{item_id}').status_code==404
    assert client.put(f'/api/items/{item_id}',json=item_input,headers={'x-csrf-token':token2}).status_code==404
    assert client.get(f'/api/items/{item_id}/kit/ebay').status_code==404
    assert client.get('/api/items').json()['items']==[]


def test_assisted_publishing_and_sale(seller,item_input):
    c=seller['client'];h=seller['csrf']
    it=c.post('/api/items',json=item_input,headers=h).json()
    i=it['id']
    kit=c.get(f'/api/items/{i}/kit/ebay').json()
    assert 'Sample' in kit['title']
    assert 'Like new' in kit['description']
    assert 'Assisted workflow only' in kit['disclaimer']
    bad=c.put(f'/api/items/{i}/channels/grailed',json={'status':'manually_published','listing_url':'https://attacker.tld/fake'},headers=h)
    assert bad.status_code==422
    for ch in ['grailed','depop']:
        r=c.put(f'/api/items/{i}/channels/{ch}',json={'status':'manually_published','listing_url':''},headers=h)
        assert r.status_code==200
    archived=c.delete(f'/api/items/{i}',headers=h)
    assert archived.status_code==409
    sale=c.post(f'/api/items/{i}/sale',json={'channel':'grailed','sold_cents':40000,'fee_cents':4000,'ship_cents':700},headers=h)
    assert sale.status_code==200
    assert sale.json()['net_profit_cents']==23300
    assert sale.json()['manual_delist_channels']==['Depop']
    assert 'No external marketplace' in sale.json()['notice']
    assert c.post(f'/api/items/{i}/sale',json={'channel':'grailed','sold_cents':40000},headers=h).status_code==409
    record=c.get(f'/api/items/{i}').json()
    assert record['channels']['depop']['status']=='delist_required'
    assert record['status']=='sold'
    confirmed=c.put(f'/api/items/{i}/channels/depop',json={'status':'delisted','listing_url':''},headers=h)
    assert confirmed.status_code==200
    assert c.get('/api/overview').json()['action_required']==0
    assert c.get('/api/sales').json()['sales'][0]['sold_cents']==40000


def test_image_access_and_processing(seller,item_input):
    c=seller['client'];h=seller['csrf'];i=c.post('/api/items',json=item_input,headers=h).json()['id']
    assert c.post(f'/api/items/{i}/photo',headers=h,files={'photo':('evil.exe',b'not-image','application/octet-stream')}).status_code==415
    src=io.BytesIO();Image.new('RGB',(640,480),(43,57,56)).save(src,format='PNG')
    r=c.post(f'/api/items/{i}/photo',headers=h,files={'photo':('photo.png',src.getvalue(),'image/png')})
    assert r.status_code==200
    img=c.get(f'/api/items/{i}/photo')
    assert img.status_code==200
    assert img.headers['content-type']=='image/webp'
    assert c.get(f'/api/items/{i}').json()['has_photo']


def test_csv_and_formula_protection(seller,item_input):
    c=seller['client'];h=seller['csrf']
    body='title,price,sku,brand\nFirst Item,55.50,CSV-001,Sample\nSecond Item,25.00,CSV-002,Sample\n'
    r=c.post('/api/import.csv',headers=h,files={'file':('products.csv',body.encode(),'text/csv')})
    assert r.status_code==200 and r.json()['imported']==2
    r=c.post('/api/import.csv',headers=h,files={'file':('products.csv',body.encode(),'text/csv')})
    assert r.status_code==409
    assert c.get('/api/items').json()['total']==2
    x=item_input.copy();x.update(sku='CSV-003',title='=HYPERLINK("bad")')
    c.post('/api/items',headers=h,json=x)
    r=c.get('/api/export.csv');assert r.status_code==200
    rows=list(csv.DictReader(io.StringIO(r.text)))
    assert rows[0]['title'].startswith("'=")
    assert rows[1]['price']=='25.00'


def test_feedback_and_pricing_waitlist(seller):
    c=seller['client'];h=seller['csrf']
    assert c.post('/api/feedback',json={'rating':5,'message':'This is useful for my workflow.'},headers=h).status_code==200
    assert c.post('/api/feedback',json={'rating':0,'message':'Hi!'},headers=h).status_code==422
    assert c.post('/api/pilot-request',json={'email':'customer@example.com'}).status_code==200
    assert c.post('/api/pilot-request',json={'email':'customer@example.com'}).status_code==200
    assert c.post('/api/pilot-request',json={'email':'not-an-email'}).status_code==422
