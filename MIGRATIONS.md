# Database upgrades and recovery

The database now records ordered, checksummed revisions in `schema_migrations`:
1. Original v0.7 core schema, older missing session-version adoption and legacy cover compatibility.
2. Durable private-photo deletion work.
3. Durable photo-write intents and their lookup indexes.

SQL lives in `app/migration_sql/`. Applied revisions, names, SQL and the first
revision's compatibility callbacks are immutable. Append a new revision for a
change; never edit an applied revision, delete ledger rows or manually stamp a
version to bypass an error. Checksums are backend-specific; copying a SQLite
ledger into PostgreSQL is not a supported conversion.

## Transaction and startup contract

All pending revisions, structural validation, compatibility backfill and ledger
entries share **one transaction**. SQLite uses `BEGIN IMMEDIATE`; PostgreSQL uses
a transaction-scoped advisory lock, a 15-second lock timeout and a 120-second
statement timeout. Concurrent upgraders serialize. Failed SQL/validation or an
interrupted connection leaves no newly committed revision or partial DDL batch.
The runner rejects transaction-escape statements such as embedded `COMMIT`.
Revision files use simple semicolon-terminated SQL, not procedural functions.

Development/test startup applies pending revisions automatically, preserving the
local quick start. **Staging/production startup only checks** and fails if an
explicit upgrade is required. Readiness also rejects missing, changed, gapped or
newer history and unsupported core structure; liveness is independent.

The non-destructive legacy cover-to-gallery backfill remains a compatibility
repair when `--apply` or local/test initialization runs, even after all revisions
are present. Hosted check-only startup and inspection do not perform this repair.
No photos are read, written or deleted by schema migration.

Structural adoption checks columns, integer/text type families, nullability,
unique keys and ownership foreign keys. Applying migrations also rejects SQLite
foreign-key violations or unvalidated PostgreSQL constraints. Existing bad data
is not silently deleted or “fixed.” This is **not** an exhaustive audit of CHECK
expressions, default/identity expressions, triggers or performance indexes.

## Operator sequence

Use the same release image, database configuration and secret-manager environment
as the intended app. Do not paste credentials into commands or commit them.

1. Stop/drain **all** application writes and old worker processes. This is a
   maintenance-window protocol, not a proven zero-downtime rolling migration.
2. Create and verify a pre-upgrade database **and photo** recovery point. Preserve
   the exact app release and dependencies. A seller portable ZIP is not a full
   operational recovery point. For local SQLite/photos, the existing encrypted
   backup commands can be used with an independently secured `FORM_BACKUP_KEY`:

   ```sh
   python -m tools.ops_backup create --output /private/backup/pre-upgrade.formbak
   python -m tools.ops_backup verify --input /private/backup/pre-upgrade.formbak
   ```

   Choose a real private path; the example is not a configured destination.
   PostgreSQL/S3 requires an independently verified matching provider recovery
   procedure. The local backup tool refuses cloud backends.
3. Inspect the target (read-only; exit 1 means not ready or an error):

   ```sh
   python -m tools.migrate
   ```

4. Explicitly apply the pending batch while writes remain stopped. For
   **development/test only**, the existing local command remains available:

   ```sh
   python -m tools.migrate --apply
   python -m tools.migrate
   ```

   For **staging/production**, the operator must independently verify matching
   database and photo recovery points, stop all writes, inspect the intended
   target, and then provide **both** the CLI confirmation and a one-command
   environment acknowledgement (not a persistent service environment setting):

   ```sh
   FORM_MIGRATION_CONFIRM=YES_BACKUP_VERIFIED_AND_WRITES_STOPPED \\
     python -m tools.migrate --apply --confirm-hosted-maintenance
   python -m tools.migrate
   ```

   Hosted `--apply` without both confirmations exits **2 before connecting**.
   Read-only inspection never requires approval. The acknowledgement is not
   evidence of backup integrity, maintenance exclusivity, correct target
   selection, or a tested provider restore. Do not bypass the gate by changing
   `FORM_ENV`; never set the acknowledgement in `render.yaml`, CI deployment
   variables, or the long-lived web service environment. Keep approval scoped
   to the explicit maintenance command after independently completing steps 1–3.

   A successful check exits 0. CLI output is limited to status/version counts;
   driver errors and connection details are not printed. The inspection command
   does not create a missing SQLite database or switch its journal mode.
5. Start the candidate worker set, verify `/readyz`, photo authorization, inventory
   state, backup recovery and the intended critical workflows before reopening.
   The checked-in staging templates require this explicit step; do not blindly
   launch an empty hosted database and expect startup to initialize it.

On failure, keep maintenance in place and preserve the recovery point. Correct
the cause or restore into an isolated location for investigation. A missing
column/key or checksum mismatch is not permission to erase or stamp history.

## Rollback boundaries

There is deliberately no destructive down-migration command. Dropping cleanup
tables could lose privacy-recovery work. Older app binaries that do not understand
the ledger, authorization protocol or cleanup queues must not run against a
post-upgrade writable database merely because extra columns appear compatible.

A recovery rollback needs the verified **pre-upgrade** database and matching
photos plus its matching app release. Restore to a new isolated destination,
verify complete records/object hashes, then follow a reviewed cutover procedure.
Do not overwrite a live healthy database. If writes were accepted after the
recovery point, restoring it loses those changes; preserve the failed environment
and agree reconciliation/data-loss handling before cutover. Late provider writes,
historical object versions and cleanup-watch retention need separate handling.

## Verification and remaining gates

Fixtures in `tests/fixtures/v07_*.sql` were extracted using `ast.literal_eval`
from the original archive's `SCHEMA` and `PG_SCHEMA` constants, trimming only
surrounding whitespace. No archive code was executed to create them. Source ZIP:
`DopeStuff_v0.7_Source (9).zip`, SHA-256
`910248d972c280f9f4f093940db2a08f401baab621fb388ec2cc6b8279d1b83d`.
Only schema definitions and synthetic records/photos are used in these probes.

Tests check original-schema adoption, every core table's retained records and
timestamps, legacy covers, existing cleanup queues, batch rollback, concurrent
startup, a real child-process crash, history/file drift, newer databases,
unsupported structure, orphan rows, hosted check-only startup and read-only CLI
inspection. An encrypted local pre-upgrade snapshot is restored into a separate
folder and compared for complete records and real WebP hashes after a simulated
post-upgrade data change. This is a **data restoration rehearsal**, not a claim
that an old app binary or a hosted deployment was rolled back.

Revision/fixture SQL uses `_sqlite.sql` names, not `.sqlite.sql`, so sensitive
database ignore rules do not remove runtime source from the Docker context.
CI builds the actual image, starts a disposable container without external
networking or host volumes, and checks real HTTP/cookies/CSRF, photo upload,
export, account deletion and the packaged migration CLI. That is an additional
candidate check, not a local Docker-build claim or deployed HTTPS evidence.

Disposable PostgreSQL CI repeats original-schema adoption, failed-DDL rollback,
concurrent upgrade, record preservation and catalog checks in a uniquely generated
test schema. Inspect the actual candidate run before claiming a PostgreSQL pass.
Managed-provider recovery, actual release-image rollback/cutover, dependency locks,
complete schema-drift auditing and measured operational recovery objectives remain
v1.0 gates. No paid environment or production migration was performed here.
