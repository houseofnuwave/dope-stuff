"""FORM Seller OS pilot API.

Design constraints:
 - No unauthorized marketplace automation. Channels are honest manual workflows.
 - Data belongs to the authenticated seller; all item queries are owner-scoped.
 - No unimplemented AI, billing, or auto-delist claims.
"""
from __future__ import annotations
import csv
import asyncio
import hashlib
import logging
import smtplib
import ssl
from email.message import EmailMessage
import io
import json
import zipfile
import hmac
import os
import re
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from urllib.parse import urlparse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import FastAPI, Request, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError, field_validator
from typing import Literal
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.middleware.sessions import SessionMiddleware

from .db import init_db, connect, rowdict, DATA_DIR, postgres_enabled
from .backup import inspect_archive, MAX_ZIP_BYTES
from . import photo_storage, photo_cleanup

# EmailStr depends on email-validator. Avoid adding an undeclared package by using a small validator instead.
EMAIL = re.compile(r"^[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,}$")
CHANNELS = {
 "ebay": {"name":"eBay", "type":"assisted", "url":"https://www.ebay.com/sl/sell", "domain":"ebay.com"},
 "grailed": {"name":"Grailed", "type":"assisted", "url":"https://www.grailed.com/sell", "domain":"grailed.com"},
 "depop": {"name":"Depop", "type":"assisted", "url":"https://www.depop.com/sell/", "domain":"depop.com"},
 "facebook": {"name":"Facebook Marketplace", "type":"assisted", "url":"https://www.facebook.com/marketplace/create/item", "domain":"facebook.com"},
 "poshmark": {"name":"Poshmark", "type":"assisted", "url":"https://poshmark.com/create-listing", "domain":"poshmark.com"},
 "mercari": {"name":"Mercari", "type":"assisted", "url":"https://www.mercari.com/sell/", "domain":"mercari.com"},
 "vestiaire": {"name":"Vestiaire Collective", "type":"assisted", "url":"https://www.vestiairecollective.com/", "domain":"vestiairecollective.com"},
 "shopify": {"name":"Shopify", "type":"assisted", "url":"https://admin.shopify.com/", "domain":"shopify.com"},
}
ALLOWED_CONDITIONS = {"Unspecified","New with tags","New without tags","Like new","Good","Fair"}
ALLOWED_STATUS = {"not_started","ready","manually_published","delist_required","delisted"}
ph = PasswordHasher(time_cost=2, memory_cost=32768, parallelism=2)
failed_attempts: dict[str, list[float]] = {}
logger = logging.getLogger("form.recovery")

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    cleanup_worker = asyncio.create_task(photo_cleanup.retry_loop())
    try:
        yield
    finally:
        cleanup_worker.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_worker

# Fail closed in hosted staging and production. The local founder beta remains
# usable over 127.0.0.1 without requiring a domain or HTTPS.
ENVIRONMENT = os.getenv('FORM_ENV', 'development').strip().lower()
if ENVIRONMENT not in {'development', 'test', 'staging', 'production'}:
    raise RuntimeError('FORM_ENV must be development, test, staging or production')
production = ENVIRONMENT == 'production'
hosted = ENVIRONMENT in {'staging', 'production'}
session_secret = os.getenv('FORM_SESSION_SECRET', '')
cookie_secure = os.getenv('FORM_COOKIE_SECURE', 'false').lower() == 'true'
allowed_hosts = [host.strip().lower() for host in os.getenv('FORM_ALLOWED_HOSTS', '').split(',') if host.strip()]
public_origin = os.getenv('FORM_PUBLIC_ORIGIN', '').strip()
# Render supplies this exact host and HTTPS URL at runtime. For PRIVATE STAGING
# only, accept that provider-controlled identity as a safe default so deploys
# and Render readiness probes work before a custom domain is purchased.
render_host = os.getenv('RENDER_EXTERNAL_HOSTNAME','').lower().strip()
render_url = os.getenv('RENDER_EXTERNAL_URL','').strip()
if (ENVIRONMENT == 'staging' and os.getenv('RENDER') == 'true'
    and re.fullmatch(r'[a-z0-9-]+\.onrender\.com', render_host)
    and render_url == 'https://' + render_host):
    if render_host not in allowed_hosts:
        allowed_hosts.append(render_host)
    if not public_origin:
        public_origin = render_url
if hosted:
    if len(session_secret) < 32 or not cookie_secure:
        raise RuntimeError('Hosted mode requires FORM_SESSION_SECRET (32+ chars) and FORM_COOKIE_SECURE=true')
    if not allowed_hosts or not public_origin:
        raise RuntimeError('Hosted mode requires FORM_ALLOWED_HOSTS and FORM_PUBLIC_ORIGIN')
    parsed_origin = urlparse(public_origin)
    if (parsed_origin.scheme != 'https' or not parsed_origin.hostname or
            parsed_origin.hostname.lower() not in allowed_hosts or
            parsed_origin.path not in ('', '/') or parsed_origin.query or parsed_origin.fragment or
            parsed_origin.username or parsed_origin.password or
            any(host == '*' or host.startswith('*.') for host in allowed_hosts)):
        raise RuntimeError('Hosted mode requires a valid HTTPS origin matching an explicit trusted host')
    path = os.getenv('FORM_DATA_DIR', '')
    if not path or not Path(path).is_absolute():
        raise RuntimeError('Hosted mode requires an absolute mounted FORM_DATA_DIR path')
    # Cloud staging must never accidentally write to ephemeral SQLite or disk.
    if os.getenv('FORM_CLOUD_MODE', '').lower() == 'true':
        if not os.getenv('FORM_DATABASE_URL', '').startswith(('postgresql://','postgres://')):
            raise RuntimeError('Cloud mode requires managed PostgreSQL via FORM_DATABASE_URL')
        if os.getenv('FORM_PHOTO_STORAGE') != 's3':
            raise RuntimeError('Cloud mode requires private S3-compatible photo storage')
        if not all(os.getenv(key) for key in ('FORM_S3_BUCKET','FORM_S3_ENDPOINT','FORM_S3_ACCESS_KEY_ID','FORM_S3_SECRET_ACCESS_KEY')):
            raise RuntimeError('Cloud mode requires private bucket connection settings')
        if len(os.getenv('FORM_PILOT_INVITE_CODE','')) < 16:
            raise RuntimeError('Cloud staging requires a 16+ character pilot invite code')

# v0.7 recovery transports: local secure spool for offline founder tests,
# SMTP over TLS for hosted pilots, or disabled. No token is sent in an API response.
RECOVERY_MODE = os.getenv('FORM_RECOVERY_MODE', 'disabled' if hosted else 'local').lower().strip()
if RECOVERY_MODE not in {'disabled', 'local', 'smtp'}:
    raise RuntimeError('FORM_RECOVERY_MODE must be disabled, local or smtp')
if hosted and RECOVERY_MODE == 'local':
    raise RuntimeError('Hosted recovery cannot write emails to a local spool')
if RECOVERY_MODE == 'smtp':
    if not all(os.getenv(k) for k in ('FORM_SMTP_HOST', 'FORM_SMTP_USERNAME', 'FORM_SMTP_PASSWORD', 'FORM_SMTP_FROM')):
        raise RuntimeError('SMTP recovery requires host, username, password, and sender settings')
    if int(os.getenv('FORM_SMTP_PORT', '465')) not in (465, 587):
        raise RuntimeError('SMTP recovery requires TLS via port 465 or 587')

app = FastAPI(title='Dope Stuff Seller OS Pilot', version='1.0.0+recovery-v0.7',
              docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=session_secret or secrets.token_hex(32),
                   same_site='lax', https_only=cookie_secure, max_age=60*60*24*7)
if hosted:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts, www_redirect=False)
STATIC = Path(__file__).resolve().parent / 'static'
app.mount('/static', StaticFiles(directory=STATIC), name='static')

@app.middleware("http")
async def privacy_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
        "form-action 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; connect-src 'self'"
    )
    response.headers['X-Permitted-Cross-Domain-Policies'] = 'none'
    if hosted:
        # Enable HSTS only when externally served through a verified HTTPS domain.
        response.headers['Strict-Transport-Security'] = 'max-age=31536000'
    return response


class Credentials(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=10, max_length=200)
    @field_validator("email")
    @classmethod
    def valid_email(cls, v: str):
        v = v.strip().lower()
        if not EMAIL.fullmatch(v): raise ValueError("Enter a valid email address")
        return v

class RecoveryRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    @field_validator('email')
    @classmethod
    def validate_email(cls, email):
        email = email.strip().lower()
        if not EMAIL.fullmatch(email): raise ValueError('Enter a valid email address')
        return email

class RecoveryConfirm(BaseModel):
    token: str = Field(min_length=40, max_length=200)
    new_password: str = Field(min_length=12, max_length=200)

class Register(Credentials):
    name: str = Field(min_length=2,max_length=60)
    invite_code: str = Field(default="", max_length=200)
    @field_validator("name")
    @classmethod
    def valid_name(cls, v: str):
        value = v.strip()
        if len(value) < 2: raise ValueError("Name must contain at least two characters")
        return value

class ItemInput(BaseModel):
    title: str = Field(min_length=2,max_length=180)
    sku: str = Field(default="",max_length=64)
    brand: str = Field(default="",max_length=100)
    category: str = Field(default="",max_length=80)
    size: str = Field(default="",max_length=40)
    color: str = Field(default="",max_length=60)
    condition: str = Field(default="Unspecified")
    description: str = Field(default="",max_length=3000)
    notes: str = Field(default="",max_length=1000)
    price_cents: int = Field(ge=0, le=100_000_000)
    cost_cents: int = Field(default=0, ge=0, le=100_000_000)
    shipping_cents: int = Field(default=0, ge=0, le=100_000_000)
    quantity: int = Field(default=1,ge=0,le=999)
    @field_validator("condition")
    @classmethod
    def valid_condition(cls,v):
        if v not in ALLOWED_CONDITIONS: raise ValueError("Invalid condition")
        return v
    @field_validator("sku")
    @classmethod
    def valid_sku(cls,v):
        if v and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", v):
            raise ValueError("SKU may contain letters, numbers, hyphens, periods and underscores")
        return v

class ChannelInput(BaseModel):
    status: str
    listing_url: str = Field(default="",max_length=700)
    @field_validator("status")
    @classmethod
    def valid_status(cls,v):
        if v not in ALLOWED_STATUS: raise ValueError("Invalid status")
        return v

class SaleInput(BaseModel):
    channel: str
    sold_cents: int = Field(ge=0,le=100_000_000)
    fee_cents: int = Field(default=0,ge=0,le=100_000_000)
    ship_cents: int = Field(default=0,ge=0,le=100_000_000)

class FeedbackInput(BaseModel):
    rating: int = Field(ge=1,le=5)
    message: str = Field(min_length=5,max_length=2000)

class ReorderPhotosInput(BaseModel):
    photo_ids: list[int] = Field(min_length=1, max_length=8)

class PasswordChangeInput(BaseModel):
    current_password: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=12, max_length=200)

class DeleteAccountInput(BaseModel):
    password: str = Field(min_length=10, max_length=200)
    confirmation: Literal["DELETE MY ACCOUNT"]

class PilotInput(BaseModel):
    email: str
    @field_validator("email")
    @classmethod
    def valid_email(cls, v):
        v = v.strip().lower()
        if not EMAIL.fullmatch(v): raise ValueError("Invalid email")
        return v


def limiter(request: Request, purpose: str, max_requests: int=10):
    # Best-effort pilot rate limit. Production: shared Redis keyed by validated client IP.
    key = f"{purpose}:{request.client.host if request.client else 'unknown'}"
    now = time.monotonic()
    recent = [x for x in failed_attempts.get(key,[]) if now-x < 900]
    if len(recent) >= max_requests: raise HTTPException(429,"Too many attempts. Try again later.")
    recent.append(now)
    failed_attempts[key] = recent


def current_user(request: Request):
    uid = request.session.get("uid")
    if not uid: raise HTTPException(401,"Sign in to continue")
    with connect() as db:
        user = db.execute("SELECT id,name,email,session_version FROM users WHERE id=?",(uid,)).fetchone()
    # No session version means an old or invalid cookie. Fail closed.
    if not user or request.session.get('sv') != user['session_version']:
        raise HTTPException(401,"Session expired. Sign in again.")
    return {k:user[k] for k in ('id','name','email')}


def csrf(request: Request, user=Depends(current_user)):
    expected = request.session.get("csrf","")
    received = request.headers.get("x-csrf-token","")
    if not expected or not hmac.compare_digest(expected, received):
        raise HTTPException(403,"Missing or invalid CSRF token")
    return user


def user_item(db, uid:int, item_id:int, *, for_update=False):
    # Mutation callers must begin a transaction before requesting a row lock.
    # SQLite BEGIN IMMEDIATE already serializes writers; PostgreSQL needs an
    # explicit row lock so precondition checks cannot use stale item state.
    suffix = ' FOR UPDATE' if for_update and postgres_enabled() else ''
    item = db.execute("SELECT * FROM items WHERE id=? AND user_id=?" + suffix,(item_id,uid)).fetchone()
    if not item: raise HTTPException(404,"Item not found")
    return rowdict(item)


def listing_readiness(item, photos: int):
    """Advisory data-completeness checks, not AI authentication or condition verification."""
    checks = [
        {'label':'At least 3 original product photos', 'ok': photos >= 3},
        {'label':'A descriptive item title', 'ok': len(item['title'].strip()) >= 8},
        {'label':'Brand identified (or Unbranded)', 'ok': bool(item['brand'].strip())},
        {'label':'Size or dimensions entered', 'ok': bool(item['size'].strip())},
        {'label':'Condition explicitly verified', 'ok': item['condition'] in ALLOWED_CONDITIONS and item['condition'] != 'Unspecified'},
        {'label':'Factual description with condition details', 'ok': len(item['description'].strip()) >= 40 and 'SAMPLE DATA' not in item['description'].upper()},
        {'label':'Asking price entered', 'ok': item['price_cents'] > 0},
    ]
    complete = sum(int(x['ok']) for x in checks)
    return {'complete':complete,'total':len(checks),'checks':checks,
        'notice':'Readiness checks only; sellers remain responsible for listing accuracy and marketplace policy.'}


def serialize_item(db, item):
    item = dict(item)
    item["channels"] = {r["channel"]:{"status":r["status"],"listing_url":r["listing_url"]}
                        for r in db.execute("SELECT channel,status,listing_url FROM item_channels WHERE item_id=?",(item["id"],))}
    item["has_photo"] = bool(item.pop("photo_path"))
    item["photos"] = [{"id":r["id"], "url":f"/api/items/{item['id']}/photos/{r['id']}"}
        for r in db.execute("SELECT id FROM item_photos WHERE item_id=? ORDER BY position,id",(item["id"],))]
    item["photo_count"] = len(item["photos"])
    item["readiness"] = listing_readiness(item,item["photo_count"])
    return item


def create_item(db, user_id:int, payload:ItemInput):
    p = payload.model_dump()
    if not p["sku"]: p["sku"] = "FORM-" + secrets.token_hex(4).upper()
    fields = list(p.keys())
    created = db.execute(f"INSERT INTO items(user_id,{','.join(fields)}) VALUES (?,{','.join('?' for _ in fields)}) RETURNING id", [user_id]+[p[x] for x in fields])
    inserted = created.fetchone()
    item_id = inserted["id"] if postgres_enabled() else inserted[0]
    for channel in CHANNELS:
        db.execute("INSERT INTO item_channels(item_id,channel) VALUES (?,?)",(item_id,channel))
    return item_id


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC/"index.html")

@app.get('/livez')
def livez():
    """Process liveness; deliberately does not depend on external services."""
    return {'status':'ok'}

@app.get('/readyz')
def readyz():
    """Staging readiness: database schema is queryable and photo backend is reachable."""
    try:
        with connect() as db:
            if postgres_enabled():
                exists = db.execute("SELECT to_regclass('public.users')").fetchone()
                if not exists or not exists['to_regclass']:
                    raise RuntimeError('Database schema missing')
            else:
                if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'").fetchone():
                    raise RuntimeError('Database schema missing')
            db.execute('SELECT 1')
        photo_storage.storage_ready()
        return {'status':'ready'}
    except Exception as exc:
        raise HTTPException(503, 'Service temporarily unavailable') from exc

@app.get('/healthz')
def healthz():
    """Legacy status shape, with identical dependency validation."""
    readyz()
    return {'status':'ok'}

@app.get("/api/session")
def session(request:Request):
    try: user = current_user(request)
    except HTTPException: return {"authenticated":False,"user":None,"invite_required": bool(os.getenv('FORM_PILOT_INVITE_CODE')), "recovery_available": RECOVERY_MODE != "disabled", "recovery_local": RECOVERY_MODE == "local"}
    if not request.session.get("csrf"):
        request.session["csrf"] = secrets.token_urlsafe(32)
    return {"authenticated":True,"user":user,"csrf":request.session["csrf"], "recovery_available": RECOVERY_MODE != "disabled", "recovery_local": RECOVERY_MODE == "local"}

@app.post("/api/auth/register")
def register(p:Register,request:Request):
    limiter(request,"register",8)
    invite = os.getenv('FORM_PILOT_INVITE_CODE','')
    if invite and not hmac.compare_digest(p.invite_code, invite):
        raise HTTPException(403, "A valid pilot invitation is required")
    with connect() as db:
        try:
            db.execute("INSERT INTO users(name,email,password_hash) VALUES(?,?,?)",(p.name.strip(),p.email,ph.hash(p.password)))
        except sqlite3.IntegrityError: raise HTTPException(409,"An account with that email already exists")
        uid = db.execute("SELECT id FROM users WHERE email=?",(p.email,)).fetchone()[0]
    request.session.clear()
    request.session.update({"uid":uid,"sv":0,"csrf":secrets.token_urlsafe(32)})
    return {"ok":True}

@app.post("/api/auth/login")
def login(p:Credentials,request:Request):
    limiter(request,"login",16)
    with connect() as db:
        user = db.execute("SELECT * FROM users WHERE email=?",(p.email,)).fetchone()
    try:
        if not user: raise VerifyMismatchError("unknown")
        ph.verify(user["password_hash"],p.password)
    except (VerifyMismatchError, VerificationError):
        raise HTTPException(401,"Incorrect email or password")
    request.session.clear()
    request.session.update({"uid":user["id"],"sv":user["session_version"],"csrf":secrets.token_urlsafe(32)})
    return {"ok":True}

@app.post("/api/auth/logout")
def logout(request:Request, user=Depends(csrf)):
    request.session.clear()
    return {"ok":True}


@app.post("/api/account/password")
def change_password(p: PasswordChangeInput, request: Request, user=Depends(csrf)):
    """Reauthenticate and revoke all other signed session cookies."""
    limiter(request, "change-password", 8)
    if p.current_password == p.new_password:
        raise HTTPException(422, "Choose a different new password")
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        stored = db.execute("SELECT password_hash,session_version FROM users WHERE id=?",(user['id'],)).fetchone()
        try:
            if not stored: raise VerifyMismatchError('unknown')
            ph.verify(stored['password_hash'], p.current_password)
        except (VerifyMismatchError, VerificationError):
            raise HTTPException(401, "Incorrect current password")
        version = stored['session_version'] + 1
        db.execute("UPDATE users SET password_hash=?,session_version=? WHERE id=?",
                   (ph.hash(p.new_password),version,user['id']))
        # An already-issued recovery link must not survive a legitimate password change.
        db.execute('DELETE FROM password_resets WHERE user_id=?', (user['id'],))
        db.execute('COMMIT')
    request.session.clear()
    request.session.update({'uid':user['id'],'sv':version,'csrf':secrets.token_urlsafe(32)})
    return {'ok':True,'notice':'Password updated. Other signed-in sessions have been revoked.'}

def send_recovery_email(address: str, token: str):
    """Send via TLS or write to a private local outbox. Never log tokens."""
    origin = public_origin.rstrip('/') if hosted else 'http://127.0.0.1:8000'
    link = f"{origin}/#reset={token}"
    if RECOVERY_MODE == 'local':
        # File only contains test credentials in development. Never enabled on hosted deployments.
        mailbox = DATA_DIR / 'local-recovery-mail'
        mailbox.mkdir(parents=True, exist_ok=True, mode=0o700)
        try: mailbox.chmod(0o700)
        except OSError: pass
        filename = mailbox / (secrets.token_hex(12) + '.txt')
        fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            out.write(f'To: {address}\nSubject: Reset your Dope Stuff password\n\n{link}\n\nLink expires in 30 minutes.\n')
        return
    if RECOVERY_MODE != 'smtp':
        raise RuntimeError('Password recovery transport is disabled')
    message = EmailMessage()
    message['Subject'] = 'Reset your Dope Stuff password'
    message['From'] = os.environ['FORM_SMTP_FROM']
    message['To'] = address
    message.set_content('You requested a password reset for Dope Stuff.\n\n'
                        f'{link}\n\nThis link expires in 30 minutes and can be used once. '
                        'If this was not you, ignore this email.')
    host, port = os.environ['FORM_SMTP_HOST'], int(os.getenv('FORM_SMTP_PORT', '465'))
    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=8, context=context) as smtp:
            smtp.login(os.environ['FORM_SMTP_USERNAME'], os.environ['FORM_SMTP_PASSWORD'])
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=8) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            smtp.login(os.environ['FORM_SMTP_USERNAME'], os.environ['FORM_SMTP_PASSWORD'])
            smtp.send_message(message)


@app.post('/api/auth/recovery/request')
def request_recovery(payload: RecoveryRequest, request: Request):
    """Uniform response avoids leaking whether an email is a Dope Stuff account."""
    if RECOVERY_MODE == 'disabled':
        raise HTTPException(503, 'Password recovery is not configured yet')
    limiter(request, 'recovery-request', 5)
    # Lookups and token storage remain account-scoped. Never issue raw token in JSON.
    with connect() as db:
        row = db.execute('SELECT id FROM users WHERE email=?', (payload.email,)).fetchone()
        if row:
            token = secrets.token_urlsafe(48)
            digest = hashlib.sha256(token.encode('ascii')).hexdigest()
            now = int(time.time())
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM password_resets WHERE user_id=?', (row['id'],))
            db.execute('INSERT INTO password_resets(user_id,token_hash,expires_at,created_at) VALUES (?,?,?,?)',
                       (row['id'], digest, now + 1800, now))
            db.execute('COMMIT')
    if row:
        try:
            send_recovery_email(payload.email, token)
        except Exception:
            # Do not reveal account existence via error responses or mail traces.
            logger.error('Recovery email delivery failed; check email transport configuration')
    return {'ok': True, 'notice': 'If this email belongs to a Dope Stuff account, recovery instructions will be sent.'}


@app.post('/api/auth/recovery/confirm')
def confirm_recovery(payload: RecoveryConfirm, request: Request):
    if RECOVERY_MODE == 'disabled':
        raise HTTPException(503, 'Password recovery is not configured yet')
    limiter(request, 'recovery-confirm', 10)
    if not re.fullmatch(r'[A-Za-z0-9_-]{40,200}', payload.token):
        raise HTTPException(400, 'Invalid or expired recovery link')
    digest = hashlib.sha256(payload.token.encode('ascii')).hexdigest()
    now = int(time.time())
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        used = db.execute("""UPDATE password_resets SET consumed_at=?
            WHERE token_hash=? AND consumed_at IS NULL AND expires_at>?
            RETURNING user_id""", (now, digest, now)).fetchone()
        if not used:
            raise HTTPException(400, 'Invalid or expired recovery link')
        db.execute('UPDATE users SET password_hash=?,session_version=session_version+1 WHERE id=?',
                   (ph.hash(payload.new_password), used['user_id']))
        db.execute('DELETE FROM password_resets WHERE user_id=?', (used['user_id'],))
        db.execute('COMMIT')
    request.session.clear()
    return {'ok': True, 'notice': 'Password reset. All previous sessions were signed out. Please log in.'}


@app.get("/api/account/export.zip")
def export_account(user=Depends(current_user)):
    """Portable private backup: records, sales, status history and available images."""
    with connect() as db:
        items = [dict(r) for r in db.execute("SELECT * FROM items WHERE user_id=? ORDER BY id", (user['id'],))]
        channels = [dict(r) for r in db.execute("SELECT c.* FROM item_channels c JOIN items i ON i.id=c.item_id WHERE i.user_id=? ORDER BY c.item_id,c.channel", (user['id'],))]
        pictures = [dict(r) for r in db.execute("SELECT p.* FROM item_photos p JOIN items i ON i.id=p.item_id WHERE i.user_id=? ORDER BY p.item_id,p.position", (user['id'],))]
        sales = [dict(r) for r in db.execute("SELECT * FROM sales WHERE user_id=? ORDER BY id", (user['id'],))]
        feedback = [dict(r) for r in db.execute("SELECT * FROM feedback WHERE user_id=? ORDER BY id", (user['id'],))]
    # Explicitly exclude private password hashes and signing/session values.
    backup = {"format": "FORM Seller OS portable backup", "version": 1,
              "account": user, "items": items, "item_channels": channels,
              "item_photos": pictures, "sales": sales, "feedback": feedback,
              "readme": "Personal backup. Do not publicly share; may contain inventory costs, personal notes and photographs."}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("form_backup.json", json.dumps(backup, indent=2, ensure_ascii=False))
        for pic in pictures:
            file_name = Path(pic['file_path']).name
            try:
                encoded = photo_storage.read_photo(file_name)
            except FileNotFoundError:
                continue  # Existing v0.5 behavior for missing legacy photographs.
            archive.writestr(f"photos/item-{pic['item_id']}/photo-{pic['id']}.webp", encoded)
    output.seek(0)
    return StreamingResponse(output, media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="form_account_backup.zip"', "Cache-Control": "no-store"})


def validate_restored_channel(channel: str, status: str, url: str):
    if channel not in CHANNELS or status not in ALLOWED_STATUS or len(url) > 700:
        raise ValueError("Invalid marketplace channel")
    validate_listing_url(channel, url)


async def read_restore_file(file: UploadFile, user: dict):
    raw = await file.read(MAX_ZIP_BYTES + 1)
    return inspect_archive(raw, user['email'], validate_item=lambda item: ItemInput.model_validate(item),
        validate_channel_url=validate_restored_channel,
        validate_sale_channel=lambda channel: channel in CHANNELS or channel=='other',
        validate_image=encode_photo)


@app.post("/api/account/restore-preview")
async def restore_preview(file: UploadFile = File(...), user=Depends(csrf)):
    """Inspect one backup without writing to disk or database."""
    with connect() as db:
        if db.execute("SELECT COUNT(*) FROM items WHERE user_id=?", (user['id'],)).fetchone()[0] or db.execute("SELECT COUNT(*) FROM feedback WHERE user_id=?", (user['id'],)).fetchone()[0]:
            raise HTTPException(409, "Restoring is only allowed into an empty inventory and feedback account")
    archive = await read_restore_file(file, user)
    return {"ok":True, "summary":archive.metadata,
        "notice":"Preview only. No local or external marketplace records have been changed."}


@app.post("/api/account/restore")
async def restore_account(request: Request, file: UploadFile = File(...),
        password: str = Form(..., min_length=10, max_length=200),
        confirmation: str = Form(...), user=Depends(csrf)):
    """Reauthenticated, blank-account-only, atomic restore of a FORM v1 backup."""
    limiter(request, 'restore-account', 8)
    if confirmation != 'RESTORE MY DATA':
        raise HTTPException(422, "Type RESTORE MY DATA to confirm")
    with connect() as db:
        stored = db.execute("SELECT password_hash FROM users WHERE id=?", (user['id'],)).fetchone()
        try:
            if not stored: raise VerifyMismatchError("unknown")
            ph.verify(stored['password_hash'], password)
        except (VerifyMismatchError, VerificationError):
            raise HTTPException(401, "Incorrect account password")
        if db.execute("SELECT COUNT(*) FROM items WHERE user_id=?", (user['id'],)).fetchone()[0]:
            raise HTTPException(409, "Restoring requires an account with no existing inventory")
    backup = await read_restore_file(file, user)
    photo_names: dict[int, str] = {}
    try:
        # Use fresh, unguessable internal names rather than trusting paths in ZIP metadata.
        for old_id, encoded in backup.images.items():
            name = secrets.token_hex(16) + '.webp'
            photo_storage.save_photo(name, encoded)
            photo_names[old_id] = name
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT COUNT(*) FROM items WHERE user_id=?", (user['id'],)).fetchone()[0]:
                raise HTTPException(409, "Inventory changed during restore; no backup data was imported")
            if db.execute("SELECT COUNT(*) FROM feedback WHERE user_id=?", (user['id'],)).fetchone()[0]:
                raise HTTPException(409, "Please use a new account without existing feedback for a full restore")
            mapped = {}
            for entry in backup.items:
                item_id = create_item(db, user['id'], entry['model'])
                mapped[entry['old_id']] = item_id
                db.execute("""UPDATE items SET status=?, created_at=COALESCE(?,created_at),
                    updated_at=COALESCE(?,updated_at) WHERE id=?""", (entry['status'],entry['created_at'],
                    entry['updated_at'],item_id))
            for entry in backup.channels:
                db.execute("""UPDATE item_channels SET status=?,listing_url=?,updated_at=COALESCE(?,datetime('now'))
                    WHERE item_id=? AND channel=?""",
                    (entry['status'],entry['url'],entry['updated_at'],mapped[entry['old_id']],entry['channel']))
            for entry in backup.photos:
                db.execute("""INSERT INTO item_photos(item_id,file_path,position,created_at)
                    VALUES (?,?,?,COALESCE(?,datetime('now')))""",
                    (mapped[entry['item_id']],photo_names[entry['old_id']],entry['position'],entry['created_at']))
            for item_id in mapped.values():
                cover = db.execute("SELECT file_path FROM item_photos WHERE item_id=? ORDER BY position,id LIMIT 1", (item_id,)).fetchone()
                if cover:
                    db.execute("UPDATE items SET photo_path=? WHERE id=?", (cover['file_path'],item_id))
            for entry in backup.sales:
                db.execute("""INSERT INTO sales(item_id,user_id,channel,sold_cents,fee_cents,ship_cents,cost_cents,created_at)
                    VALUES (?,?,?,?,?,?,?,COALESCE(?,datetime('now')))""", (mapped[entry['old_id']],user['id'],entry['channel'],
                    entry['sold_cents'],entry['fee_cents'],entry['ship_cents'],entry['cost_cents'],entry['created_at']))
            for entry in backup.feedback:
                db.execute("""INSERT INTO feedback(user_id,rating,message,created_at)
                    VALUES (?,?,?,COALESCE(?,datetime('now')))""",
                    (user['id'],entry['rating'],entry['message'],entry['created_at']))
            db.execute('COMMIT')
    except Exception:
        # Transaction closes without COMMIT, so SQLite rolls it back.
        for name in photo_names.values():
            photo_storage.delete_photo(name)
        raise
    return {"ok":True,"restored":backup.metadata,
        "notice":"Dope Stuff records restored locally. External marketplace listings were NOT inspected, published, or changed. Verify all statuses manually."}


@app.post("/api/account/delete")
def delete_account(p: DeleteAccountInput, request: Request, response: Response, user=Depends(csrf)):
    """Reauthenticate; delete owner data and local photos; invalidate session."""
    limiter(request, "delete-account", 8)
    with connect() as db:
        stored = db.execute("SELECT password_hash FROM users WHERE id=?", (user['id'],)).fetchone()
        try:
            if not stored: raise VerifyMismatchError("unknown")
            ph.verify(stored['password_hash'], p.password)
        except (VerifyMismatchError, VerificationError):
            raise HTTPException(401, "Incorrect password")
        paths = [r['file_path'] for r in db.execute("""SELECT p.file_path FROM item_photos p
            JOIN items i ON i.id=p.item_id WHERE i.user_id=?""", (user['id'],))]
        # Legacy cover files may not have gallery references in older databases.
        paths.extend(r['photo_path'] for r in db.execute("SELECT photo_path FROM items WHERE user_id=? AND photo_path IS NOT NULL", (user['id'],)))
        db.execute("BEGIN IMMEDIATE")
        photo_cleanup.enqueue(db, [Path(name).name for name in paths])
        # Explicitly remove restricted child records before cascading inventory.
        db.execute("DELETE FROM sales WHERE user_id=?", (user['id'],))
        db.execute("DELETE FROM feedback WHERE user_id=?", (user['id'],))
        db.execute("DELETE FROM users WHERE id=?", (user['id'],))
        db.execute("DELETE FROM pilot_requests WHERE email=?", (user['email'],))
        db.execute("COMMIT")
    request.session.clear()
    cleanup = photo_cleanup.process_pending(names=[Path(name).name for name in paths])
    if cleanup['pending']:
        response.status_code = 202
    return {"ok": True, "photo_cleanup_pending": cleanup['pending'],
        "notice": ("Your account and inventory records were deleted. Private photo cleanup is queued for retry."
                   if cleanup['pending'] else "Your account, inventory records and active photo objects were deleted.")
                  + " External marketplace listings are unaffected."}

@app.get("/api/channels")
def channels(user=Depends(current_user)):
    return {"channels":CHANNELS,"mode":"Assisted publishing only. No live API connections."}

@app.get("/api/overview")
def overview(user=Depends(current_user)):
    with connect() as db:
        stats = db.execute("""SELECT COUNT(*) inventory,
          COALESCE(SUM(CASE WHEN status='sold' THEN 1 ELSE 0 END),0) sold,
          COALESCE(SUM(CASE WHEN status IN ('draft','active') THEN 1 ELSE 0 END),0) available,
          COALESCE(SUM(CASE WHEN status='active' THEN 1 ELSE 0 END),0) active,
          COALESCE(SUM(CASE WHEN status IN ('draft','active') THEN price_cents ELSE 0 END),0) inventory_value
          FROM items WHERE user_id=? AND status != 'archived'""",(user['id'],)).fetchone()
        finance=db.execute("""SELECT COUNT(*) sales,
          COALESCE(SUM(sold_cents),0) gross,
          COALESCE(SUM(sold_cents - fee_cents - ship_cents - cost_cents),0) profit
          FROM sales WHERE user_id=?""",(user['id'],)).fetchone()
        attention=db.execute("""SELECT COUNT(*) cnt FROM item_channels c JOIN items i ON i.id=c.item_id
          WHERE i.user_id=? AND c.status='delist_required'""",(user['id'],)).fetchone()['cnt']
        latest=db.execute("SELECT * FROM items WHERE user_id=? AND status!='archived' ORDER BY updated_at DESC,id DESC LIMIT 6",(user['id'],)).fetchall()
        return {"stats":dict(stats),"finance":dict(finance),"action_required":attention,"latest":[serialize_item(db,r) for r in latest]}

@app.get("/api/actions")
def manual_actions(user=Depends(current_user)):
    """Seller-confirmed live channels pending *manual* delisting after sale.
    No external marketplace is contacted or changed.
    """
    with connect() as db:
        total = db.execute("""SELECT COUNT(*) FROM item_channels c JOIN items i ON i.id=c.item_id
            WHERE i.user_id=? AND c.status='delist_required'""",(user['id'],)).fetchone()[0]
        rows = db.execute("""SELECT c.channel,c.listing_url,c.updated_at,i.id item_id,
            i.title,i.sku FROM item_channels c JOIN items i ON i.id=c.item_id
            WHERE i.user_id=? AND c.status='delist_required'
            ORDER BY c.updated_at ASC,i.id ASC,c.channel ASC LIMIT 200""",(user['id'],)).fetchall()
    return {'total':total,'actions':[{**dict(r),'display_name':CHANNELS[r['channel']]['name']} for r in rows],
            'notice':'Manual seller checklist only. Dope Stuff has not removed or verified any external listing.'}

@app.get("/api/insights")
def insights(user=Depends(current_user)):
    """Only realized, seller-entered transactions; never forecast future sales."""
    with connect() as db:
        rows = [dict(r) for r in db.execute("""SELECT channel,COUNT(*) sales,
            COALESCE(SUM(sold_cents),0) gross_cents,
            COALESCE(SUM(fee_cents),0) fee_cents,
            COALESCE(SUM(ship_cents),0) ship_cents,
            COALESCE(SUM(cost_cents),0) acquisition_cents,
            COALESCE(SUM(sold_cents-fee_cents-ship_cents-cost_cents),0) profit_cents
            FROM sales WHERE user_id=? GROUP BY channel ORDER BY gross_cents DESC,channel""",(user['id'],))]
        available = db.execute("""SELECT COUNT(*) count, COALESCE(SUM(cost_cents),0) cost_cents,
            COALESCE(SUM(price_cents),0) asking_cents,
            COALESCE(SUM(CASE WHEN condition='Unspecified' THEN 1 ELSE 0 END),0) unverified_condition
            FROM items WHERE user_id=? AND status IN ('draft','active')""",(user['id'],)).fetchone()
        delist = db.execute("""SELECT COUNT(*) FROM item_channels c JOIN items i ON i.id=c.item_id
            WHERE i.user_id=? AND c.status='delist_required'""",(user['id'],)).fetchone()[0]
    all_sales = sum(x['sales'] for x in rows)
    gross = sum(x['gross_cents'] for x in rows)
    profit = sum(x['profit_cents'] for x in rows)
    return {'channels':[{**x,'display_name': CHANNELS.get(x['channel'],{'name':'Other / Offline'})['name']} for x in rows],
            'totals':{'sales':all_sales,'gross_cents':gross,'profit_cents':profit,
                      'margin_pct':round(profit/gross*100,1) if gross else None},
            'available_inventory':dict(available),'manual_delists':delist,
            'disclaimer':'Figures reflect only manually recorded sales and user-entered costs; exclude taxes, returns, overhead and subscriptions. Unsold asking value is not earned revenue.'}

@app.get("/api/items")
def list_items(q:str="",status:str="all",limit:int=80,offset:int=0,user=Depends(current_user)):
    limit = max(1,min(limit,200)); offset=max(0,offset)
    if status not in {"all","draft","active","sold","archived"}: raise HTTPException(400,"Invalid filter")
    conditions=["user_id=?"];args=[user['id']]
    if status == "all": conditions.append("status!='archived'")
    else: conditions.append("status=?"); args.append(status)
    if q.strip():
        conditions.append("(title LIKE ? OR brand LIKE ? OR sku LIKE ?)")
        search="%"+q.strip()[:120]+"%"
        args.extend([search]*3)
    where=" AND ".join(conditions)
    with connect() as db:
        rows=db.execute(f"SELECT * FROM items WHERE {where} ORDER BY updated_at DESC,id DESC LIMIT ? OFFSET ?",args+[limit,offset]).fetchall()
        total=db.execute(f"SELECT COUNT(*) FROM items WHERE {where}",args).fetchone()[0]
        return {"items":[serialize_item(db,r) for r in rows],"total":total}

@app.get("/api/items/{item_id}")
def get_item(item_id:int,user=Depends(current_user)):
    with connect() as db: return serialize_item(db,user_item(db,user['id'],item_id))

@app.post("/api/items",status_code=201)
def add_item(p:ItemInput,user=Depends(csrf)):
    with connect() as db:
        try: item_id=create_item(db,user['id'],p)
        except sqlite3.IntegrityError: raise HTTPException(409,"SKU already used in your inventory")
        return serialize_item(db,user_item(db,user['id'],item_id))

@app.post("/api/items/{item_id}/duplicate", status_code=201)
def duplicate_item(item_id: int, user=Depends(csrf)):
    """Create an independent draft. Never clone photos, external links or sales."""
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        original = user_item(db, user['id'], item_id)
        fields = ItemInput.model_fields.keys()
        data = {key: original[key] for key in fields}
        data['sku'] = ''  # Server allocates a new unique SKU
        data['quantity'] = 1
        data['title'] = (original['title'][:171] + ' — Copy') if len(original['title']) > 171 else original['title'] + ' — Copy'
        new_id = create_item(db, user['id'], ItemInput.model_validate(data))
        db.execute('COMMIT')
        record = user_item(db,user['id'],new_id)
        return {'id':new_id,'item':serialize_item(db,record),
                'notice':'Independent draft created. Photos, external listings and sale history were not copied. Verify all details before publishing.'}

@app.put("/api/items/{item_id}")
def edit_item(item_id:int,p:ItemInput,user=Depends(csrf)):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        item=user_item(db,user['id'],item_id,for_update=True)
        if item['status']=='sold': raise HTTPException(409,"Sold items are locked; make accounting corrections outside this MVP")
        fields=p.model_dump()
        if not fields['sku']: fields['sku']=item['sku']
        try:
            db.execute("UPDATE items SET "+",".join(f"{x}=?" for x in fields)+",updated_at=datetime('now') WHERE id=?",list(fields.values())+[item_id])
        except sqlite3.IntegrityError: raise HTTPException(409,"SKU already used in your inventory")
        result = serialize_item(db,user_item(db,user['id'],item_id))
        db.execute('COMMIT')
        return result

@app.delete("/api/items/{item_id}")
def archive_item(item_id:int,user=Depends(csrf)):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        item=user_item(db,user['id'],item_id,for_update=True)
        if item['status']=='sold': raise HTTPException(409,"Sold items cannot be archived")
        live=db.execute("SELECT COUNT(*) FROM item_channels WHERE item_id=? AND status='manually_published'",(item_id,)).fetchone()[0]
        if live: raise HTTPException(409,"Remove all published listings before archiving")
        db.execute("UPDATE items SET status='archived',updated_at=datetime('now') WHERE id=?",(item_id,))
        db.execute('COMMIT')
    return {"ok":True,"message":"Archived. Not removed from external marketplaces."}

MAX_ITEM_PHOTOS = 8
MAX_PHOTO_BYTES = 6 * 1024 * 1024


def encode_photo(raw: bytes) -> bytes:
    """Validate/resize original image and strip EXIF/location metadata."""
    try:
        with Image.open(io.BytesIO(raw)) as img:
            if img.format not in {"JPEG", "PNG", "WEBP"}:
                raise HTTPException(415, "Use JPEG, PNG or WebP images")
            if img.width * img.height > 30_000_000:
                raise HTTPException(413, "Image dimensions too large")
            result = ImageOps.exif_transpose(img).convert("RGB")
            result.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            result.save(output, "WEBP", quality=87, method=4)
            return output.getvalue()
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(415, "Upload a valid JPEG, PNG or WebP image")


@app.post("/api/items/{item_id}/photos")
async def upload_photos(item_id: int, photos: list[UploadFile] = File(...), user=Depends(csrf)):
    if not photos or len(photos) > MAX_ITEM_PHOTOS:
        raise HTTPException(422, "Choose 1 to 8 photos at a time")
    # Validate ownership and capacity before decoding; repeat within the write transaction.
    with connect() as db:
        item = user_item(db, user['id'], item_id)
        if item['status'] in ('sold','archived'):
            raise HTTPException(409, "Cannot change photos on sold or archived items")
        count = db.execute("SELECT COUNT(*) FROM item_photos WHERE item_id=?", (item_id,)).fetchone()[0]
        if count + len(photos) > MAX_ITEM_PHOTOS:
            raise HTTPException(409, "An item can have up to 8 photos. Remove photos before adding more.")
    encoded = []
    for photo in photos:
        raw = await photo.read(MAX_PHOTO_BYTES + 1)
        if len(raw) > MAX_PHOTO_BYTES:
            raise HTTPException(413, "Each image must be 6 MB or smaller")
        encoded.append(encode_photo(raw))
    filenames = []
    try:
        for raw in encoded:
            name = secrets.token_hex(16) + ".webp"
            photo_storage.save_photo(name, raw)
            filenames.append(name)
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            item = user_item(db, user['id'], item_id, for_update=True)
            if item['status'] in ('sold','archived'):
                raise HTTPException(409, "Cannot change photos on sold or archived items")
            count = db.execute("SELECT COUNT(*) FROM item_photos WHERE item_id=?", (item_id,)).fetchone()[0]
            if count + len(filenames) > MAX_ITEM_PHOTOS:
                raise HTTPException(409, "Photo limit reached by another upload")
            for pos, name in enumerate(filenames, count):
                db.execute("INSERT INTO item_photos(item_id,file_path,position) VALUES (?,?,?)",(item_id,name,pos))
            if count == 0:
                db.execute("UPDATE items SET photo_path=? WHERE id=?",(filenames[0],item_id))
            db.execute("UPDATE items SET updated_at=datetime('now') WHERE id=?",(item_id,))
            db.execute("COMMIT")
            return {"ok": True, "uploaded":len(filenames), "item":serialize_item(db,user_item(db,user['id'],item_id))}
    except Exception:
        for name in filenames:
            photo_storage.delete_photo(name)
        raise


@app.post("/api/items/{item_id}/photo")
async def upload_photo(item_id: int, photo: UploadFile=File(...), user=Depends(csrf)):
    """Backwards-compatible single-file route; adds a gallery photo."""
    result = await upload_photos(item_id, [photo], user)
    return {"ok":True, "url":f"/api/items/{item_id}/photo", "photo_count":result['item']['photo_count']}


@app.get("/api/items/{item_id}/photo")
def get_photo(item_id:int,user=Depends(current_user)):
    with connect() as db: item=user_item(db,user['id'],item_id)
    if not item['photo_path']: raise HTTPException(404,"No photograph")
    try: image_bytes = photo_storage.read_photo(item['photo_path'])
    except FileNotFoundError: raise HTTPException(404, "Photo missing")
    return Response(image_bytes,media_type="image/webp",headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})


@app.get("/api/items/{item_id}/photos/{photo_id}")
def get_gallery_photo(item_id:int,photo_id:int,user=Depends(current_user)):
    with connect() as db:
        user_item(db,user['id'],item_id)
        photo=db.execute("SELECT file_path FROM item_photos WHERE id=? AND item_id=?",(photo_id,item_id)).fetchone()
        if not photo: raise HTTPException(404,"Photo not found")
    try: image_bytes = photo_storage.read_photo(photo['file_path'])
    except FileNotFoundError: raise HTTPException(404, "Photo missing")
    return Response(image_bytes,media_type="image/webp",headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})


@app.delete("/api/items/{item_id}/photos/{photo_id}")
def delete_gallery_photo(item_id:int,photo_id:int,response:Response,user=Depends(csrf)):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        item=user_item(db,user['id'],item_id,for_update=True)
        if item['status'] in ('sold','archived'):
            raise HTTPException(409,"Cannot change photos on sold or archived items")
        photo=db.execute("SELECT file_path FROM item_photos WHERE id=? AND item_id=?",(photo_id,item_id)).fetchone()
        if not photo: raise HTTPException(404,"Photo not found")
        photo_cleanup.enqueue(db, [photo['file_path']])
        db.execute("DELETE FROM item_photos WHERE id=?",(photo_id,))
        cover=db.execute("SELECT file_path FROM item_photos WHERE item_id=? ORDER BY position,id LIMIT 1",(item_id,)).fetchone()
        db.execute("UPDATE items SET photo_path=?,updated_at=datetime('now') WHERE id=?",(cover['file_path'] if cover else None,item_id))
        db.execute("COMMIT")
        updated=serialize_item(db,user_item(db,user['id'],item_id))
    cleanup = photo_cleanup.process_pending(names=[photo['file_path']])
    if cleanup['pending']:
        response.status_code = 202
    return {"ok":True,"item":updated,"photo_cleanup_pending":cleanup['pending']}



@app.put("/api/items/{item_id}/photos/order")
def reorder_gallery(item_id: int, p: ReorderPhotosInput, user=Depends(csrf)):
    """Atomic order update. The first photograph becomes the cover."""
    if len(set(p.photo_ids)) != len(p.photo_ids):
        raise HTTPException(422, "Each photograph may appear once")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        item = user_item(db, user['id'], item_id, for_update=True)
        if item['status'] in ('sold', 'archived'):
            raise HTTPException(409, "Cannot change photos on sold or archived items")
        rows = db.execute("SELECT id,file_path FROM item_photos WHERE item_id=? ORDER BY position,id", (item_id,)).fetchall()
        current = {r['id']: r['file_path'] for r in rows}
        if set(p.photo_ids) != set(current):
            raise HTTPException(422, "Supply every photo ID for this item exactly once")
        for position, photo_id in enumerate(p.photo_ids):
            db.execute("UPDATE item_photos SET position=? WHERE id=? AND item_id=?", (position, photo_id, item_id))
        db.execute("UPDATE items SET photo_path=?,updated_at=datetime('now') WHERE id=?",
                   (current[p.photo_ids[0]], item_id))
        db.execute("COMMIT")
        return {"ok": True, "item": serialize_item(db, user_item(db, user['id'], item_id))}

def validate_listing_url(channel:str,url:str):
    if not url: return
    try:
        parsed=urlparse(url)
        host=(parsed.hostname or '').lower()
        allowed=CHANNELS[channel]['domain']
        if parsed.scheme!='https' or parsed.username or parsed.password or (host!=allowed and not host.endswith('.'+allowed)):
            raise ValueError()
    except ValueError: raise HTTPException(422,"Listing URL must be an HTTPS link to the selected marketplace")

@app.put("/api/items/{item_id}/channels/{channel}")
def update_channel(item_id:int,channel:str,p:ChannelInput,user=Depends(csrf)):
    if channel not in CHANNELS: raise HTTPException(404,"Unknown marketplace")
    validate_listing_url(channel,p.listing_url)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        item=user_item(db,user['id'],item_id,for_update=True)
        if item['status']=='archived': raise HTTPException(409,"Archived item")
        if item['status']=='sold' and p.status in ('ready','manually_published'):
            raise HTTPException(409,"Cannot publish a sold item")
        db.execute("UPDATE item_channels SET status=?, listing_url=?, updated_at=datetime('now') WHERE item_id=? AND channel=?",
                   (p.status,p.listing_url,item_id,channel))
        if p.status=='manually_published' and item['status']=='draft':
            db.execute("UPDATE items SET status='active',updated_at=datetime('now') WHERE id=?",(item_id,))
        elif item['status']=='active':
            # An item's local Live state must always reflect at least one
            # seller-confirmed externally published channel.
            still_live = db.execute("SELECT 1 FROM item_channels WHERE item_id=? AND status='manually_published' LIMIT 1",(item_id,)).fetchone()
            if not still_live:
                db.execute("UPDATE items SET status='draft',updated_at=datetime('now') WHERE id=?",(item_id,))
        result = serialize_item(db,user_item(db,user['id'],item_id))
        db.execute('COMMIT')
        return result


def kit(item,channel,photos=0):
    descriptor=" ".join(x for x in [item['brand'].strip(),item['title'].strip()] if x)
    # If title already includes brand, avoid repeating it.
    if item['brand'] and item['brand'].lower() in item['title'].lower(): descriptor=item['title']
    title=" · ".join(x for x in [descriptor,item['size'] and "Size "+item['size']] if x)
    title=title[:80] if channel in ('ebay','depop') else title[:140]
    parts=[item['title'], "",*(f"{label}: {item[field]}" for label,field in
              [('Brand','brand'),('Size','size'),('Color','color'),('Condition','condition')]
              if item[field] and not (field=='condition' and item[field]=='Unspecified'))]
    if item['description'].strip(): parts.extend(["",item['description'].strip()])
    parts.extend(["", "Please review photos and measurements before purchasing."])
    description="\n".join(parts).strip()
    return {"title":title,"description":description,"readiness":listing_readiness(item,photos),"price_cents":item['price_cents'],"condition":item['condition'],
            "sku":item['sku'],"channel":channel,"destination":CHANNELS[channel]['url'],
            "disclaimer":"Assisted workflow only. Copy the listing into the marketplace and confirm publication manually."}

@app.get("/api/items/{item_id}/kit/{channel}")
def listing_kit(item_id:int,channel:str,user=Depends(current_user)):
    if channel not in CHANNELS: raise HTTPException(404,"Unknown marketplace")
    with connect() as db:
        item = user_item(db,user['id'],item_id)
        total = db.execute('SELECT COUNT(*) FROM item_photos WHERE item_id=?',(item_id,)).fetchone()[0]
        return kit(item,channel,total)

@app.post("/api/items/{item_id}/sale")
def mark_sold(item_id:int,p:SaleInput,user=Depends(csrf)):
    if p.channel not in CHANNELS and p.channel!='other': raise HTTPException(422,"Invalid channel")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        item=user_item(db,user['id'],item_id,for_update=True)
        if item['status'] in ('sold','archived'): raise HTTPException(409,"Item is already sold or archived")
        if item['quantity'] != 1: raise HTTPException(409,"Multi-quantity sales need a separate inventory model. Set quantity to 1 for pilot sales.")
        db.execute("INSERT INTO sales(item_id,user_id,channel,sold_cents,fee_cents,ship_cents,cost_cents) VALUES (?,?,?,?,?,?,?)",
                   (item_id,user['id'],p.channel,p.sold_cents,p.fee_cents,p.ship_cents,item['cost_cents']))
        db.execute("UPDATE items SET status='sold',quantity=0,updated_at=datetime('now') WHERE id=?",(item_id,))
        # No implied external delisting. Only previously marked live channels become actionable.
        db.execute("UPDATE item_channels SET status='delist_required',updated_at=datetime('now') WHERE item_id=? AND status='manually_published' AND channel!=?",(item_id,p.channel))
        if p.channel in CHANNELS:
            db.execute("UPDATE item_channels SET status='delisted',updated_at=datetime('now') WHERE item_id=? AND channel=?",(item_id,p.channel))
        db.execute("COMMIT")
        pending=db.execute("SELECT channel FROM item_channels WHERE item_id=? AND status='delist_required'",(item_id,)).fetchall()
    return {"ok":True,"net_profit_cents":p.sold_cents-p.fee_cents-p.ship_cents-item['cost_cents'],
            "manual_delist_channels":[CHANNELS[r['channel']]['name'] for r in pending],
            "notice":"Sale recorded locally. No external marketplace listing was automatically removed."}

@app.get("/api/sales")
def sales(user=Depends(current_user)):
    with connect() as db:
        rows=db.execute("""SELECT s.*,i.title,i.brand,i.sku FROM sales s JOIN items i ON i.id=s.item_id
             WHERE s.user_id=? ORDER BY s.created_at DESC,s.id DESC LIMIT 500""",(user['id'],)).fetchall()
    return {"sales":[dict(x) for x in rows]}


def protect_excel(value):
    value=str(value or "")
    return "'"+value if value.lstrip().startswith(('=','+','-','@')) else value

@app.get("/api/export.csv")
def export_csv(user=Depends(current_user)):
    with connect() as db:
        rows=db.execute("""SELECT sku,title,brand,category,size,color,condition,description,notes,
           price_cents,cost_cents,shipping_cents,quantity,status FROM items WHERE user_id=? ORDER BY id DESC""",(user['id'],)).fetchall()
    out=io.StringIO(); writer=csv.writer(out)
    headers=['sku','title','brand','category','size','color','condition','description','notes','price','cost','shipping','quantity','status']
    writer.writerow(headers)
    for r in rows:
        values=dict(r)
        writer.writerow([protect_excel(f"{values[k]/100:.2f}") if k in ('price_cents','cost_cents','shipping_cents')
                         else protect_excel(values[k]) for k in ['sku','title','brand','category','size','color','condition','description','notes']+['price_cents','cost_cents','shipping_cents','quantity','status']])
    return StreamingResponse(iter([out.getvalue()]),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="form_inventory.csv"','Cache-Control':'no-store'})

@app.get("/api/sales-export.csv")
def export_sales_csv(user=Depends(current_user)):
    with connect() as db:
        rows = db.execute("""SELECT s.created_at,i.sku,i.title,s.channel,s.sold_cents,
            s.fee_cents,s.ship_cents,s.cost_cents,
            (s.sold_cents-s.fee_cents-s.ship_cents-s.cost_cents) profit_cents
            FROM sales s JOIN items i ON i.id=s.item_id WHERE s.user_id=? ORDER BY s.id DESC""",
            (user['id'],)).fetchall()
    out=io.StringIO()
    writer=csv.writer(out)
    writer.writerow(['date','sku','title','channel','sold_usd','fees_usd','shipping_usd','acquisition_usd','net_profit_usd'])
    for r in rows:
        writer.writerow([protect_excel(r[k]) for k in ('created_at','sku','title','channel')]+
                        [f"{r[k]/100:.2f}" for k in ('sold_cents','fee_cents','ship_cents','cost_cents','profit_cents')])
    return StreamingResponse(iter([out.getvalue()]),media_type='text/csv',
        headers={'Content-Disposition':'attachment; filename="form_sales.csv"','Cache-Control':'no-store'})

CSV_HEADERS = ['sku','title','brand','category','size','color','condition','description','notes','price','cost','shipping','quantity']


@app.get("/api/import-template.csv")
def csv_template(user=Depends(current_user)):
    out=io.StringIO()
    csv.writer(out).writerow(CSV_HEADERS)
    return StreamingResponse(iter([out.getvalue()]),media_type='text/csv',
        headers={'Content-Disposition':'attachment; filename="form_inventory_template.csv"','Cache-Control':'no-store'})


async def parse_inventory_csv(file: UploadFile):
    raw=await file.read(1024*1024+1)
    if len(raw)>1024*1024: raise HTTPException(413,"CSV cannot exceed 1 MB")
    try:
        text=raw.decode('utf-8-sig')
        reader=csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or not {'title','price'}.issubset(reader.fieldnames):
            raise ValueError("CSV needs title and price columns")
        if len(reader.fieldnames)!=len(set(reader.fieldnames)):
            raise ValueError("CSV has duplicate column headings")
        rows=list(reader)
        if len(rows)>200: raise ValueError("Import at most 200 items per file")
    except (UnicodeDecodeError,ValueError,csv.Error) as e:
        raise HTTPException(422,str(e))
    converted, issues=[],[]
    for idx,r in enumerate(rows,2):
        try:
            if None in r: raise ValueError("too many columns")
            def money(k):
                from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
                try:
                    value=Decimal(str(r.get(k) or '0'))
                    if not value.is_finite(): raise ValueError()
                    result=int((value*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
                    if not 0<=result<=100_000_000: raise ValueError()
                    return result
                except (InvalidOperation,ValueError,OverflowError): raise ValueError(f"invalid {k}")
            payload=ItemInput(title=r.get('title') or '',sku=r.get('sku') or '',brand=r.get('brand') or '',
                category=r.get('category') or '',size=r.get('size') or '',color=r.get('color') or '',
                condition=r.get('condition') or 'Unspecified',description=r.get('description') or '',
                notes=r.get('notes') or '',price_cents=money('price'),cost_cents=money('cost'),
                shipping_cents=money('shipping'),quantity=int(r.get('quantity') or '1'))
            converted.append((idx,payload))
        except (ValidationError,ValueError,TypeError) as e:
            message=str(e)
            if isinstance(e,ValidationError):
                message='; '.join(f"{v['loc'][0]}: {v['msg']}" for v in e.errors())
            issues.append({'row':idx,'message':message[:300]})
    return len(rows),converted,issues


def csv_conflicts(db, user_id: int, converted, issues):
    existing={r['sku'] for r in db.execute("SELECT sku FROM items WHERE user_id=?",(user_id,))}
    seen=set()
    for line,payload in converted:
        sku=payload.sku
        if sku and sku in seen:
            issues.append({'row':line,'message':f'Duplicate SKU within CSV: {sku}'})
        elif sku and sku in existing:
            issues.append({'row':line,'message':f'SKU already exists in your inventory: {sku}'})
        if sku: seen.add(sku)
    return issues


@app.post("/api/import-preview.csv")
async def preview_csv(file:UploadFile=File(...),user=Depends(csrf)):
    total,converted,issues=await parse_inventory_csv(file)
    with connect() as db: csv_conflicts(db,user['id'],converted,issues)
    return {'ok':not issues and total>0,'total':total,
            'ready':total-len({x['row'] for x in issues}),
            'issues':issues[:50],
            'sample':[{'row':i,'title':p.title,'sku':p.sku or '(auto-generated)',
                'price_cents':p.price_cents} for i,p in converted[:5]],
            'notice':'Preview only. No items were created.'}


@app.post("/api/import.csv")
async def import_csv(file:UploadFile=File(...),user=Depends(csrf)):
    total,converted,issues=await parse_inventory_csv(file)
    if not total: raise HTTPException(422,"The CSV contains no inventory rows")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        csv_conflicts(db,user['id'],converted,issues)
        if issues:
            raise HTTPException(409 if all(x['message'].startswith(('Duplicate SKU','SKU already exists')) for x in issues) else 422,
                'Import validation failed: ' + '; '.join(f"Row {x['row']}: {x['message']}" for x in issues[:4]) + '. Nothing imported.')
        try:
            for _,p in converted: create_item(db,user['id'],p)
            db.execute('COMMIT')
        except sqlite3.IntegrityError:
            db.execute('ROLLBACK')
            raise HTTPException(409,"Duplicate SKU. Nothing imported.")
    return {"ok":True,"imported":len(converted)}


@app.post("/api/feedback")
def feedback(p:FeedbackInput,user=Depends(csrf)):
    with connect() as db:
        db.execute("INSERT INTO feedback(user_id,rating,message) VALUES(?,?,?)",(user['id'],p.rating,p.message.strip()))
    return {"ok":True}

@app.post("/api/pilot-request")
def pilot_request(p:PilotInput,request:Request):
    limiter(request,"pilot",12)
    with connect() as db:
        db.execute("INSERT OR IGNORE INTO pilot_requests(email) VALUES (?)",(p.email,))
    return {"ok":True,"message":"Pilot interest recorded. No payment has been taken."}
