# FORM Seller OS v0.2 — Implementation and handoff

**Release date:** 2026-10-23  
**Status:** local seller pilot, not commercial production.

## Delivered
- Recovered the original 29-file MVP; preserved seller auth, inventory, assisted publishing, sale accounting, and delisting reminders.
- Added `item_photos` table and non-destructive v0.1 photo migration.
- Secure private image gallery (8 photos/item), strict file limits, re-encoding to WebP, EXIF stripping, first-image cover logic, deletion + CSRF checks.
- Added duplicate-aware, non-mutating CSV preview, downloadable blank CSV template, and atomic confirmed import.
- Updated desktop/mobile item editor and first-inventory dashboard.
- Added five regression tests: multi-photo flow, invalid upload/cap, account isolation, CSV preview/import errors, and photo migration.
- Created Mac quick-start and founder inventory test checklist.

## Verified in this environment
- `python -m pytest -q` → 12 passed.
- `node --check app/static/app.js` → no JS syntax errors.
- `python -m compileall -q app` → passed.

## Validation caveat
Browser automation was attempted but Chrome navigation to the test server was blocked by this hosted execution environment (`ERR_BLOCKED_BY_ADMINISTRATOR`). This is a tooling restriction, **not** evidence that the app itself fails. Therefore the new v0.2 UI is NOT claimed browser-E2E verified. Run manual checks on Mac before recruiting testers. Earlier image references in docs may depict the v0.1 UI rather than the updated gallery and import preview.

## Release acceptance checklist (run manually)
- Desktop and mobile: register, sign in, sign out.
- New inventory item; upload 3 photos; edit item; delete primary; verify new cover.
- Import CSV with 2 valid items; verify preview creates zero rows until confirmed.
- Preview duplicated SKU; verify nothing imported and visible error.
- Prepare channel kit, copy title/description, manual publish confirmation.
- Mark test sale; verify net profit math and manual removal notice.
- Check 390px viewport for horizontal overflow; confirm focus and keyboard navigation.

## Security / infrastructure blockers before paid beta
- HTTPS hosting with robust secrets, email verification and resets.
- Object storage, tested backups/restores, database migration tooling and Postgres for scaling.
- Shared rate limiting, monitoring/alerts, abuse prevention, privacy/terms and data deletion.
- Stripe hosted billing + verified webhooks (only after product validation).
- Official authorization for any third-party marketplace automation.
- App branding/trademark review and privacy impact assessment.

## Suggested next engineering milestone
Publish a **private staging instance**, finish Playwright desktop/mobile acceptance tests, and add photo sorting/reorder + item completeness score only if the first sellers actually need them. Don't build unsupported autoposting integrations.
