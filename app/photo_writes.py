"""Durable storage-write intents, separate from successful photo registration.

An unacknowledged provider write can appear AFTER a successful delete. Keep an
opaque cleanup watch for those names; repeated deletes are deliberate, not proof
of erasure from versions/backups. Never remove a referenced object. Active writers
hold intent row locks until registration commits, so recovery cannot race them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import secrets
import time

from fastapi import HTTPException

from . import db, photo_cleanup, photo_storage

logger = logging.getLogger('dope_stuff.photo_writes')
GRACE_SECONDS = 900


@dataclass
class Operation:
    id: str
    target: str
    names: tuple[str, ...]
    attempted: set[str] = field(default_factory=set)
    acknowledged: set[str] = field(default_factory=set)
    locked: bool = False


def prepare(names):
    """Commit intent before ANY provider call; fail closed if persistence fails."""
    names = tuple(names)
    if len(names) != len(set(names)):
        raise ValueError('Duplicate generated photo name')
    for name in names:
        photo_storage.validated_name(name)
    op = Operation(secrets.token_hex(16), photo_cleanup.target_key(), names)
    now = int(time.time())
    with db.connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        for name in names:
            connection.execute('''INSERT INTO photo_write_intents
                (target_key,file_path,operation_id,phase,created_at,next_attempt_at)
                VALUES (?,?,?,'staging',?,?)''',
                (op.target, name, op.id, now, now + GRACE_SECONDS))
        connection.execute('COMMIT')
    return op


def lock_operation(connection, op):
    """Caller holds a metadata write transaction throughout storage and finish."""
    suffix = ' FOR UPDATE' if db.postgres_enabled() else ''
    rows = connection.execute('''SELECT file_path,phase FROM photo_write_intents
        WHERE target_key=? AND operation_id=? ORDER BY file_path''' + suffix,
        (op.target, op.id)).fetchall()
    if (op.target != photo_cleanup.target_key()
            or {r['file_path'] for r in rows} != set(op.names)
            or any(r['phase'] != 'staging' for r in rows)):
        raise HTTPException(409, 'Photo operation expired. Check the item before retrying.')
    op.locked = True


def write(op, name, payload):
    if not op.locked or name not in op.names or name in op.attempted:
        raise ValueError('Photo write is not prepared or was already attempted')
    op.attempted.add(name)
    try:
        photo_storage.save_photo(name, payload)
    except Exception:
        # Provider errors can contain private URLs, credentials and object names.
        raise HTTPException(503, 'Photo storage could not confirm the write. '
                            'Cleanup is tracked; check the item before retrying.') from None
    op.acknowledged.add(name)


def finish(connection, op):
    """Remove intents atomically with metadata registration, never separately."""
    if not op.locked or op.acknowledged != set(op.names):
        raise RuntimeError('Cannot register an incomplete photo operation')
    connection.execute('DELETE FROM photo_write_intents WHERE target_key=? AND operation_id=?',
                       (op.target, op.id))
    op.locked = False


def referenced(connection, name):
    return (connection.execute('SELECT 1 FROM item_photos WHERE file_path=? LIMIT 1', (name,)).fetchone()
            or connection.execute('SELECT 1 FROM items WHERE photo_path=? LIMIT 1', (name,)).fetchone())


def abort(op):
    """Best-effort compensation without masking the original request failure.

The transaction may actually have committed before its acknowledgement failed.
Check live references under intent locks before scheduling any deletion.
"""
    op.locked = False
    try:
        if op.target != photo_cleanup.target_key():
            return  # Original-target intents remain available to its worker.
        known, unknown = [], []
        with db.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            suffix = ' FOR UPDATE' if db.postgres_enabled() else ''
            rows = connection.execute('''SELECT file_path,phase FROM photo_write_intents
                WHERE target_key=? AND operation_id=? ORDER BY file_path''' + suffix,
                (op.target, op.id)).fetchall()
            phases = {r['file_path']: r['phase'] for r in rows}
            for name in op.names:
                if referenced(connection, name):
                    connection.execute('DELETE FROM photo_write_intents WHERE target_key=? AND file_path=?',
                                       (op.target, name))
                elif phases.get(name) == 'cleanup':
                    # A worker has already claimed this operation. Never discard
                    # its late-write watch, even if this caller saw no write.
                    unknown.append(name)
                elif name not in op.attempted:
                    connection.execute('DELETE FROM photo_write_intents WHERE target_key=? AND file_path=?',
                                       (op.target, name))
                elif name in op.acknowledged:
                    photo_cleanup.enqueue(connection, [name])
                    connection.execute('DELETE FROM photo_write_intents WHERE target_key=? AND file_path=?',
                                       (op.target, name))
                    known.append(name)
                else:
                    now = int(time.time())
                    connection.execute('''INSERT INTO photo_write_intents
                        (target_key,file_path,operation_id,phase,created_at,next_attempt_at)
                        VALUES (?,?,?,'cleanup',?,0)
                        ON CONFLICT (target_key,file_path) DO UPDATE SET phase='cleanup',next_attempt_at=0''',
                        (op.target, name, op.id, now))
                    unknown.append(name)
            connection.execute('COMMIT')
        if known:
            photo_cleanup.process_pending(names=known)
        if unknown:
            reconcile(names=unknown)
    except Exception:
        logger.warning('Photo write recovery could not finish; durable intent remains for retry')


def reconcile(*, names=None, limit=8, now=None):
    """Retire interrupted writes in a bounded batch; skip active PG row locks.

The SQLite writer transaction likewise excludes active writers. Holding the
lock through provider deletion is essential: a writer may not resume an intent
that recovery has retired. Grace only protects the prepare-to-lock gap.
"""
    now = int(time.time()) if now is None else int(now)
    suffix, args = photo_cleanup._scope(names)
    result = {'checked': 0, 'deleted': 0, 'protected': 0, 'failed': 0}
    with db.connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        lock = ' FOR UPDATE SKIP LOCKED' if db.postgres_enabled() else ''
        rows = connection.execute('''SELECT file_path,attempts FROM photo_write_intents
            WHERE target_key=? AND next_attempt_at<=?''' + suffix
            + ' ORDER BY next_attempt_at,created_at,file_path LIMIT ?' + lock,
            [photo_cleanup.target_key(), now, *args, max(1, min(limit, 100))]).fetchall()
        key = photo_cleanup.target_key()
        for row in rows:
            name = row['file_path']
            result['checked'] += 1
            if referenced(connection, name):
                connection.execute('DELETE FROM photo_write_intents WHERE target_key=? AND file_path=?', (key, name))
                result['protected'] += 1
                continue
            error = ''
            try:
                photo_storage.delete_photo(name)
                result['deleted'] += 1
            except Exception:
                error = 'storage_unavailable'
                result['failed'] += 1
            delay = min(3600, 30 * (2 ** min(row['attempts'], 7)))
            connection.execute('''UPDATE photo_write_intents SET phase='cleanup',
                next_attempt_at=?,attempts=attempts+1,last_error=? WHERE target_key=? AND file_path=?''',
                (now + delay, error, key, name))
            if error:
                logger.warning('Photo write recovery is pending; private storage deletion failed')
                break
        connection.execute('COMMIT')
    return result


def status():
    """A watch count is not an object count or a claim that deletion failed."""
    with db.connect() as connection:
        rows = connection.execute('''SELECT target_key,phase,last_error,COUNT(*) AS count
            FROM photo_write_intents GROUP BY target_key,phase,last_error''').fetchall()
    result = {'write_prepared': 0, 'write_recovery_watch': 0,
              'write_recovery_failed': 0, 'write_other_storage': 0}
    key = photo_cleanup.target_key()
    for row in rows:
        if row['target_key'] != key:
            result['write_other_storage'] += row['count']
        else:
            result['write_prepared' if row['phase'] == 'staging' else 'write_recovery_watch'] += row['count']
            if row['last_error']:
                result['write_recovery_failed'] += row['count']
    return result
