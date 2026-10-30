"""FORM single-instance pilot disaster-recovery snapshot CLI.

Creates authenticated AES-256-GCM encrypted application archives. Requires
FORM_BACKUP_KEY, a base64-encoded 32-byte key managed OUTSIDE the backup path.
This is operator-level disaster recovery, not the existing user ZIP export.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import sys
import tempfile
import zipfile

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import db as form_db

MAGIC = b'FORMOPS1\x00'
NONCE_BYTES = 12
TAG_BYTES = 16
CHUNK = 1024 * 1024
MAX_FILES = 100_000
MAX_EXPANDED = 20 * 1024**3


class BackupError(Exception):
    pass


def key_from_environment():
    raw = os.environ.get('FORM_BACKUP_KEY', '')
    try:
        key = base64.b64decode(raw, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise BackupError('FORM_BACKUP_KEY must be a base64-encoded 32-byte secret') from exc
    if len(key) != 32:
        raise BackupError('FORM_BACKUP_KEY must decode to exactly 32 bytes')
    return key


def valid_photo_filename(name: str) -> bool:
    # Include legacy formats; still reject paths, symlinks and special entries.
    from re import fullmatch
    return bool(fullmatch(r'[a-zA-Z0-9._-]{1,128}\.(webp|png|jpe?g)', name, flags=2)) and '..' not in name


def hash_file(path: Path):
    digest = hashlib.sha256()
    total = 0
    with path.open('rb') as source:
        while chunk := source.read(CHUNK):
            digest.update(chunk)
            total += len(chunk)
    return {'sha256': digest.hexdigest(), 'size': total}


def gather_snapshot(temp_root: Path):
    if form_db.postgres_enabled() or os.getenv('FORM_PHOTO_STORAGE','local') == 's3':
        raise BackupError('Legacy operations backups support local SQLite/photos only; use managed PostgreSQL backup and private bucket recovery for cloud staging')
    """SQLite's online backup API captures committed rows and ignores WAL races."""
    destination = temp_root / 'database' / 'form.db'
    destination.parent.mkdir(parents=True)
    with form_db.connect() as source:
        with sqlite3.connect(destination) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise BackupError('Database integrity check failed')
            names = {r[0] for r in target.execute('SELECT file_path FROM item_photos')}
            names |= {r[0] for r in target.execute('SELECT photo_path FROM items WHERE photo_path IS NOT NULL')}
    for name in sorted(names):
        if not valid_photo_filename(name):
            raise BackupError('Database references an invalid photo filename')
        source = form_db.DATA_DIR / 'photos' / name
        if not source.is_file() or source.is_symlink():
            raise BackupError(f'Missing or non-regular photo file: {name}. Retry during maintenance.')
        photo_dest = temp_root / 'photos' / name
        photo_dest.parent.mkdir(exist_ok=True)
        shutil.copyfile(source, photo_dest)
        # Detect an image modified during copying, rather than silently shipping
        # an inconsistent archive.
        if hash_file(source) != hash_file(photo_dest):
            raise BackupError(f'Photo changed during backup: {name}. Retry while writes are paused.')
    return destination, len(names)


def create_backup(output: Path):
    key = key_from_environment()
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise BackupError('Refusing to overwrite an existing backup')
    fd, pending_name = tempfile.mkstemp(prefix='.form-backup-', dir=output.parent)
    os.close(fd)
    pending = Path(pending_name)
    try:
        with tempfile.TemporaryDirectory(prefix='form-snapshot-') as temp:
            temp_root = Path(temp)
            destination, photo_count = gather_snapshot(temp_root)
            payload = temp_root / 'payload.zip'
            paths = [destination, *sorted((temp_root / 'photos').glob('*'))] if (temp_root / 'photos').exists() else [destination]
            manifest = {
                'format':'FORM Seller OS operations backup', 'version':1,
                'created_at':datetime.now(timezone.utc).isoformat(),
                'files':{str(path.relative_to(temp_root)): hash_file(path) for path in paths}
            }
            with zipfile.ZipFile(payload, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for path in paths:
                    archive.write(path, arcname=str(path.relative_to(temp_root)))
                archive.writestr('manifest.json', json.dumps(manifest, indent=2))
            nonce = secrets.token_bytes(NONCE_BYTES)
            encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
            encryptor.authenticate_additional_data(MAGIC)
            with payload.open('rb') as src, pending.open('wb') as dest:
                dest.write(MAGIC + nonce)
                while block := src.read(CHUNK):
                    dest.write(encryptor.update(block))
                dest.write(encryptor.finalize())
                dest.write(encryptor.tag)
            os.chmod(pending, 0o600)
        # Do not publish until encryption completed and the archive is verifiable.
        verify_backup(pending)
        os.replace(pending, output)
        return {'path':str(output),'photo_count':photo_count,'encrypted':True}
    finally:
        pending.unlink(missing_ok=True)


def decrypt_to_zip(encrypted: Path, plaintext: Path):
    key = key_from_environment()
    with encrypted.open('rb') as src:
        header = src.read(len(MAGIC) + NONCE_BYTES)
        if len(header) != len(MAGIC) + NONCE_BYTES or not header.startswith(MAGIC):
            raise BackupError('Invalid FORM operations archive header')
        nonce = header[len(MAGIC):]
        size = encrypted.stat().st_size
        body_size = size - len(MAGIC) - NONCE_BYTES - TAG_BYTES
        if body_size <= 0:
            raise BackupError('Truncated encrypted archive')
        src.seek(size-TAG_BYTES)
        tag = src.read(TAG_BYTES)
        src.seek(len(MAGIC) + NONCE_BYTES)
        decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
        decryptor.authenticate_additional_data(MAGIC)
        try:
            with plaintext.open('wb') as dest:
                remaining = body_size
                while remaining:
                    block = src.read(min(CHUNK, remaining))
                    if not block:
                        raise BackupError('Truncated encrypted payload')
                    dest.write(decryptor.update(block))
                    remaining -= len(block)
                dest.write(decryptor.finalize())
        except InvalidTag as exc:
            plaintext.unlink(missing_ok=True)
            raise BackupError('Archive authentication failed: wrong key or modified backup') from exc


def validate_zip(path: Path):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_FILES or sum(entry.file_size for entry in entries) > MAX_EXPANDED:
            raise BackupError('Backup exceeds supported safety limits')
        if len(set(entry.filename for entry in entries)) != len(entries):
            raise BackupError('Duplicate archive entries are forbidden')
        if 'manifest.json' not in archive.namelist():
            raise BackupError('Manifest not found')
        if archive.getinfo('manifest.json').file_size > 2_000_000:
            raise BackupError('Manifest is too large')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('format') != 'FORM Seller OS operations backup' or manifest.get('version') != 1:
            raise BackupError('Unsupported backup format')
        expected = manifest.get('files', {})
        if 'database/form.db' not in expected or set(archive.namelist()) != set(expected) | {'manifest.json'}:
            raise BackupError('Backup entries do not match the manifest')
        for info in entries:
            name = info.filename
            if name != 'manifest.json' and name != 'database/form.db' and not (name.startswith('photos/') and valid_photo_filename(name[7:])):
                raise BackupError('Unexpected archive entry')
            if info.is_dir() or (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise BackupError('Links and directories are not supported in operations archives')
            if name == 'manifest.json':
                continue
            file_entry = expected[name]
            if not isinstance(file_entry.get('size'), int) or not isinstance(file_entry.get('sha256'), str) or info.file_size != file_entry['size']:
                raise BackupError(f'Invalid size/hash metadata: {name}')
            digest = hashlib.sha256()
            with archive.open(info, 'r') as src:
                while block := src.read(CHUNK):
                    digest.update(block)
            if digest.hexdigest() != file_entry['sha256']:
                raise BackupError(f'Checksum mismatch: {name}')
        with tempfile.TemporaryDirectory(prefix='form-verify-sqlite-') as tmp:
            db_copy = Path(tmp) / 'form.db'
            with archive.open('database/form.db') as src, db_copy.open('wb') as dest:
                shutil.copyfileobj(src,dest)
            with sqlite3.connect(f'file:{db_copy}?mode=ro', uri=True) as db:
                if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise BackupError('SQLite integrity check failed')
                for table in ('users','items','item_photos','sales'):
                    row = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()
                    if not row:
                        raise BackupError('Required database table missing')
                # A valid ZIP checksum alone cannot prove that every image
                # referenced by the restored inventory is actually present.
                referenced = {row[0] for row in db.execute('SELECT file_path FROM item_photos')}
                referenced.update(row[0] for row in db.execute(
                    'SELECT photo_path FROM items WHERE photo_path IS NOT NULL'))
                archived = {name[7:] for name in expected if name.startswith('photos/')}
                if (any(not isinstance(name, str) or not valid_photo_filename(name)
                        for name in referenced) or referenced != archived):
                    raise BackupError('Backup photo files do not match database references')
        return {'files':len(expected),'photos':sum(name.startswith('photos/') for name in expected),
                'created_at':manifest['created_at']}


def verify_backup(input_path: Path):
    with tempfile.TemporaryDirectory(prefix='form-verify-') as tmp:
        decrypted = Path(tmp) / 'payload.zip'
        decrypt_to_zip(input_path, decrypted)
        return validate_zip(decrypted)


def extract_rehearsal(input_path: Path, destination: Path):
    # Operator must choose a new directory. Never overwrite a running instance.
    destination = destination.expanduser().resolve()
    if destination.exists():
        raise BackupError('Recovery destination already exists; choose a new empty path')
    with tempfile.TemporaryDirectory(prefix='form-rehearsal-') as tmp:
        decoded = Path(tmp) / 'payload.zip'
        decrypt_to_zip(input_path, decoded)
        metadata = validate_zip(decoded)
        destination.mkdir(parents=True, mode=0o700)
        try:
            with zipfile.ZipFile(decoded) as archive:
                for name in sorted(archive.namelist()):
                    if name == 'manifest.json':
                        continue
                    target = destination / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(name) as src, target.open('wb') as output:
                        shutil.copyfileobj(src, output)
                    os.chmod(target, 0o600)
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise
    return {'destination':str(destination),**metadata}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('keygen', help='Generate a secret and store it in a secret manager')
    for name in ('create','verify','rehearse'):
        p = sub.add_parser(name)
        if name != 'create':
            p.add_argument('--input', type=Path, required=True)
        else:
            p.add_argument('--output', type=Path, required=True)
        if name == 'rehearse':
            p.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.cmd == 'keygen':
            print(base64.b64encode(secrets.token_bytes(32)).decode())
            return
        if args.cmd == 'create':
            result = create_backup(args.output)
        elif args.cmd == 'verify':
            if args.input is None: parser.error('--input is required')
            result = verify_backup(args.input)
        else:
            if args.input is None: parser.error('--input is required')
            result = extract_rehearsal(args.input,args.destination)
        print(json.dumps(result, indent=2))
    except (BackupError, ValueError, OSError, sqlite3.DatabaseError, zipfile.BadZipFile, KeyError, TypeError) as exc:
        parser.exit(1, f'FORM backup failed: {exc}\n')

if __name__ == '__main__':
    main()
