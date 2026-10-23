"""Infrastructure milestone: disaster recovery and hosted configuration tests."""
from __future__ import annotations
import base64
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import zipfile

import pytest
from app import db
from tools import ops_backup
import io
from PIL import Image

def image_bytes():
    out=io.BytesIO()
    Image.new('RGB',(100,100),(78,91,76)).save(out,format='PNG')
    return out.getvalue()


def test_health_endpoints_and_headers(seller):
    client = seller['client']
    assert client.get('/livez').json() == {'status':'ok'}
    assert client.get('/readyz').json() == {'status':'ready'}
    assert client.get('/healthz').json() == {'status':'ok'}
    res=client.get('/')
    assert 'script-src' in res.headers['content-security-policy']
    assert res.headers['x-frame-options']=='DENY'
    assert 'strict-origin' in res.headers['referrer-policy']


def test_readiness_fails_when_db_unavailable(seller,monkeypatch,tmp_path):
    client=seller['client']
    monkeypatch.setattr(db,'DB_PATH',tmp_path/'missing'/'db.sqlite')
    # sqlite can't open when the directory is missing; readiness must be 503.
    assert client.get('/livez').status_code == 200
    assert client.get('/readyz').status_code == 503


def test_encrypted_operations_backup_recovery(seller, item_input, monkeypatch, tmp_path):
    client=seller['client']; headers=seller['csrf']
    item=client.post('/api/items',json=item_input,headers=headers).json()
    iid=item['id']
    upload=client.post(f'/api/items/{iid}/photos',headers=headers,
        files=[('photos',('front.png',image_bytes(),'image/png'))])
    assert upload.status_code==200
    monkeypatch.setenv('FORM_BACKUP_KEY',base64.b64encode(secrets.token_bytes(32)).decode())
    backup_file=tmp_path/'operations.formbak'
    result=ops_backup.create_backup(backup_file)
    assert result['photo_count']==1 and backup_file.exists()
    content=backup_file.read_bytes()
    assert content.startswith(ops_backup.MAGIC)
    assert b'seller@example.com' not in content
    assert b'SQLite format 3' not in content
    verified=ops_backup.verify_backup(backup_file)
    assert verified['photos']==1
    recovery=tmp_path/'restore-rehearsal'
    restored=ops_backup.extract_rehearsal(backup_file,recovery)
    assert restored['photos']==1
    assert len(list((recovery/'photos').glob('*.webp')))==1
    with sqlite3.connect(recovery/'database'/'form.db') as conn:
        assert conn.execute("SELECT title FROM items WHERE id=?",(iid,)).fetchone()[0] == item_input['title']
    with pytest.raises(ops_backup.BackupError,match='already exists'):
        ops_backup.extract_rehearsal(backup_file,recovery)
    with pytest.raises(ops_backup.BackupError,match='overwrite'):
        ops_backup.create_backup(backup_file)


def test_ops_backup_detects_wrong_key_and_tampering(seller,monkeypatch,tmp_path):
    key=base64.b64encode(secrets.token_bytes(32)).decode()
    monkeypatch.setenv('FORM_BACKUP_KEY',key)
    p=tmp_path/'backup.formbak';ops_backup.create_backup(p)
    altered=bytearray(p.read_bytes());altered[len(altered)//2] ^= 1
    tampered=tmp_path/'tampered.formbak';tampered.write_bytes(altered)
    with pytest.raises(ops_backup.BackupError,match='authentication failed'):
        ops_backup.verify_backup(tampered)
    monkeypatch.setenv('FORM_BACKUP_KEY',base64.b64encode(secrets.token_bytes(32)).decode())
    with pytest.raises(ops_backup.BackupError,match='authentication failed'):
        ops_backup.verify_backup(p)
    monkeypatch.setenv('FORM_BACKUP_KEY','too-short')
    with pytest.raises(ops_backup.BackupError,match='base64'):
        ops_backup.verify_backup(p)


def test_ops_backup_missing_photo_does_not_publish(seller,item_input,monkeypatch,tmp_path):
    client=seller['client'];headers=seller['csrf']
    iid=client.post('/api/items',json=item_input,headers=headers).json()['id']
    with db.connect() as con:
        con.execute("UPDATE items SET photo_path='missing.webp' WHERE id=?",(iid,))
    monkeypatch.setenv('FORM_BACKUP_KEY',base64.b64encode(secrets.token_bytes(32)).decode())
    dest=tmp_path/'missing.formbak'
    with pytest.raises(ops_backup.BackupError,match='Missing'):
        ops_backup.create_backup(dest)
    assert not dest.exists()


def test_hosted_mode_rejects_insecure_config(tmp_path):
    # Import configuration in a new interpreter, independent of TestClient env.
    import os
    script='from app import main; print(main.ENVIRONMENT)'
    env=dict(os.environ, FORM_ENV='staging', FORM_SESSION_SECRET='short',
             FORM_COOKIE_SECURE='false',FORM_ALLOWED_HOSTS='stage.example.com',
             FORM_PUBLIC_ORIGIN='https://stage.example.com',FORM_DATA_DIR=str(tmp_path))
    r=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,env=env,timeout=20)
    assert r.returncode!=0 and 'Hosted mode requires FORM_SESSION_SECRET' in r.stderr
    env.update(FORM_SESSION_SECRET=secrets.token_urlsafe(48),FORM_COOKIE_SECURE='true')
    r=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,env=env,timeout=20)
    assert r.returncode==0,r.stderr
    assert r.stdout.strip()=='staging'
    env['FORM_ALLOWED_HOSTS']='*'
    r=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,env=env,timeout=20)
    assert r.returncode!=0
