"""Opt-in, bounded R2 write/read/delete check for a private staging deployment.

This is NOT an HTTP readiness check or a general-purpose object-store cleaner.
It writes only one random synthetic WebP via the app's existing photo backend,
tries to delete that exact object even after a failed upload/read, and confirms
that the object is no longer readable. It never touches the application DB.
"""
from __future__ import annotations

import argparse
import io
import os
import re
import secrets
from urllib.parse import urlsplit

from PIL import Image

from app import photo_storage


class ProbeRefused(RuntimeError):
    """Unsafe target or missing explicit operator approval."""


def validate_target() -> None:
    expected = {
        "FORM_ENV": "staging",
        "FORM_CLOUD_MODE": "true",
        "FORM_PHOTO_STORAGE": "s3",
        "FORM_S3_PREFIX": "staging",
        "FORM_STORAGE_PROBE_CONFIRM": "YES_PRIVATE_STAGING_R2_ONLY",
    }
    if any(os.getenv(key) != value for key, value in expected.items()):
        raise ProbeRefused("Requires explicit isolated staging R2 configuration and confirmation")
    # This particular operator check is R2-specific; never send credentials to
    # an arbitrary endpoint, localhost, plaintext HTTP, or a URL with userinfo.
    endpoint = urlsplit(os.getenv("FORM_S3_ENDPOINT", ""))
    host = (endpoint.hostname or "").lower()
    if (endpoint.scheme != "https"
            or not re.fullmatch(r"[a-f0-9]{32}\.r2\.cloudflarestorage\.com", host)
            or endpoint.netloc.lower() != host
            or endpoint.path not in ("", "/")
            or endpoint.query or endpoint.fragment):
        raise ProbeRefused("Requires the standard private HTTPS Cloudflare R2 account endpoint")
    if any(not os.getenv(k) for k in (
        "FORM_S3_BUCKET", "FORM_S3_ACCESS_KEY_ID", "FORM_S3_SECRET_ACCESS_KEY"
    )):
        raise ProbeRefused("Private staging bucket credentials are missing")


def run_probe() -> bool:
    validate_target()  # Absolutely no remote calls before all guards pass.
    name = "ops-probe-" + secrets.token_hex(16) + ".webp"
    image = io.BytesIO()
    Image.new("RGB", (2, 2), (64, 90, 64)).save(image, format="WEBP")
    payload = image.getvalue()
    # Attempt cleanup even if the upload reached R2 but the client timed out.
    # Only our unique synthetic key is ever targeted for deletion.
    try:
        photo_storage.save_photo(name, payload)
        if photo_storage.read_photo(name) != payload:
            raise RuntimeError("Staging photo round-trip did not match")
    finally:
        photo_storage.delete_photo(name)
    try:
        photo_storage.read_photo(name)
    except FileNotFoundError:
        return True
    raise RuntimeError("Staging photo remained readable after deletion")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Opt-in isolated staging R2 photo operations check")
    parser.add_argument("--run", action="store_true", help="Perform one synthetic write/read/delete probe")
    args = parser.parse_args(argv)
    if not args.run:
        print("Refused: supply --run and the explicit staging confirmation environment variable.")
        return 2
    try:
        run_probe()
    except Exception:
        # Never print SDK exception strings: they may contain credentials,
        # bucket/object identifiers, account endpoints, or signed request data.
        print("STAGING R2 PROBE FAILED: investigate storage access and possible probe cleanup; do not onboard sellers.")
        return 1
    print("STAGING R2 PROBE PASSED: synthetic write/read/delete verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
