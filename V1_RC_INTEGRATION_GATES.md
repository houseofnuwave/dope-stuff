# V1 release-candidate integration and approval gates

Status: **planning only — NOT a release approval, staging verification, or evidence that draft PRs work together.**

## Baseline and review
- Base: `main` at `1aab6c920b58cfd06d44ede077474901001d2782` (2026-11-04 review).
- Review all open draft PR heads and CI conclusions again immediately before assembly. Do not assume branch CI is equivalent to integrated CI.
- Keep `main` untouched. Create a separate disposable integration branch; cherry-pick/reconcile reviewed changes there, without merging any PR.
- Record each source PR number, source head SHA, selected commit SHA, conflicts, and any manual resolution in the integration PR description.

## Dependency and overlap review
| Draft PRs | Integration risk | Required validation |
| --- | --- | --- |
| #10 and #14 | Both change hosted startup policy | Hosted Render development/ephemeral settings rejected; hosted invite missing/short rejected; valid hosted startup passes |
| #14 and #16 | Hosted invite requirement versus staging Compose environment | `docker compose -f compose.staging.yaml config --quiet` rejects unset/empty invite; valid synthetic 16+ character invite reaches app startup |
| #12 and #13 | Both change `tools/ops_backup.py` | Atomic no-overwrite behavior and exact database/photo reference verification both remain enforced |
| #8, #9, #10, #11 | Cloud TLS, object storage, hosted startup and migration operator checks | Disposable PostgreSQL/MinIO integration and refusal of unauthorized hosted migrations |
| #15 and other container changes | Build reproducibility and image integrity | Real image builds and `python -m pip check` succeeds |

This is a review map, **not** an assertion that any PR is conflict-free. Review all remaining open PRs and changed files before selecting an assembly order.

## Required evidence on one integration head SHA
1. `python -m pytest -q`: capture pass/fail/skip/warning counts, not merely exit status.
2. `python -m compileall -q app tools tests` and `node --check app/static/app.js` (when Node is installed).
3. Desktop and mobile Chromium seller journeys, including no JS exceptions and no horizontal overflow.
4. Actual Docker image build, HTTP/CSRF/auth and packaged migration smoke.
5. Disposable PostgreSQL migrations and private MinIO/S3 read/write/delete and recovery tests.
6. Hosted configuration negative tests: missing invite, unsafe Render mode, absent durable DB/object store, migration without both acknowledgements.
7. Encrypted local backup regression: concurrent destination, symlink, invalid/missing photo references and clean restore.
8. Review the GitHub Actions workflow for the **same integration commit SHA**; document each job's conclusion and link to its run. Do not describe a queued job as passing.

## Operational gates that CI cannot establish
- Obtain owner-approved persistent staging with verified HTTPS identity and isolated synthetic data. Do not provision paid services without explicit approval.
- Verify a **real provider** PostgreSQL and private object-store backup and isolated restore, with documented recovery time and data-loss window. Local SQLite/MinIO tests do not satisfy this.
- Confirm invite-only onboarding, session/security settings, monitoring, retention/deletion procedures and operator runbook.
- Configure and verify branch protection and required checks before any authorized merge.
- Explicit owner approval is required for merge, public deployment, paid provisioning and any real seller data.

## Release decision
Mark **NO-GO** while any integrated CI check is failing, missing or pending, any backup restore is unverified, hosting is ephemeral, branch protection is absent, or required owner approval has not been given. Never claim marketplace synchronization: external marketplace listing and delisting remain manual seller actions.
