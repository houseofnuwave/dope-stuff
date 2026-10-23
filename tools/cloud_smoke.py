"""DESTRUCTIVE integration smoke for disposable PostgreSQL + S3/MinIO only.

Requires FORM_DATABASE_URL containing a database name ending _test,
FORM_S3_PREFIX beginning ci/, and FORM_CLOUD_SMOKE_ALLOW_DELETE=YES_ISOLATED_TEST_ENV.
Never run against real seller records or cloud production/staging databases.
"""
from __future__ import annotations
import io
import os
from unittest.mock import patch
from urllib.parse import urlparse


def main():
    db_url = os.getenv('FORM_DATABASE_URL','')
    prefix = os.getenv('FORM_S3_PREFIX','')
    if (os.getenv('FORM_CLOUD_SMOKE_ALLOW_DELETE') != 'YES_ISOLATED_TEST_ENV'
        or not urlparse(db_url).path.endswith('_test')
        or not prefix.startswith('ci/') or os.getenv('FORM_PHOTO_STORAGE') != 's3'
        or os.getenv('FORM_ENV','development') not in ('test','development')):
        raise RuntimeError('Refusing to run destructive smoke outside an isolated test DB/bucket prefix')

    from fastapi.testclient import TestClient
    from PIL import Image
    from app import db, photo_storage, photo_cleanup
    from app.main import app

    bucket=os.environ['FORM_S3_BUCKET']
    s3=photo_storage.s3_client()
    try:
        s3.head_bucket(Bucket=bucket)
    except Exception:
        s3.create_bucket(Bucket=bucket)

    with TestClient(app) as client:
        auth={'name':'CI Integration','email':'ci-cloud-smoke@example.com',
              'password':'throwaway-ci-password-012345',
              'invite_code':os.getenv('FORM_PILOT_INVITE_CODE','')}
        resp=client.post('/api/auth/register',json=auth)
        assert resp.status_code==200, resp.text
        token={'x-csrf-token':client.get('/api/session').json()['csrf']}
        item = {'sku':'CI-ONE','title':'Vintage cotton work jacket', 'brand':'Sample',
                'category':'Jacket','size':'M','color':'Blue','condition':'Like new',
                'price_cents':12500,'cost_cents':5000,'shipping_cents':800,
                'quantity':1, 'description':'Temporary test item, not real inventory.'}
        resp=client.post('/api/items',json=item,headers=token)
        assert resp.status_code==201,resp.text
        item_id=resp.json()['id']
        img=Image.new('RGB',(64,64),'white')
        b=io.BytesIO();img.save(b,'PNG')
        photo=client.post(f'/api/items/{item_id}/photos',headers=token,
                          files={'photos':('test.png',b.getvalue(),'image/png')})
        assert photo.status_code==200,photo.text
        got=client.get(f'/api/items/{item_id}/photo')
        assert got.status_code==200 and got.content[:4]==b'RIFF'
        assert client.get('/readyz').status_code==200
        backup=client.get('/api/account/export.zip')
        assert backup.status_code==200 and len(backup.content)>100
        listed=client.get('/api/items').json()
        assert listed['total']==1
        from tools.state_race_checks import assert_publish_sale_integrity, assert_double_sale_integrity
        assert_publish_sale_integrity(client, token, item)
        assert_double_sale_integrity(client, token, item)
        from tools.pagination_checks import assert_pagination_boundaries, assert_live_count_snapshot
        assert_pagination_boundaries(client)
        for kind in ('actions', 'sales'):
            assert_live_count_snapshot(client, kind)
        # Exercise the real PostgreSQL transaction with private S3 unavailable
        # during deletion, then recover against the same real object store.
        with patch.object(photo_storage, 'delete_photo', side_effect=OSError('test outage')):
            deleted=client.post('/api/account/delete',headers=token,json={
                'password':auth['password'],'confirmation':'DELETE MY ACCOUNT'})
        assert deleted.status_code==202,deleted.text
        assert deleted.json()['photo_cleanup_pending']==1
        assert client.get('/api/session').json()['authenticated'] is False
        with db.connect() as connection:
            tasks = connection.execute('SELECT file_path FROM photo_deletions').fetchall()
        names = [row['file_path'] for row in tasks]
        assert len(names)==1
        assert photo_storage.read_photo(names[0])[:4]==b'RIFF'
        assert photo_cleanup.process_pending(names=names)=={'completed':1,'pending':0}
        try:
            photo_storage.read_photo(names[0])
        except FileNotFoundError:
            pass
        else:
            raise AssertionError('Deleted account photo remains in object storage')
    print('CLOUD SMOKE PASSED: Postgres, private S3, inventory, export, concurrent sale/publication, deletion outage and retry.')


if __name__=='__main__': main()
