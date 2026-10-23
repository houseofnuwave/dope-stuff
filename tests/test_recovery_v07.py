"""Offline credential recovery security regressions (no external SMTP)."""
import hashlib
import os
import re
import time
from pathlib import Path
from fastapi.testclient import TestClient
from app import main, db


def _reset_link(client, email, folder):
    response=client.post('/api/auth/recovery/request',json={'email':email})
    assert response.status_code == 200, response.text
    assert 'token' not in response.text.lower()
    mail=list((folder/'local-recovery-mail').glob('*.txt'))
    assert mail, 'A known account should have received a local test message'
    raw=mail[-1].read_text()
    match=re.search(r'#reset=([A-Za-z0-9_-]{40,200})',raw)
    assert match, raw
    return match.group(1)


def test_recovery_is_generic_and_does_not_mail_unknown_user(client,tmp_path):
    before=client.post('/api/auth/recovery/request',json={'email':'missing@example.com'})
    assert before.status_code==200
    folder=tmp_path/'local-recovery-mail'
    assert not folder.exists()
    created=client.post('/api/auth/register',json={'name':'Test Owner','email':'owner@example.com','password':'SecureOldPassword123'})
    assert created.status_code==200
    actual=client.post('/api/auth/recovery/request',json={'email':'owner@example.com'})
    assert actual.status_code==200
    assert before.json()==actual.json()
    files=list(folder.glob('*.txt'))
    assert len(files)==1
    assert folder.stat().st_mode & 0o777==0o700
    assert files[0].stat().st_mode & 0o777==0o600


def test_password_recovery_revokes_other_sessions_and_cannot_be_reused(client,tmp_path):
    client.post('/api/auth/register',json={'name':'Test Owner','email':'owner@example.com','password':'SecureOldPassword123'})
    old_session=TestClient(main.app)
    try:
        assert old_session.post('/api/auth/login',json={'email':'owner@example.com','password':'SecureOldPassword123'}).status_code==200
        assert old_session.get('/api/session').json()['authenticated']
        token=_reset_link(client,'owner@example.com',tmp_path)
        with db.connect() as c:
            hashed=c.execute('SELECT token_hash FROM password_resets').fetchone()['token_hash']
        assert hashed==hashlib.sha256(token.encode()).hexdigest()
        assert token != hashed
        done=client.post('/api/auth/recovery/confirm',json={'token':token,'new_password':'MuchSaferNewPassword123'})
        assert done.status_code==200,done.text
        assert client.get('/api/session').json()['authenticated'] is False
        assert old_session.get('/api/session').json()['authenticated'] is False
        assert client.post('/api/auth/login',json={'email':'owner@example.com','password':'SecureOldPassword123'}).status_code==401
        assert client.post('/api/auth/login',json={'email':'owner@example.com','password':'MuchSaferNewPassword123'}).status_code==200
        assert client.post('/api/auth/recovery/confirm',json={'token':token,'new_password':'AnotherSecurePassword123'}).status_code==400
    finally: old_session.close()


def test_requesting_another_link_invalidates_earlier(client,tmp_path):
    client.post('/api/auth/register',json={'name':'Test Owner','email':'owner@example.com','password':'SecureOldPassword123'})
    first=_reset_link(client,'owner@example.com',tmp_path)
    for file in (tmp_path/'local-recovery-mail').iterdir(): file.unlink()
    second=_reset_link(client,'owner@example.com',tmp_path)
    assert second!=first
    assert client.post('/api/auth/recovery/confirm',json={'token':first,'new_password':'NewPassword123456'}).status_code==400
    assert client.post('/api/auth/recovery/confirm',json={'token':second,'new_password':'NewPassword123456'}).status_code==200


def test_expired_or_malformed_links_rejected(client,tmp_path):
    client.post('/api/auth/register',json={'name':'Test Owner','email':'owner@example.com','password':'SecureOldPassword123'})
    token=_reset_link(client,'owner@example.com',tmp_path)
    with db.connect() as c:
        c.execute('UPDATE password_resets SET expires_at=?',(int(time.time())-5,))
    assert client.post('/api/auth/recovery/confirm',json={'token':token,'new_password':'NewPassword123456'}).status_code==400
    assert client.post('/api/auth/recovery/confirm',json={'token':'not-valid','new_password':'NewPassword123456'}).status_code==422


def test_changed_password_revokes_existing_recovery_link(seller,tmp_path):
    c=seller['client']
    token=_reset_link(c,'seller@example.com',tmp_path)
    changed=c.post('/api/account/password',headers=seller['csrf'],json={'current_password':'longPassword123','new_password':'LongerOtherPassword123'})
    assert changed.status_code==200,changed.text
    assert c.post('/api/auth/recovery/confirm',json={'token':token,'new_password':'ThirdUniquePassword123'}).status_code==400


def test_reset_rejects_weak_password_before_consuming_token(client,tmp_path):
    client.post('/api/auth/register',json={'name':'Test Owner','email':'owner@example.com','password':'SecureOldPassword123'})
    token=_reset_link(client,'owner@example.com',tmp_path)
    rejected=client.post('/api/auth/recovery/confirm',json={'token':token,'new_password':'short'})
    assert rejected.status_code==422
    assert client.post('/api/auth/recovery/confirm',json={'token':token,'new_password':'SecureGoodPassword123'}).status_code==200


def test_recovery_pg_schema_and_sql_translation():
    assert 'CREATE TABLE IF NOT EXISTS password_resets' in db.PG_SCHEMA
    assert 'CREATE TABLE IF NOT EXISTS password_resets' in db.SCHEMA
    assert db.postgres_sql('UPDATE password_resets SET consumed_at=? WHERE token_hash=? RETURNING user_id') == 'UPDATE password_resets SET consumed_at=%s WHERE token_hash=%s RETURNING user_id'
