"""Private photo storage: local developer disk or S3-compatible private bucket.

Only opaque, server-generated .webp names are accepted. No public object URLs or
client-side AWS credentials. Authorization happens in API handlers before reads.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
from urllib.parse import urlparse
from . import db

PHOTO_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,95}\.(webp|png|jpg|jpeg)$', re.IGNORECASE)
MAX_STORED_PHOTO_BYTES = 8 * 1024 * 1024


class PhotoTooLarge(RuntimeError):
    """Stored data exceeds the reader's bounded resource budget."""


def photo_backend():
    backend = os.getenv('FORM_PHOTO_STORAGE', 'local').lower().strip()
    if backend not in ('local', 's3'):
        raise RuntimeError('FORM_PHOTO_STORAGE must be local or s3')
    return backend


def validated_name(name: str) -> str:
    if not isinstance(name, str) or not PHOTO_NAME.fullmatch(name) or '..' in name:
        raise ValueError('Invalid internal photograph name')
    return name



def validate_hosted_s3_endpoint(endpoint: str) -> None:
    """Never send private object-store credentials over plaintext in hosted mode.

    Local development and isolated CI may use HTTP MinIO. Staging/production
    require an HTTPS origin, without embedded credentials or URL components
    that could redirect storage operations away from the intended endpoint.
    """
    if os.getenv('FORM_ENV', 'development').strip().lower() not in ('staging', 'production'):
        return
    try:
        if not endpoint or any(char.isspace() for char in endpoint):
            raise ValueError('Invalid endpoint')
        parsed = urlparse(endpoint)
        if (parsed.scheme != 'https' or not parsed.hostname or
                parsed.username is not None or parsed.password is not None or
                parsed.path not in ('', '/') or parsed.params or parsed.query or
                parsed.fragment or '*' in parsed.hostname):
            raise ValueError('Invalid endpoint')
        # Accessing port validates numeric range, including malformed host:port.
        parsed.port
    except ValueError as exc:
        # Do not echo the endpoint: it could contain embedded secrets.
        raise RuntimeError('Hosted S3 endpoint must be a credential-free HTTPS origin') from exc

def s3_client():
    required = ('FORM_S3_BUCKET', 'FORM_S3_ENDPOINT',
                'FORM_S3_ACCESS_KEY_ID', 'FORM_S3_SECRET_ACCESS_KEY')
    if any(not os.getenv(k) for k in required):
        raise RuntimeError('Private object storage credentials are not configured')
    validate_hosted_s3_endpoint(os.environ['FORM_S3_ENDPOINT'])
    import boto3
    from botocore.config import Config
    return boto3.client('s3',
        endpoint_url=os.environ['FORM_S3_ENDPOINT'],
        aws_access_key_id=os.environ['FORM_S3_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['FORM_S3_SECRET_ACCESS_KEY'],
        region_name=os.getenv('FORM_S3_REGION', 'auto'),
        config=Config(signature_version='s3v4', connect_timeout=4,
                      read_timeout=8, retries={'max_attempts': 2}))


def object_key(name: str) -> str:
    validated_name(name)
    prefix = os.getenv('FORM_S3_PREFIX', 'staging').strip('/')
    if not re.fullmatch(r'[A-Za-z0-9/_-]{1,100}', prefix) or '..' in prefix:
        raise RuntimeError('FORM_S3_PREFIX has invalid characters')
    return f'{prefix}/photos/{name}'


def save_photo(name: str, payload: bytes):
    validated_name(name)
    if not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_STORED_PHOTO_BYTES:
        raise ValueError('Invalid processed photograph')
    if photo_backend() == 's3':
        s3_client().put_object(Bucket=os.environ['FORM_S3_BUCKET'], Key=object_key(name),
                               Body=payload, ContentType='image/webp',
                               CacheControl='private, no-store')
    else:
        dest = db.DATA_DIR / 'photos'
        dest.mkdir(parents=True, exist_ok=True)
        (dest / name).write_bytes(payload)


def read_photo(name: str) -> bytes:
    validated_name(name)
    if photo_backend() == 's3':
        from botocore.exceptions import ClientError
        try:
            resp = s3_client().get_object(Bucket=os.environ['FORM_S3_BUCKET'], Key=object_key(name))
            try:
                content = resp['Body'].read(MAX_STORED_PHOTO_BYTES + 1)
            finally:
                resp['Body'].close()
            if len(content) > MAX_STORED_PHOTO_BYTES:
                raise PhotoTooLarge('Stored photograph is oversized')
            return content
        except ClientError as exc:
            if exc.response.get('Error', {}).get('Code') in ('NoSuchKey','404','NotFound'):
                raise FileNotFoundError('Photograph missing') from exc
            raise
    path = db.DATA_DIR / 'photos' / name
    try:
        if path.is_symlink():
            raise FileNotFoundError('Unsafe photo path')
        with path.open('rb') as source:
            content = source.read(MAX_STORED_PHOTO_BYTES + 1)
        if len(content) > MAX_STORED_PHOTO_BYTES:
            raise PhotoTooLarge('Stored photograph is oversized')
        return content
    except FileNotFoundError:
        raise


def delete_photo(name: str):
    validated_name(name)
    if photo_backend() == 's3':
        s3_client().delete_object(Bucket=os.environ['FORM_S3_BUCKET'], Key=object_key(name))
    else:
        (db.DATA_DIR / 'photos' / name).unlink(missing_ok=True)


def storage_ready() -> bool:
    if photo_backend() == 's3':
        s3_client().head_bucket(Bucket=os.environ['FORM_S3_BUCKET'])
    else:
        import tempfile
        folder = db.DATA_DIR / 'photos'
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=folder, prefix='.probe-', delete=True) as probe:
            probe.write(b'ok')
            probe.flush()
    return True
