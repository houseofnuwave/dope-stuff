"""Portable archive inspection. Parse untrusted ZIPs without trusting paths or DB identifiers.

Validation is intentionally independent from DB writes: a restore is either valid
before staging any photos or rejected without changing the seller's account.
"""
from __future__ import annotations

import io
import json
import re
import tempfile
import zipfile
from dataclasses import dataclass
from typing import BinaryIO, Callable
from fastapi import HTTPException

MAX_ZIP_BYTES = 128 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_JSON_BYTES = 10 * 1024 * 1024
MAX_ARCHIVE_FILES = 4100
MAX_RESTORE_ITEMS = 10_000
MAX_RESTORE_PHOTOS = 4000
MAX_RESTORE_FEEDBACK = 2000
MAX_PHOTO_FILE_BYTES = 6 * 1024 * 1024


def limits():
    """The same budgets are advertised, exported and enforced on restore."""
    return {'zip_bytes': MAX_ZIP_BYTES, 'expanded_bytes': MAX_UNCOMPRESSED_BYTES,
            'metadata_bytes': MAX_JSON_BYTES, 'items': MAX_RESTORE_ITEMS,
            'photos': MAX_RESTORE_PHOTOS, 'photo_bytes': MAX_PHOTO_FILE_BYTES,
            'feedback': MAX_RESTORE_FEEDBACK}


def check_export_counts(counts):
    maxima = {'items': MAX_RESTORE_ITEMS, 'item_channels': MAX_RESTORE_ITEMS * 8,
              'item_photos': MAX_RESTORE_PHOTOS, 'sales': MAX_RESTORE_ITEMS,
              'feedback': MAX_RESTORE_FEEDBACK}
    if any(counts[key] > maximum for key, maximum in maxima.items()):
        raise HTTPException(413, 'Account exceeds portable backup record limits. No backup was produced; use operator recovery procedures.')
    if counts['item_photos'] + 1 > MAX_ARCHIVE_FILES:
        raise HTTPException(413, 'Account exceeds portable backup file limits. No backup was produced.')


def build_archive(data, *, read_photo: Callable, **validators):
    """Return a fully validated seekable ZIP, or an error before any response.

    Large output spills to a private temporary file rather than retaining a
    second full ZIP in memory. The caller must close the returned file.
    """
    check_export_counts({key: len(data[key]) for key in ('items', 'item_channels', 'item_photos', 'sales', 'feedback')})
    try:
        metadata = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
    except (TypeError, ValueError):
        raise HTTPException(409, 'Stored account data failed backup validation. No backup was produced.') from None
    if len(metadata) > MAX_JSON_BYTES:
        raise HTTPException(413, 'Account exceeds the portable backup metadata limit. No backup was produced.')
    if len(metadata) > MAX_UNCOMPRESSED_BYTES:
        raise HTTPException(413, 'Account exceeds the portable backup expanded-size limit. No backup was produced.')
    output = None
    try:
        output = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode='w+b')
        expanded = len(metadata)
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('form_backup.json', metadata)
            for photo in data['item_photos']:
                try:
                    encoded = read_photo(photo['file_path'])
                except HTTPException:
                    raise
                except FileNotFoundError:
                    raise HTTPException(409, 'Backup incomplete: a referenced photo is missing. No backup was produced.') from None
                except Exception:
                    raise HTTPException(503, 'Private photo storage is temporarily unavailable. No backup was produced.') from None
                if len(encoded) > MAX_PHOTO_FILE_BYTES:
                    raise HTTPException(413, 'A stored photo exceeds the portable backup photo-size limit. No backup was produced.')
                expanded += len(encoded)
                if expanded > MAX_UNCOMPRESSED_BYTES:
                    raise HTTPException(413, 'Account exceeds the portable backup expanded-size limit. No backup was produced.')
                archive.writestr(f"photos/item-{photo['item_id']}/photo-{photo['id']}.webp", encoded)
                if output.tell() > MAX_ZIP_BYTES:
                    raise HTTPException(413, 'Account exceeds the portable backup ZIP-size limit. No backup was produced.')
        if output.tell() > MAX_ZIP_BYTES:
            raise HTTPException(413, 'Account exceeds the portable backup ZIP-size limit. No backup was produced.')
        output.seek(0)
        try:
            inspect_archive(output, data['account']['email'], retain_images=False, **validators)
        except HTTPException:
            raise HTTPException(409, 'Stored account data or photos failed backup validation. No backup was produced.') from None
        output.seek(0)
        return output
    except OSError:
        if output is not None:
            output.close()
        raise HTTPException(503, 'Temporary backup storage is unavailable. No backup was produced.') from None
    except Exception:
        if output is not None:
            output.close()
        raise


@dataclass
class InspectedArchive:
    metadata: dict
    items: list[dict]
    channels: list[dict]
    photos: list[dict]
    sales: list[dict]
    feedback: list[dict]
    images: dict[int, bytes]


def fail(message: str):
    raise HTTPException(422, message)


def list_section(data: dict, key: str, maximum: int) -> list[dict]:
    entries = data.get(key)
    if not isinstance(entries, list) or len(entries) > maximum:
        fail(f'Backup has an invalid or oversized {key} section')
    if any(not isinstance(row, dict) for row in entries):
        fail(f'Backup {key} records must be objects')
    return entries


def safe_timestamp(value) -> str | None:
    """Preserve SQLite's original timeline without trusting arbitrary metadata."""
    if value is None:
        return None
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}',value):
        fail('Backup contains an invalid record timestamp')
    return value


def record_id(value, label: str) -> int:
    if type(value) is not int or value < 1:
        fail(f'Invalid {label} identifier')
    return value


def inspect_archive(raw: bytes | BinaryIO, email: str, *, validate_item: Callable,
                    validate_channel_url: Callable, validate_sale_channel: Callable,
                    validate_image: Callable, retain_images: bool = True) -> InspectedArchive:
    if isinstance(raw, bytes):
        size, source = len(raw), io.BytesIO(raw)
    else:
        raw.seek(0, 2)
        size = raw.tell()
        raw.seek(0)
        source = raw
    if not size or size > MAX_ZIP_BYTES:
        fail('Backup ZIP is empty or exceeds the 128 MB pilot limit')
    try:
        archive = zipfile.ZipFile(source, 'r')
    except (zipfile.BadZipFile, OSError):
        fail('Choose an intact FORM backup ZIP')
    with archive:
        infos = archive.infolist()
        names = [f.filename for f in infos]
        if len(infos) > MAX_ARCHIVE_FILES or len(set(names)) != len(names):
            fail('Backup contains too many entries or duplicate filenames')
        if 'form_backup.json' not in names:
            fail('Not a FORM backup: form_backup.json is missing')
        if any(f.flag_bits & 1 for f in infos):
            fail('Encrypted ZIP archives are not supported')
        if any(f.is_dir() for f in infos):
            fail('Backup may only contain expected data and photo files')
        if sum(f.file_size for f in infos) > MAX_UNCOMPRESSED_BYTES:
            fail('Backup expands beyond the 256 MB pilot limit')
        root = archive.getinfo('form_backup.json')
        if root.file_size > MAX_JSON_BYTES:
            fail('Backup metadata is too large')
        try:
            data = json.loads(archive.read(root))
        except (ValueError, UnicodeDecodeError, RuntimeError, zipfile.BadZipFile):
            fail('Backup metadata could not be read')
        if not isinstance(data, dict) or data.get('format') != 'FORM Seller OS portable backup' or type(data.get('version')) is not int or data['version'] != 1:
            fail('Unsupported backup format or version')
        account = data.get('account')
        if not isinstance(account, dict) or not isinstance(account.get('email'), str) or account['email'].strip().lower() != email:
            fail('This backup belongs to a different email account')

        items = list_section(data, 'items', MAX_RESTORE_ITEMS)
        channels = list_section(data, 'item_channels', MAX_RESTORE_ITEMS * 8)
        photos = list_section(data, 'item_photos', MAX_RESTORE_PHOTOS)
        sales = list_section(data, 'sales', MAX_RESTORE_ITEMS)
        feedback = list_section(data, 'feedback', MAX_RESTORE_FEEDBACK)

        item_ids, sku_set = set(), set()
        validated_items = []
        for entry in items:
            old_id = record_id(entry.get('id'), 'item')
            if old_id in item_ids: fail('Duplicate item identifier')
            item_ids.add(old_id)
            try:
                model = validate_item(entry)
            except Exception:
                fail('Backup contains an invalid inventory item')
            if not model.sku or model.sku in sku_set:
                fail('Backup has an empty or duplicate SKU')
            sku_set.add(model.sku)
            state = entry.get('status')
            if state not in ('draft', 'active', 'sold', 'archived'):
                fail('Backup contains an invalid item status')
            if state == 'sold' and model.quantity != 0:
                fail('Sold inventory must have zero remaining quantity')
            validated_items.append({'old_id': old_id, 'model': model, 'status': state,
                'created_at':safe_timestamp(entry.get('created_at')), 'updated_at':safe_timestamp(entry.get('updated_at'))})

        validated_channels, ch_set = [], set()
        for entry in channels:
            old_id = record_id(entry.get('item_id'), 'channel item')
            channel = entry.get('channel')
            status = entry.get('status')
            url = entry.get('listing_url', '')
            if old_id not in item_ids or not isinstance(channel, str) or not isinstance(url, str):
                fail('Backup has a channel that does not belong to an item')
            key = (old_id, channel)
            if key in ch_set: fail('Duplicate marketplace channel for an item')
            ch_set.add(key)
            try:
                validate_channel_url(channel, status, url)
            except Exception:
                fail('Backup contains an invalid marketplace listing or URL')
            validated_channels.append({'old_id':old_id, 'channel':channel,'status':status,'url':url,
                'updated_at':safe_timestamp(entry.get('updated_at'))})

        validated_photos, image_bytes, expected_paths, pic_ids, positions = [], {}, set(), set(), set()
        for entry in photos:
            old_id = record_id(entry.get('id'), 'photo')
            item_id = record_id(entry.get('item_id'), 'photo item')
            if item_id not in item_ids or old_id in pic_ids:
                fail('Invalid or duplicate photo reference')
            pic_ids.add(old_id)
            position = entry.get('position')
            if type(position) is not int or not 0 <= position < 8 or (item_id,position) in positions:
                fail('Invalid or duplicate photo position')
            positions.add((item_id,position))
            path = f'photos/item-{item_id}/photo-{old_id}.webp'
            expected_paths.add(path)
            if path not in names:
                fail('A photo referenced by the backup is missing')
            info = archive.getinfo(path)
            if info.file_size > MAX_PHOTO_FILE_BYTES:
                fail('A photo exceeds the restore size limit')
            try:
                raw_photo = archive.read(info)
                # Re-encode to remove any metadata and reject malformed payloads.
                validated_image = validate_image(raw_photo)
                if retain_images:
                    image_bytes[old_id] = validated_image
            except Exception:
                fail('Backup contains a damaged or unsupported photograph')
            validated_photos.append({'old_id':old_id,'item_id':item_id,'position':position,
                'created_at':safe_timestamp(entry.get('created_at'))})
        if set(names) != expected_paths | {'form_backup.json'}:
            fail('Backup contains unexpected files')
        picture_count = {}
        for p in validated_photos:
            picture_count[p['item_id']] = picture_count.get(p['item_id'], 0) + 1
        if any(n > 8 for n in picture_count.values()):
            fail('An item has more than eight photographs')

        validated_sales, sale_items = [], set()
        for entry in sales:
            old_id = record_id(entry.get('item_id'), 'sale item')
            if old_id not in item_ids or old_id in sale_items:
                fail('Invalid or duplicate sale reference')
            sale_items.add(old_id)
            channel = entry.get('channel')
            if not isinstance(channel, str) or not validate_sale_channel(channel):
                fail('Invalid sale marketplace')
            for field in ('sold_cents','fee_cents','ship_cents','cost_cents'):
                value = entry.get(field)
                if type(value) is not int or not 0 <= value <= 100_000_000:
                    fail('Invalid sale amount')
            validated_sales.append({'old_id':old_id,'channel':channel,
                **{f:entry[f] for f in ('sold_cents','fee_cents','ship_cents','cost_cents')},
                'created_at':safe_timestamp(entry.get('created_at'))})
        sold_item_ids = {it['old_id'] for it in validated_items if it['status'] == 'sold'}
        if sale_items != sold_item_ids:
            fail('Sold inventory and recorded sales do not match')
        validated_feedback = []
        for entry in feedback:
            rating = entry.get('rating')
            message = entry.get('message')
            if type(rating) is not int or not 1 <= rating <= 5 or not isinstance(message, str) or not 5 <= len(message) <= 2000:
                fail('Invalid feedback record')
            validated_feedback.append({'rating':rating,'message':message,
                'created_at':safe_timestamp(entry.get('created_at'))})

        return InspectedArchive(
            metadata={'items':len(items),'photos':len(photos),'sales':len(sales),
                      'published':sum(c['status']=='manually_published' for c in validated_channels),
                      'manual_delists':sum(c['status']=='delist_required' for c in validated_channels),
                      'feedback':len(feedback), 'email':email},
            items=validated_items, channels=validated_channels, photos=validated_photos,
            sales=validated_sales, feedback=validated_feedback, images=image_bytes)
