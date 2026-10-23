"""v0.2 verified workflows: multi-photo inventory and safe import previews."""
import io
from PIL import Image


def image_bytes(color=(50,70,60), kind='PNG'):
    data=io.BytesIO()
    Image.new('RGB',(300,250),color).save(data,format=kind)
    return data.getvalue()


def test_gallery_multiple_private_delete_cover(seller,item_input):
    c=seller['client'];h=seller['csrf']
    i=c.post('/api/items',headers=h,json=item_input).json()['id']
    photos=[('photos',('front.png',image_bytes((10,20,30)),'image/png')),
            ('photos',('back.jpg',image_bytes((200,100,70),'JPEG'),'image/jpeg'))]
    res=c.post(f'/api/items/{i}/photos',headers=h,files=photos)
    assert res.status_code==200,res.text
    item=res.json()['item']
    assert item['photo_count']==2 and item['has_photo']
    assert len(item['photos'])==2
    original=c.get(f'/api/items/{i}/photo')
    assert original.status_code==200 and original.headers['content-type']=='image/webp'
    first,second=[p['id'] for p in item['photos']]
    assert c.get(f'/api/items/{i}/photos/{second}').status_code==200
    assert c.get(f'/api/items/{i}/photos/99999').status_code==404
    assert c.delete(f'/api/items/{i}/photos/{first}').status_code==403
    updated=c.delete(f'/api/items/{i}/photos/{first}',headers=h)
    assert updated.status_code==200
    assert updated.json()['item']['photo_count']==1
    assert c.get(f'/api/items/{i}/photo').content == c.get(f'/api/items/{i}/photos/{second}').content
    assert c.delete(f'/api/items/{i}/photos/{second}',headers=h).json()['item']['photo_count']==0
    assert c.get(f'/api/items/{i}/photo').status_code==404


def test_gallery_cap_and_atomic_invalid_batch(seller,item_input):
    c=seller['client'];h=seller['csrf']
    i=c.post('/api/items',headers=h,json=item_input).json()['id']
    mix=[('photos',('good.png',image_bytes(),'image/png')),
         ('photos',('bad.txt',b'not an image','text/plain'))]
    assert c.post(f'/api/items/{i}/photos',headers=h,files=mix).status_code==415
    assert c.get(f'/api/items/{i}').json()['photo_count']==0
    eight=[('photos',(f'view-{n}.png',image_bytes(),'image/png')) for n in range(8)]
    assert c.post(f'/api/items/{i}/photos',headers=h,files=eight).json()['item']['photo_count']==8
    assert c.post(f'/api/items/{i}/photos',headers=h,files=[('photos',('ninth.png',image_bytes(),'image/png'))]).status_code==409
    assert c.get(f'/api/items/{i}').json()['photo_count']==8


def test_gallery_owner_isolation(client,item_input):
    client.post('/api/auth/register',json={'name':'Seller A','email':'a@example.com','password':'password1234'})
    a=client.get('/api/session').json()['csrf']
    i=client.post('/api/items',headers={'x-csrf-token':a},json=item_input).json()['id']
    res=client.post(f'/api/items/{i}/photos',headers={'x-csrf-token':a},files=[('photos',('a.png',image_bytes(),'image/png'))])
    p=res.json()['item']['photos'][0]['id']
    client.post('/api/auth/logout',headers={'x-csrf-token':a})
    client.post('/api/auth/register',json={'name':'Seller B','email':'b@example.com','password':'password1234'})
    b=client.get('/api/session').json()['csrf']
    assert client.get(f'/api/items/{i}/photos/{p}').status_code==404
    assert client.delete(f'/api/items/{i}/photos/{p}',headers={'x-csrf-token':b}).status_code==404
    assert client.post(f'/api/items/{i}/photos',headers={'x-csrf-token':b},files=[('photos',('x.png',image_bytes(),'image/png'))]).status_code==404


def test_csv_dry_run_and_validation(seller):
    c=seller['client'];h=seller['csrf']
    sample='sku,title,price,cost,condition\nOWNER-01,Linen shirt,35.00,10.00,Good\nOWNER-02,Leather boots,100.00,40.00,Like new\n'
    args={'headers':h,'files':{'file':('own.csv',sample.encode(),'text/csv')}}
    r=c.post('/api/import-preview.csv',**args)
    assert r.status_code==200 and r.json()['ok'] and r.json()['ready']==2
    assert c.get('/api/items').json()['total']==0
    assert c.get('/api/import-template.csv').text.startswith('sku,title,brand')
    assert c.post('/api/import.csv',**args).json()['imported']==2
    dup=c.post('/api/import-preview.csv',**args).json()
    assert not dup['ok'] and dup['total']==2 and len(dup['issues'])==2
    assert c.get('/api/items').json()['total']==2
    invalid='sku,title,price\nCSV-11,Good item,50.00\nCSV-12,Bad price,not-a-number\n'
    preview=c.post('/api/import-preview.csv',headers=h,files={'file':('bad.csv',invalid.encode(),'text/csv')}).json()
    assert preview['total']==2 and preview['ready']==1 and preview['issues'][0]['row']==3
    failed=c.post('/api/import.csv',headers=h,files={'file':('bad.csv',invalid.encode(),'text/csv')})
    assert failed.status_code==422 and c.get('/api/items').json()['total']==2


def test_gallery_legacy_migration(tmp_path, monkeypatch):
    # Original v0.1 items.photo_path values are registered in galleries on next init.
    from app import db
    import sqlite3
    monkeypatch.setattr(db,'DATA_DIR',tmp_path)
    monkeypatch.setattr(db,'DB_PATH',tmp_path/'migration.db')
    db.init_db()
    with db.connect() as conn:
        conn.execute("INSERT INTO users(name,email,password_hash) VALUES ('A','a@example.com','fake')")
        conn.execute("INSERT INTO items(user_id,sku,title,photo_path) VALUES (1,'S1','Vintage top','old.webp')")
    db.init_db()
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM item_photos").fetchone()[0]==1
    db.init_db()
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM item_photos").fetchone()[0]==1
