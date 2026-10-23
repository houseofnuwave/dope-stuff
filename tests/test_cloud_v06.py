"""Offline cloud adapter contract tests. Actual Postgres/MinIO runs in cloud CI."""
import io
import os
import sqlite3
from unittest.mock import patch

import pytest
from app import db, main, photo_storage


def test_pg_sql_compatibility_and_hybrid_rows():
    assert db.postgres_sql('BEGIN IMMEDIATE') == 'BEGIN'
    assert db.postgres_sql('SELECT * FROM users WHERE id=? AND email=?') == 'SELECT * FROM users WHERE id=%s AND email=%s'
    assert 'ON CONFLICT (email) DO NOTHING' in db.postgres_sql('INSERT OR IGNORE INTO pilot_requests(email) VALUES (?)')
    assert 'to_char(now()' in db.postgres_sql("UPDATE items SET updated_at=datetime('now') WHERE id=?")
    row = db.HybridRow({'id': 21, 'title': 'Jacket'})
    assert row[0] == row['id'] == 21
    assert row[1] == row['title'] == 'Jacket'


def test_pilot_registration_rejects_invalid_invite(client, monkeypatch):
    monkeypatch.setenv('FORM_PILOT_INVITE_CODE', 'founder-beta-code-with-entropy')
    session = client.get('/api/session').json()
    assert session['invite_required'] is True
    form = {'name':'Private Pilot','email':'invited@example.com','password':'longPassword123'}
    denied = client.post('/api/auth/register',json={**form,'invite_code':'wrong'})
    assert denied.status_code == 403
    accepted = client.post('/api/auth/register',json={**form,'invite_code':'founder-beta-code-with-entropy'})
    assert accepted.status_code == 200
    monkeypatch.delenv('FORM_PILOT_INVITE_CODE')


def test_storage_path_rejects_traversal():
    for name in ['../../settings.env', 'a/b.webp', '.hidden.webp', 'x\\x.webp']:
        with pytest.raises(ValueError): photo_storage.validated_name(name)
    assert photo_storage.validated_name('a4b5.webp') == 'a4b5.webp'
    assert photo_storage.validated_name('legacy.jpg') == 'legacy.jpg'


def test_cloud_credentials_required(monkeypatch):
    monkeypatch.setenv('FORM_PHOTO_STORAGE','s3')
    for key in ('FORM_S3_BUCKET','FORM_S3_ENDPOINT','FORM_S3_ACCESS_KEY_ID','FORM_S3_SECRET_ACCESS_KEY'):
        monkeypatch.delenv(key,raising=False)
    with pytest.raises(RuntimeError,match='credentials'):
        photo_storage.s3_client()


class FakeBody:
    def __init__(self,data): self.data=data
    def read(self, n): return self.data[:n]
    def close(self): pass


class FakeS3:
    def __init__(self): self.files={}
    def put_object(self, **kw):
        self.files[(kw['Bucket'],kw['Key'])]=kw['Body']
        assert kw['CacheControl']=='private, no-store'
        assert kw['ContentType']=='image/webp'
    def get_object(self, **kw): return {'Body': FakeBody(self.files[(kw['Bucket'],kw['Key'])])}
    def delete_object(self, **kw): self.files.pop((kw['Bucket'],kw['Key']),None)
    def head_bucket(self, **kw): return {}


def test_s3_private_upload_retrieve_and_delete(monkeypatch):
    fake=FakeS3()
    monkeypatch.setenv('FORM_PHOTO_STORAGE','s3')
    monkeypatch.setenv('FORM_S3_BUCKET','private-test-bucket')
    monkeypatch.setenv('FORM_S3_PREFIX','isolated-beta')
    monkeypatch.setattr(photo_storage,'s3_client',lambda:fake)
    photo_storage.save_photo('abc.webp',b'WebP')
    assert photo_storage.storage_ready() is True
    assert photo_storage.read_photo('abc.webp') == b'WebP'
    assert ('private-test-bucket','isolated-beta/photos/abc.webp') in fake.files
    photo_storage.delete_photo('abc.webp')
    assert fake.files == {}


def test_s3_requires_authenticated_owner_for_item_image(seller, item_input, monkeypatch):
    from PIL import Image
    fake=FakeS3()
    monkeypatch.setenv('FORM_PHOTO_STORAGE','s3')
    monkeypatch.setenv('FORM_S3_BUCKET','private-test-bucket')
    monkeypatch.setenv('FORM_S3_PREFIX','isolated-beta')
    monkeypatch.setattr(photo_storage,'s3_client',lambda:fake)
    c=seller['client']
    item=c.post('/api/items',json=item_input,headers=seller['csrf']).json()
    img=Image.new('RGB',(40,40),'white')
    buffer=io.BytesIO();img.save(buffer,format='PNG')
    r=c.post(f"/api/items/{item['id']}/photos",headers=seller['csrf'],files={'photos':('photo.png',buffer.getvalue(),'image/png')})
    assert r.status_code==200, r.text
    stored=c.get(f"/api/items/{item['id']}/photo")
    assert stored.status_code == 200
    assert stored.content[:4] == b'RIFF'
    assert 'no-store' in stored.headers['cache-control']
    other=__import__('fastapi').testclient.TestClient(main.app)
    try:
        assert other.get(f"/api/items/{item['id']}/photo").status_code == 401
        owner_backup=c.get('/api/account/export.zip')
        assert owner_backup.status_code == 200
        assert any(n.startswith('photos/') for n in __import__('zipfile').ZipFile(io.BytesIO(owner_backup.content)).namelist())
    finally:
        other.close()


def test_backup_cli_refuses_cloud_backend(monkeypatch,tmp_path):
    from tools.ops_backup import gather_snapshot, BackupError
    monkeypatch.setenv('FORM_PHOTO_STORAGE','s3')
    with pytest.raises(BackupError,match='Legacy'):
        gather_snapshot(tmp_path)
