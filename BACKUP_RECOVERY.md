# Portable backup and recovery contract

An account export is delivered only after the finished ZIP passes the same
metadata, relationship and photo validator used by restore. Export uses one
database read snapshot, includes all records in that snapshot, reads every
referenced photo and validates it before sending download headers. Missing
files are never silently skipped.

The existing `FORM Seller OS portable backup` version-1 format and internal
`form_backup.json` name remain compatible. A restore requires a blank account
with the same email and its current password. It preserves inventory, recorded
sales, channel states, photo associations/order, feedback and timestamps; it
keeps the current account's chosen display name and credentials.

## Shared portable budgets

| Budget | Ceiling |
|---|---:|
| ZIP download/upload | 128 MiB |
| Expanded archive | 256 MiB |
| Metadata | 10 MiB |
| Lifetime inventory, including sold/archived items | 10,000 |
| Photo objects | 4,000 |
| Each archived photo | 6 MiB |
| Feedback records | 2,000 |

All budgets apply together; the first exceeded budget blocks the operation.
The item ceiling is not a promise that every 10,000-item account fits the byte
budgets. Sold and archived history no longer hits the former 500-item ceiling.
The authenticated session advertises the backend limits to the account UI.
Creation/import does not silently discard data when a portable budget is hit.

Large ZIP output spills to private temporary storage after 8 MiB. It is
validated from that seekable stream without keeping a second whole ZIP or all
re-encoded photos in memory, streamed in bounded chunks, then closed. Local and
S3 photo reads are also bounded. Restore still retains its validated photo set
within the existing expanded-size budget; this work does not establish a
production memory/concurrency SLA.

## Failure behavior

- **409:** a referenced photo is missing/corrupt or stored records are internally
  inconsistent. No backup file is produced. Investigate/recover the missing data
  before retrying; do not delete live records to make an export pass.
- **413:** a shared record, byte or file budget is exceeded. No truncated backup
  is produced. Preserve the live account and use a verified operator recovery
  procedure; multipart portable backups are not implemented.
- **503:** private photo storage or temporary backup storage is unavailable.
  No backup file is produced. Restore service availability, then retry.

The account download button shows failures inside the workspace. JSON errors
and HTML gateway responses are not downloaded as misleading `.zip` files. A
successful download is private and unencrypted; store it securely.

If a record or photo is changed/deleted during export, the database snapshot
remains coherent. If a photo from that snapshot can no longer be read, export
fails rather than representing a partial backup as complete. Live exports do
not replace versioned database/object-store disaster recovery or retention
policy, which remain v1.0 operational gates.

## Verification

Tests reproduce and fix the old 501-item restore failure and missing-photo
export failure. They exercise complete record comparison after large recovery,
all shared export ceilings, corrupt photos, sanitized provider outages, bounded
local photo reads, temporary-file closure and a sale committed during export.
Desktop/mobile Chromium tests download the real ZIP from a catalog beyond 500
items and verify its contents, plus missing-photo/HTML failures without a false
download. The cloud job repeats large recovery using real disposable PostgreSQL
and private S3-compatible storage. Consult its actual candidate commit result.
