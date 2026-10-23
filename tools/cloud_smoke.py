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
        from tools.photo_write_checks import (assert_unknown_write_recovery, assert_active_write_protected,
            assert_double_restore_serialized, assert_upload_account_delete_serialized, assert_commit_acknowledgement_safe)
        assert_unknown_write_recovery(client, token, item)
        assert_active_write_protected(client, token, item)
        assert_commit_acknowledgement_safe(client, token, item)
        # Separate disposable account: these probes deliberately recreate/delete
        # their supplied account, never the main round-trip fixture below.
        with TestClient(app) as race_client:
            race_auth={**auth, 'email': 'ci-write-race@example.com'}
            registered=race_client.post('/api/auth/register',json=race_auth)
            assert registered.status_code==200,registered.text
            assert_double_restore_serialized(race_client, race_auth, item)
            race_token={'x-csrf-token':race_client.get('/api/session').json()['csrf']}
            assert_upload_account_delete_serialized(race_client, race_token, item, race_auth['password'])
        from tools.state_race_checks import assert_publish_sale_integrity, assert_double_sale_integrity
        assert_publish_sale_integrity(client, token, item)
        assert_double_sale_integrity(client, token, item)
        from tools.pagination_checks import assert_pagination_boundaries, assert_live_count_snapshot
        assert_pagination_boundaries(client)
        for kind in ('actions', 'sales'):
            assert_live_count_snapshot(client, kind)
        from tools.backup_checks import assert_export_snapshot
        assert_export_snapshot(client, token, item)
        large_backup=client.get('/api/account/export.zip')
        assert large_backup.status_code==200,large_backup.text
        with db.connect() as connection:
            expected_photos=connection.execute('SELECT COUNT(DISTINCT file_path) FROM item_photos').fetchone()[0]
        assert expected_photos>=2
        # Exercise the real PostgreSQL transaction with private S3 unavailable
        # during deletion, then recover against the same real object store.
        with patch.object(photo_storage, 'delete_photo', side_effect=OSError('test outage')):
            deleted=client.post('/api/account/delete',headers=token,json={
                'password':auth['password'],'confirmation':'DELETE MY ACCOUNT'})
        assert deleted.status_code==202,deleted.text
        assert deleted.json()['photo_cleanup_pending']==expected_photos
        assert client.get('/api/session').json()['authenticated'] is False
        with db.connect() as connection:
            tasks = connection.execute('SELECT file_path FROM photo_deletions').fetchall()
        names = [row['file_path'] for row in tasks]
        assert len(names)==expected_photos
        for name in names:
            assert photo_storage.read_photo(name)[:4]==b'RIFF'
        assert photo_cleanup.process_pending(names=names,limit=100)=={'completed':expected_photos,'pending':0}
        for name in names:
            try:
                photo_storage.read_photo(name)
            except FileNotFoundError:
                pass
            else:
                raise AssertionError('Deleted account photo remains in object storage')
        from tools.backup_checks import restore_after_deletion
        restored_headers=restore_after_deletion(client, auth, large_backup.content)
        recovered=[record for record in client.get('/api/items',params={'q':'CI-ONE'}).json()['items']
                   if record['sku']=='CI-ONE'][0]
        recovered_photo=client.get(f"/api/items/{recovered['id']}/photo")
        assert recovered_photo.status_code==200 and recovered_photo.content==got.content
        deleted_again=client.post('/api/account/delete',headers=restored_headers,json={
            'password':auth['password'],'confirmation':'DELETE MY ACCOUNT'})
        assert deleted_again.status_code==200,deleted_again.text
        assert photo_cleanup.pending()==0
    print('CLOUD SMOKE PASSED: Postgres/private S3, write-timeout recovery, active-write protection, restore/deletion races, pagination, large backup and complete recovery.')


if __name__=='__main__': main()
