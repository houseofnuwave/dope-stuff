"""v0.3: cover-photo order, portable backups, account deletion and privacy."""
import io
import json
import zipfile
from PIL import Image


def picture(color):
    buff=io.BytesIO()
    Image.new('RGB',(90,120),color).save(buff, format='PNG')
    return buff.getvalue()


def add_with_images(seller, item_input):
    c=seller['client']; h=seller['csrf']
    item=c.post('/api/items',headers=h,json=item_input).json()
    r=c.post(f"/api/items/{item['id']}/photos",headers=h,
       files=[('photos',('front.png',picture('blue'),'image/png')),
              ('photos',('back.png',picture('red'),'image/png'))])
    assert r.status_code==200,r.text
    return r.json()['item']


def test_make_cover_atomic_and_reject_invalid(seller,item_input):
    c=seller['client']; h=seller['csrf']
    item=add_with_images(seller,item_input)
    first,second=[x['id'] for x in item['photos']]
    original=c.get(f"/api/items/{item['id']}/photo").content
    url=f"/api/items/{item['id']}/photos/order"
    for bad in [[second,second],[second],[second,98765]]:
        response=c.put(url,headers=h,json={'photo_ids':bad})
        assert response.status_code==422, response.text
        assert c.get(f"/api/items/{item['id']}/photo").content==original
    assert c.put(url,json={'photo_ids':[second,first]}).status_code==403
    good=c.put(url,headers=h,json={'photo_ids':[second,first]})
    assert good.status_code==200,good.text
    assert [p['id'] for p in good.json()['item']['photos']]==[second,first]
    assert c.get(f"/api/items/{item['id']}/photo").content == c.get(f"/api/items/{item['id']}/photos/{second}").content
    assert c.get(f"/api/items/{item['id']}/photo").content!=original


def test_backup_includes_only_owner_and_not_password_hash(client,item_input):
    c=client
    assert c.get('/api/account/export.zip').status_code==401
    c.post('/api/auth/register',json={'name':'Primary Owner','email':'one@example.com','password':'ownerPassword123'})
    token={'x-csrf-token':c.get('/api/session').json()['csrf']}
    item=c.post('/api/items',headers=token,json=item_input).json()
    c.post(f"/api/items/{item['id']}/photos",headers=token,
           files=[('photos',('first.png',picture('blue'),'image/png'))])
    c.post('/api/feedback',headers=token,json={'rating':5,'message':'Helpful for listing tests'})
    backup=c.get('/api/account/export.zip')
    assert backup.status_code==200
    assert backup.headers['cache-control']=='no-store'
    with zipfile.ZipFile(io.BytesIO(backup.content)) as z:
        assert 'form_backup.json' in z.namelist()
        assert any(n.startswith('photos/item-') for n in z.namelist())
        data=json.loads(z.read('form_backup.json'))
        assert len(data['items'])==1
        assert data['items'][0]['sku']==item_input['sku']
        assert data['account']['email']=='one@example.com'
        assert 'password_hash' not in str(data)
        assert data['feedback'][0]['rating']==5
    c.post('/api/auth/logout',headers=token)
    c.post('/api/auth/register',json={'name':'Other Owner','email':'two@example.com','password':'secondPassword123'})
    with zipfile.ZipFile(io.BytesIO(c.get('/api/account/export.zip').content)) as z:
        second=json.loads(z.read('form_backup.json'))
        assert second['items']==[] and second['item_photos']==[] and second['feedback']==[]


def test_delete_requires_password_and_cascades_sales_photos(seller,item_input,tmp_path):
    c=seller['client']; h=seller['csrf']
    item=add_with_images(seller,item_input)
    first_photo=c.get(f"/api/items/{item['id']}/photo")
    assert first_photo.status_code==200
    c.post('/api/feedback',headers=h,json={'rating':3,'message':'Needs more work'})
    c.post(f"/api/items/{item['id']}/sale",headers=h,
           json={'channel':'other','sold_cents':42000,'fee_cents':1000,'ship_cents':0})
    url='/api/account/delete'
    body={'confirmation':'DELETE MY ACCOUNT','password':'longPassword123'}
    assert c.post(url,json=body).status_code==403
    assert c.post(url,headers=h,json={**body,'confirmation':'yes'}).status_code==422
    assert c.post(url,headers=h,json={**body,'password':'wrongPassword123'}).status_code==401
    assert c.get('/api/items').json()['total']==1
    response=c.post(url,headers=h,json=body)
    assert response.status_code==200, response.text
    assert c.get('/api/session').json()['authenticated'] is False
    assert c.get('/api/items').status_code==401
    assert not list((tmp_path/'photos').glob('*.webp'))
    c.post('/api/auth/register',json={'name':'New Seller','email':'seller@example.com','password':'longPassword123'})
    assert c.get('/api/items').json()['total']==0


def test_security_headers(client):
    r=client.get('/api/session')
    assert r.headers['x-frame-options']=='DENY'
    assert r.headers['x-content-type-options']=='nosniff'
    assert r.headers['cache-control']=='no-store'
