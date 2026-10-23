"""Durable private-photo deletion, committed with the metadata removal.

Workers may repeat deletes after a crash or overlap: names are server-generated,
never reused, and storage deletion is idempotent. Tasks are tied to the original
storage location; switching buckets or local directories cannot redirect them.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time

from . import db, photo_storage

logger = logging.getLogger('dope_stuff.photo_cleanup')


def target_key():
    backend = photo_storage.photo_backend()
    if backend == 'local':
        target = [backend, str((db.DATA_DIR / 'photos').resolve())]
    else:
        target = [backend, os.getenv('FORM_S3_ENDPOINT', '').rstrip('/'),
                  os.getenv('FORM_S3_BUCKET', ''), photo_storage.object_key('probe.webp')]
    return hashlib.sha256(json.dumps(target).encode()).hexdigest()


def enqueue(connection, names):
    """Caller owns the transaction that removes the corresponding metadata."""
    key = target_key()
    for name in sorted(set(names)):
        photo_storage.validated_name(name)
        connection.execute('''INSERT INTO photo_deletions(target_key,file_path,created_at)
            VALUES (?,?,?) ON CONFLICT (target_key,file_path) DO NOTHING''',
                           (key, name, int(time.time())))


def _scope(names):
    if names is None:
        return '', []
    names = sorted(set(names))
    if not names:
        return ' AND 1=0', []
    return ' AND file_path IN (' + ','.join('?' for _ in names) + ')', names


def pending(names=None):
    suffix, args = _scope(names)
    with db.connect() as connection:
        return connection.execute('SELECT COUNT(*) FROM photo_deletions WHERE target_key=?' + suffix,
                                  [target_key(), *args]).fetchone()[0]


def status():
    """Operator counts only: no filenames, identities, credentials or raw errors."""
    with db.connect() as connection:
        total = connection.execute('SELECT COUNT(*) FROM photo_deletions').fetchone()[0]
        current = pending()
        failed = connection.execute('''SELECT COUNT(*) FROM photo_deletions
            WHERE target_key=? AND attempts>0''', (target_key(),)).fetchone()[0]
    return {'pending': total, 'current_storage_pending': current,
            'other_storage_pending': total - current, 'current_storage_failed': failed}


def process_pending(*, names=None, limit=8):
    """Bounded batch; stop on storage errors to avoid amplifying an outage.

    Oldest-attempted work is retried first, so one failing object cannot hold
    every other task at the front of the queue forever.
    """
    key = target_key()
    suffix, args = _scope(names)
    with db.connect() as connection:
        rows = connection.execute('''SELECT file_path FROM photo_deletions WHERE target_key=?'''
            + suffix + ' ORDER BY last_attempt_at,created_at,file_path LIMIT ?',
            [key, *args, max(1, min(limit, 100))]).fetchall()
    completed = 0
    for row in rows:
        name = row['file_path']
        try:
            photo_storage.delete_photo(name)
        except Exception:
            # Do not persist/log exception strings: SDK errors can include URLs
            # or private object names. Keep the task for the next retry.
            with db.connect() as connection:
                connection.execute('''UPDATE photo_deletions SET attempts=attempts+1,
                    last_attempt_at=?,last_error='storage_unavailable'
                    WHERE target_key=? AND file_path=?''', (time.time_ns(), key, name))
            logger.warning('Photo cleanup is pending; private storage deletion failed')
            break
        else:
            with db.connect() as connection:
                connection.execute('DELETE FROM photo_deletions WHERE target_key=? AND file_path=?',
                                   (key, name))
            completed += 1
    return {'completed': completed, 'pending': pending(names)}


async def retry_loop():
    while True:
        await asyncio.sleep(30)
        try:
            await asyncio.to_thread(process_pending)
            from . import photo_writes
            await asyncio.to_thread(photo_writes.reconcile)
        except Exception:
            logger.warning('Photo cleanup worker could not finish a batch; work remains queued')
