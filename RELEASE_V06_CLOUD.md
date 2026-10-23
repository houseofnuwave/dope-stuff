# FORM Seller OS — v0.6 Cloud-Ready Candidate

**Date:** 2026-10-23  
**Base:** FORM v1.0 Founder Beta with v0.5 infrastructure milestone retained.

## What changed

1. Database adapter for PostgreSQL while retaining SQLite for Mac/local development. Includes Postgres schema initialization, parameter binding, SQL dialect mapping for FORM's current query set, hybrid Row support and account migration compatibility for future expansion.
2. Private S3-compatible photo storage backend (designed for Cloudflare R2), with server-only credentials, authenticated photo endpoints, WebP support, owner-scoped downloads and storage cleanup.
3. Invite-code protection on cloud pilot registration; anonymous session advertises invite requirement to the UI without exposing the code.
4. Render Blueprint describing a managed Postgres + Docker web service with HTTPS through Render. Runtime only accepts Render's verified external hostname automatically while in staging, or explicit trusted hosts.
5. A CI cloud smoke path using disposable PostgreSQL and MinIO, plus offline tests for adapter behavior, S3 access and cloud safety restrictions.
6. Legacy SQLite operations backup explicitly blocks use with PostgreSQL/R2 to avoid false confidence. Managed cloud backups and object recovery remain configuration/operations work.

## Test matrix

- 44 backend/offline tests: **passed locally**
- JavaScript parsing: **passed**
- Python compilation: **passed**
- Chromium desktop and mobile in-process UI flows: **passed**
- Render Blueprint YAML syntax: **parsed**
- GitHub Actions YAML syntax: **parsed**
- Real PostgreSQL + S3 server integration: **not executed in this environment** (the cloud-smoke CI job is prepared but requires a CI run)
- Hosted HTTPS login, Render and Cloudflare R2 integration: **not deployed or tested**
- Vendor secret and billing configuration: **owner action needed**

## What remains unchanged

The editorial FORM interface, original inventory, multi-photo galleries, listing readiness, assisted marketplace workflows, manual delist Action Center, sales/profit ledger, CSV import/export, account ZIP backup and restore, password update, and existing 37 tests.

## High-priority release gates

1. Confirm actual Render Postgres + R2 upload/read/delete and restore under network outage.
2. Run CI cloud-smoke, review its failures, and harden connection handling.
3. Establish operator backups, R2 retention, and one isolated disaster recovery rehearsal.
4. Invite only the founder and 3–5 trusted sellers; investigate any double-sell/removal incidents and account access issues.
5. Before public use: complete account recovery, email verification, distributed rate limiting, privacy/terms, monitoring, payment readiness and formal marketplace access assessment.

**v0.6 means cloud deployment code prepared, not hosted availability.**
