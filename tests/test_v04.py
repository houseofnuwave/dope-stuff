"""v0.4: portable backup inspection, protected round-trip and atomic failure."""
import io
import json
import zipfile

from test_v03 import add_with_images


def backup_file(data: bytes):
    return {'file':('form_account_backup.zip', io.BytesIO(data),'application/zip')}


def register(client, email='seller@example.com'):
    r = client.post('/api/auth/register',json={'name':'Return Seller','email':email,'password':'longPassword123'})
    assert r.status_code == 200, r.text
    return {'x-csrf-token':client.get('/api/session').json()['csrf']}


def restore(client, token, data, password='longPassword123', confirmation='RESTORE MY DATA'):
    return client.post('/api/account/restore',headers=token,
        data={'password':password,'confirmation':confirmation},files=backup_file(data))


def archive_variant(data, update):
    """Change only JSON for adversarial archive tests."""
    output=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as dest:
        metadata=json.loads(source.read('form_backup.json'))
        update(metadata)
        for name in source.namelist():
            dest.writestr(name,json.dumps(metadata) if name=='form_backup.json' else source.read(name))
    return output.getvalue()


def test_backup_round_trip_preserves_photos_cover_sales_channels_and_feedback(seller,item_input,tmp_path):
    c=seller['client'];h=seller['csrf']
    item=add_with_images(seller,item_input)
    first,second=[x['id'] for x in item['photos']]
    c.put(f"/api/items/{item['id']}/photos/order",json={'photo_ids':[second,first]},headers=h)
    c.put(f"/api/items/{item['id']}/channels/depop",headers=h,
        json={'status':'manually_published','listing_url':'https://www.depop.com/products/seller-example/'})
    c.put(f"/api/items/{item['id']}/channels/ebay",headers=h,
        json={'status':'manually_published','listing_url':'https://www.ebay.com/itm/123456'})
    original_photo=c.get(f"/api/items/{item['id']}/photo").content
    c.post(f"/api/items/{item['id']}/sale",headers=h,json={'channel':'depop','sold_cents':28000,'fee_cents':3000,'ship_cents':900})
    c.post('/api/feedback',headers=h,json={'rating':4,'message':'The listing flow works'})
    data=c.get('/api/account/export.zip').content
    # Blank-only safeguard; neither preview nor restore can merge existing records.
    assert c.post('/api/account/restore-preview',headers=h,files=backup_file(data)).status_code==409
    assert restore(c,h,data).status_code==409
    deleted=c.post('/api/account/delete',headers=h,
        json={'password':'longPassword123','confirmation':'DELETE MY ACCOUNT'})
    assert deleted.status_code==200,deleted.text
    h=register(c)
    assert c.post('/api/account/restore-preview',files=backup_file(data)).status_code==403
    preview=c.post('/api/account/restore-preview',headers=h,files=backup_file(data))
    assert preview.status_code==200,preview.text
    assert preview.json()['summary']=={'items':1,'photos':2,'sales':1,'published':0,'manual_delists':1,'feedback':1,'email':'seller@example.com'}
    assert c.get('/api/items').json()['total']==0
    assert restore(c,h,data,password='badPassword123').status_code==401
    assert restore(c,h,data,confirmation='sure').status_code==422
    assert restore(c,{},data).status_code==403
    restored=restore(c,h,data)
    assert restored.status_code==200,restored.text
    new_item=c.get('/api/items').json()['items'][0]
    assert new_item['sku']==item_input['sku']
    assert new_item['status']=='sold'
    assert new_item['quantity']==0
    assert new_item['photo_count']==2
    assert c.get(f"/api/items/{new_item['id']}/photo").content==original_photo
    assert new_item['channels']['ebay']['status']=='delist_required'
    assert new_item['channels']['depop']['status']=='delisted'
    assert c.get('/api/overview').json()['finance']['profit']==28000-3000-900-12000
    assert c.get('/api/overview').json()['action_required']==1
    assert len(list((tmp_path/'photos').glob('*.webp')))==2
    # Round-trip again after restore, proving associations are rewritten, not stale IDs.
    with zipfile.ZipFile(io.BytesIO(c.get('/api/account/export.zip').content)) as z:
        payload=json.loads(z.read('form_backup.json'))
        assert len(payload['sales'])==1
        assert payload['feedback'][0]['message']=='The listing flow works'


def test_foreign_account_rejected_and_existing_records_unchanged(seller,item_input):
    c=seller['client'];h=seller['csrf']
    data=c.get('/api/account/export.zip').content
    attack=archive_variant(data,lambda d:d['account'].update(email='another@example.com'))
    response=restore(c,h,attack)
    assert response.status_code==422
    assert 'different email' in response.json()['detail']
    assert c.get('/api/items').json()['total']==0


def test_malicious_photo_path_and_damaged_image_rejected(seller,item_input,tmp_path):
    c=seller['client'];h=seller['csrf']
    item=add_with_images(seller,item_input)
    good=c.get('/api/account/export.zip').content
    c.post('/api/account/delete',headers=h,json={'password':'longPassword123','confirmation':'DELETE MY ACCOUNT'})
    h=register(c)
    altered=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(good)) as src, zipfile.ZipFile(altered,'w',zipfile.ZIP_DEFLATED) as dst:
        for name in src.namelist():
            dst.writestr(name, b'not an image' if name.endswith('.webp') else src.read(name))
    assert restore(c,h,altered.getvalue()).status_code==422
    traversal=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(good)) as src, zipfile.ZipFile(traversal,'w',zipfile.ZIP_DEFLATED) as dst:
        for name in src.namelist(): dst.writestr(name,src.read(name))
        dst.writestr('../../etc/passwd','attack')
    assert restore(c,h,traversal.getvalue()).status_code==422
    assert c.get('/api/items').json()['total']==0
    assert not list((tmp_path/'photos').glob('*.webp'))


def test_atomic_rollback_cleans_staged_images(seller,item_input,tmp_path,monkeypatch):
    from app import main
    c=seller['client'];h=seller['csrf']
    add_with_images(seller,item_input)
    data=c.get('/api/account/export.zip').content
    c.post('/api/account/delete',headers=h,json={'password':'longPassword123','confirmation':'DELETE MY ACCOUNT'})
    h=register(c)
    def fail_create(*args,**kwargs): raise RuntimeError('injected database failure')
    with monkeypatch.context() as patch:
        patch.setattr(main,'create_item',fail_create)
        try: restore(c,h,data)
        except RuntimeError as e: assert 'injected' in str(e)
        else: assert False,'Failure should propagate for operator detection'
    assert c.get('/api/items').json()['total']==0
    assert not list((tmp_path/'photos').glob('*.webp'))
    assert restore(c,h,data).status_code==200


def test_reject_duplicate_skus_and_inconsistent_sale_references(seller,item_input):
    c=seller['client'];h=seller['csrf']
    item=c.post('/api/items',headers=h,json=item_input).json()
    backup=c.get('/api/account/export.zip').content
    c.post('/api/account/delete',headers=h,json={'password':'longPassword123','confirmation':'DELETE MY ACCOUNT'})
    h=register(c)
    bad_sales=archive_variant(backup,lambda d:d['sales'].append({'item_id':item['id'],'channel':'depop','sold_cents':200,'fee_cents':0,'ship_cents':0,'cost_cents':0}))
    assert restore(c,h,bad_sales).status_code==422
    def duplicate(d):
        item=dict(d['items'][0]);item['id']=item['id']+500;d['items'].append(item)
    bad_skus=archive_variant(backup,duplicate)
    assert restore(c,h,bad_skus).status_code==422
    assert c.get('/api/items').json()['total']==0


def test_listing_quality_is_advisory_and_condition_is_not_assumed(seller,item_input):
    c=seller['client'];h=seller['csrf']
    raw=dict(item_input)
    raw.pop('condition')
    item=c.post('/api/items',headers=h,json=raw)
    assert item.status_code==201,item.text
    record=item.json()
    assert record['condition']=='Unspecified'
    assert record['readiness']['complete'] < record['readiness']['total']
    missing=[x['label'] for x in record['readiness']['checks'] if not x['ok']]
    assert any('Condition' in x for x in missing)
    kit=c.get(f"/api/items/{record['id']}/kit/depop").json()
    assert kit['condition']=='Unspecified'
    assert 'Condition: Unspecified' not in kit['description']
    assert kit['readiness']['complete']==record['readiness']['complete']
    raw['condition']='Good'
    updated=c.put(f"/api/items/{record['id']}",headers=h,json=raw)
    assert updated.status_code==200
    assert updated.json()['readiness']['complete']==record['readiness']['complete']+1
    # Old CSV samples without condition must NOT be silently classified as new merchandise.
    csvfile='title,price,sku,brand\nAnother jacket,50.00,UNVERIFIED-02,Unbranded\n'
    r=c.post('/api/import.csv',headers=h,files={'file':('inventory.csv',csvfile.encode(),'text/csv')})
    assert r.status_code==200
    conditions=[x['condition'] for x in c.get('/api/items').json()['items']]
    assert 'Unspecified' in conditions
