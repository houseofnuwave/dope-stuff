# Staging R2 write/read/delete verification (operator-only)

**Purpose:** A healthy `/readyz` currently confirms that PostgreSQL is queryable
and the photo bucket responds to `HeadBucket`. That does **not** establish
whether the staging R2 token can upload, retrieve, and delete photos.

This opt-in check exercises the actual `photo_storage.save_photo`,
`read_photo`, and `delete_photo` paths with **one synthetic 2×2 WebP** and
a cryptographically random `ops-probe-*.webp` name. It never reads or changes
seller metadata, customer objects, production buckets, or the database.

## Prerequisites

- A dedicated **private** staging R2 bucket, never a production or shared bucket.
- An operator-approved maintenance/test window with the staging deployment's
  environment variables supplied through the host's secret manager (not Git).
- `FORM_ENV=staging`, `FORM_CLOUD_MODE=true`, `FORM_PHOTO_STORAGE=s3`,
  `FORM_S3_PREFIX=staging`, and the standard Cloudflare account HTTPS R2 endpoint.
- The staging R2 token must be scoped to the staging bucket with object read,
  write, and delete permissions. This command **cannot** establish that the
  bucket has no public access or that token permissions are correctly restricted
  to this bucket; inspect those controls separately.

Run from the intended release image/environment:

```sh
FORM_STORAGE_PROBE_CONFIRM=YES_PRIVATE_STAGING_R2_ONLY \
  python -m tools.staging_storage_probe --run
```

Do **not** paste credentials or full environment dumps into a terminal transcript,
issue, screenshot, or chat. The command prints only generic success/failure.

**Pass:** synthetic upload, exact-byte readback, deletion, and a subsequent
read returning not found. **Fail:** any guard, storage operation, mismatched
bytes, cleanup failure, or object remaining readable. Failed uploads still
trigger best-effort deletion of the exact random probe key. If cleanup fails,
the operator must inspect and remove only that probe object using authorized
private provider tooling; the command intentionally does not log its key.

This is an **explicit one-time staging check**, not a readiness endpoint or
automated deployment action. No staging deployment or real R2 verification has
been performed by adding this tool. A successful probe does not replace backup
restore drills, bucket privacy inspection, access-control tests, or deployment
rollback procedures. Do not onboard sellers based on this result alone.
