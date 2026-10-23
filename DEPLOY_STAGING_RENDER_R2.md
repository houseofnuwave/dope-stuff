# FORM v0.6 — Private hosted beta deployment

**Deployment status:** The repository is ready for owner-account configuration, but **no live deployment has been performed**. Do not put real seller data in a new deployment until all cloud integration, backup, access control, and account deletion checks have passed.

## Architecture

- **Web app:** FastAPI + the existing editorial responsive FORM interface, on one Render Docker web instance.
- **Database:** dedicated Render-managed **PostgreSQL**, not SQLite on a disposable disk.
- **Photographs:** a separate **private** Cloudflare R2 bucket, accessed by backend-only credentials through S3-compatible boto3 calls. Public image URLs and browser-side credentials are not used.
- **TLS:** Render's `https://YOUR-SERVICE.onrender.com` staging hostname. A paid custom domain is optional at this stage.
- **Access:** registered seller accounts AND a 16+ character pilot invite code for registrations. This is an early beta access gate, **not** full invitation management or email verification.

## What the owner must do (no passwords sent in chat)

1. Create a **private GitHub repository** containing the source files in this package. Remove any local `.env`, `data/`, `__pycache__/`, or test-generated archives before uploading. The packaged ZIP already excludes local secrets and databases.
2. In Cloudflare, create a dedicated private R2 bucket such as `form-private-beta`. **Do not enable public access** or attach a public custom domain. Issue a scoped R2 token with appropriate bucket object read/write/delete/list permissions. Keep the account ID, S3 endpoint, Access Key ID, and Secret Access Key in a password manager.
3. In Render, connect that GitHub repository and select **New → Blueprint**. Render will detect `render.yaml`, creating the staging web service and PostgreSQL database. Review the cost before accepting the infrastructure.
4. When prompted for secret variables, configure `FORM_S3_BUCKET`, `FORM_S3_ENDPOINT` (e.g. `https://<account-id>.r2.cloudflarestorage.com`), `FORM_S3_ACCESS_KEY_ID`, and `FORM_S3_SECRET_ACCESS_KEY`. Never commit or paste these values into chat. `FORM_SESSION_SECRET` and `FORM_PILOT_INVITE_CODE` are generated automatically by the Blueprint.
5. Wait for the deploy to finish. Render supplies `RENDER_EXTERNAL_HOSTNAME` and `RENDER_EXTERNAL_URL`; FORM staging accepts only an exact, validated `*.onrender.com` hostname from that provider environment. No custom domain is required.
6. Visit your `https://...onrender.com` site on Mac and iPhone. Confirm `/readyz` returns a healthy response (and the protected inventory requires login). Copy the pilot invite code from Render's private environment panel to your *own* password manager; share the code with pilot sellers through private invitations, not in a public post.
7. Create a test seller account, upload a real garment item with three photographs, reload it, record a simulated sale, download the account export, and verify its photos. Test with a second seller account for data isolation.
8. **Before any customer invite:** establish provider PostgreSQL backup retention and separate private-bucket protection/recovery procedures. Do a restore drill into an **isolated test instance** and monitor failures, database costs, storage usage and errors. For the pilot, test account deletion and verify that database and photo objects are removed; examine errors/orphans.

## Important deployment variables

`render.yaml` manages `FORM_ENV=staging`, `FORM_CLOUD_MODE=true`, the managed database connection string, `FORM_PHOTO_STORAGE=s3`, a stable secret, secure cookies, a private invite code, and temp application data. Only R2 credentials/bucket/endpoint must be supplied manually.

For a custom domain later, set both `FORM_ALLOWED_HOSTS` (comma-separated exact hostnames) and `FORM_PUBLIC_ORIGIN` (matching HTTPS origin). FORM automatically also trusts Render's own exact hostname for health checks while running on Render staging. **Do not** use wildcard hosts or `http://` as a hosted public origin.

## Cloud integration verification (not yet executed)

The repository includes a cloud integration test job that starts disposable PostgreSQL and MinIO services and runs `python -m tools.cloud_smoke`. It requires GitHub Actions and Docker access. The test script contains strict environment/database/bucket-prefix guards to avoid operating on real seller data. **A passing local SQLite test suite alone does not verify hosted PostgreSQL or R2.**

## Disasters and limitations

- The previous `python -m tools.ops_backup` encrypted operator snapshot **only supports local SQLite + local images** and intentionally refuses cloud deployments. In v0.6, rely on configured PostgreSQL managed backups plus independent private object-storage recovery, and perform a restore drill. These are owner tasks, not delivered as automated recovery code.
- A database transaction and R2 object write are not a distributed transaction. Upload failures roll back metadata where possible, but storage outages can leave orphaned objects or partial cleanup. Do not claim guaranteed erasure or RPO/RTO until operational audits and a reconciliation job exist.
- Existing v1 seller ZIP files can be restored into fresh same-email accounts using FORM's authenticated restore flow. There is no automatic bulk migration of all sellers from the old SQLite instance.
- The login rate limiter is still in-process. Email verification, password reset, enforceable invite lists, identity safeguards, billing, official marketplace integrations, error alerting, privacy/legal review and production disaster recovery remain future release gates.
- **Do not accept paying users at this milestone.** Do not import sensitive customer datasets before cloud infrastructure is independently verified.

## Links to vendor documentation

Render Blueprint: https://render.com/docs/blueprint-spec
Render environment variables: https://render.com/docs/configure-environment-variables
Render hostname environment: https://render.com/docs/environment-variables
Cloudflare R2 S3: https://developers.cloudflare.com/r2/api/s3/api/


## v0.7 Recovery deployment gate

The default hosted setting is `FORM_RECOVERY_MODE=disabled`. Before enabling it, verify a domain you control with a transaction-email provider; use the hosting provider's secret manager to set `FORM_RECOVERY_MODE=smtp`, `FORM_SMTP_HOST`, `FORM_SMTP_PORT` (465 or 587), `FORM_SMTP_USERNAME`, `FORM_SMTP_PASSWORD`, and `FORM_SMTP_FROM`. The reset link uses the validated `FORM_PUBLIC_ORIGIN`; never build it from arbitrary request host headers. Complete an on-device password reset and deliverability test and confirm old sessions are invalidated.

For public use, implement shared rate limits, email verification for new accounts and recovery abuse monitoring. Do not enable the local recovery mail spool in a hosted environment (the application rejects it at startup).
