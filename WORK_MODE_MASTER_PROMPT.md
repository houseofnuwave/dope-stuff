# COPY EVERYTHING BELOW INTO CHATGPT WORK

## MISSION

Act simultaneously as my **principal software engineer, hands-on full-stack developer, head of product, staff security engineer, senior UI/UX designer, growth/product analytics lead, and technical cofounder**. Your responsibility is to turn the attached, functioning **FORM Seller OS MVP repository** into a credible, launchable resale-seller SaaS with an excellent customer experience, a secure data foundation, and a realistic path from private beta to paid pilot.

This is a **real product build**, not a speculative analysis, Figma-only mockup or marketing landing-page exercise. Work directly from the supplied zip/repository, produce tested code, and maintain a working deployable application. Treat me as founder/product owner, but challenge decisions that create legal, reliability, margin, or customer-trust problems.

**Business objective:** Build software that makes independent fashion resellers more organized and profitable through accurate inventory records, quick listing preparation, clear channel status, and reliable sales/profit tracking. Earn recurring subscriptions by demonstrably saving time and reducing errors. The ideal first customer manages 20–500 unique pre-owned or deadstock clothing items and publishes to at least two resale platforms.

**Positioning:** Premium, minimalist **seller operating system** — not a bot marketed as “post to every marketplace instantly.” It must look editorial and calm but feel more dependable than a spreadsheet. FORM is a **working name**; research trademark/domain before public brand commitment. Keep this project separate from OF SUN & INK, which is a creative-wellness brand.

**Pricing hypothesis, not fact:** Free pilot, future Starter $14.99/month, Pro $39.99/month, Studio $89.99/month. Test willingness to pay before implementing complex tiers. Do not advertise future roadmap features as delivered, and do not collect a subscription until the user has received what was promised.

## HARD INPUTS / FIRST ACTIONS

1. Inspect the entire attached `form-seller-os-mvp.zip`, read `README.md`, `ENGINEERING_SPEC.md`, `SECURITY_AND_LAUNCH_GATES.md` and `PILOT_PLAYBOOK.md`, and inspect existing source code before writing new code.
2. Start the current application locally with the documented commands; run `pytest -q` and `node --check app/static/app.js`. Show the pass/fail status and enumerate any defects found. **Do not replace a functioning app with a fresh unrelated scaffold.**
3. Inspect the actual UI with the cloud browser in Work mode when available. Verify at desktop 1440px and mobile 390px, then fix defects. Test register → create item → prepare listing → mark self-published → mark sold → review delist queue.
4. Audit the current implementation against the acceptance criteria and security gates below. Distinguish **working**, **partial**, **not implemented**, **blocked by marketplace approval**, and **out of scope**. Record evidence in `docs/BUILD_STATUS.md`.
5. Preserve the existing data model and user content. When changing persistence, write and verify reversible migrations and backup instructions. Keep development, staging, and production data strictly separate.
6. If an external service or credential is needed (deploy hosting, email, Stripe, domain, object storage, OAuth/partner program), stop only for the exact authorization required. Do not request secret keys in the chat, hardcode them, fabricate connections, or claim success if credentials are unavailable.

## PRODUCT REQUIREMENTS, IN PRIORITY ORDER

### P0 — finish a secure, trustworthy closed pilot

- Multi-user seller workspaces: self-registration, login, logout, email verification, password reset, account deletion, basic profile; seller-owned records cannot be accessed across accounts.
- Canonical inventory: title, brand, category, condition, size, color, SKU, acquisition cost, ask price, shipping estimate, quantity, notes, multiple original photos, timestamps; accurate totals, search, filters, pagination, mobile usability.
- CSV bulk import with preview/validation, atomic rollback, duplicate SKU handling; export inventory and sales for seller ownership. Protect against spreadsheet formula injection.
- Listing studio for marketplaces chosen by seller. Produce **factual, channel-specific drafts** (title, description, price/condition mapping) and a checklist of required information. Do not invent materials, sizes, authenticity, provenance, flaws, availability or buyer demand. Reuse seller-confirmed details and ask for missing required facts.
- Clear publishing states: not prepared, ready, seller-reported live, verified API live (only if an approved connector truly confirms), requires manual delist, reported removed, sync error. Each listing is traceable to canonical SKU.
- Item sale workflow: actual sale channel and final price, fees, paid shipping, cost, timestamp, calculated contribution; transaction-safe single-quantity sale; prevent accidental duplicate sale; display outstanding manual delists loudly with acknowledgements.
- A first-class **Integration Capability Registry** so each marketplace displays its *real* capabilities. Every assisted channel must be labeled “manual”. Never imply background syncing.
- Pilot usability analytics with consent and privacy controls: activation, first inventory added, first listing kit copied, first seller-confirmed external publication, sale recorded, delist task completed, support issue. Avoid invasive session recording by default.
- Feedback intake, pilot interest list, support contact, privacy/terms/acceptable-use text appropriate to jurisdiction after legal review.
- Production-equivalent staging: TLS/HTTPS, environment isolation, secure deployment, durable database backups, restore rehearsal, instrumentation, basic alerting, deployment rollback procedure.

### P1 — make it acceptable to **charge** for

- Integrate Stripe Checkout for recurring plans, Stripe Customer Portal, subscription status, signed idempotent webhooks, payment failures, renewals, refunds/cancellations, and entitlements. Keep all card details at Stripe; no custom credit-card storage. **Use test mode first and test all lifecycle scenarios.** Never enable real checkout until founder approves the production checklist.
- Add a founder-accessible billing/admin dashboard showing subscriber count, churn, trials, revenue, product activation, failed charges and support tickets without exposing user data. Role-based access control, audit trail, optional MFA for admin.
- Stripe-provisioned trial and plan limits should be enforced on the backend, not solely UI. Usage limits should be measured and fair; never lock users out of exporting their data.
- Improve photo ingestion and processing. Re-encode and strip EXIF; provide crop/rotate and honest background cleanup where possible. Never create fake labels, hide damage, or infer authenticity automatically.
- Explicit customer-facing SLA/maintenance banner, support workflow, receipts, help center, onboarding checklist and consent-based transactional emails.
- Migrate from SQLite to Postgres and cloud object storage when real multi-instance hosting/concurrency requires it; schema migrations, indexes, row-ownership policy and backup procedures. Avoid premature infrastructure complexity.
- Build browser-based E2E tests (Playwright) and CI test gate on pull requests; security scanning, typed contracts, audit logs, error aggregation.

### P2 — integrations, **only if authorized**

- Research current official APIs and partnership terms directly from authoritative sources: eBay Sell Inventory API, Shopify Admin GraphQL and webhooks, Depop private Selling API, plus current access for Grailed, Facebook Marketplace, Poshmark, Mercari, Vestiaire and Vinted. Record proof of rights, intended scope, restrictions, rate limits and status of applications in `docs/INTEGRATIONS.md`.
- Request founder approval before initiating partner applications, accessing seller accounts or installing invasive browser extensions. Do not automate protected flows against platform policies, bypass bot protections or harvest session cookies.
- Implement **one** authorized integration end-to-end before adding more: OAuth or approved access → secure token storage → publish (if permitted) → fetch status → reconcile inventory → failure handling → retries/idempotency → disconnect/revoke, with sandbox contract tests. eBay or Shopify may be useful candidates depending on access and audience needs.
- Never implement unsafe “cross-post everywhere” claims; clearly differentiate fully connected, partially connected, manually assisted and unsupported platforms. In-app messages should explain whether delisting occurred automatically or needs human attention.
- Only after real partner approvals and substantial seller demand, add paid AI assistance, bulk editing, team accounts, accounting exports and configurable repricing. Keep human review on listing claims and inventory-changing actions.

## EXPERIENCE AND DESIGN SYSTEM

The code already has an editorial aesthetic. Preserve its identity unless user research uncovers strong usability issues. Aim for the restraint of premium editorial software, not a generic AI dashboard.

- Colors: warm off-white `#F6F4EF`; white `#FFFEFA`; ink `#20251F`; sage `#586C54`; pale sage `#E6ECDF`; hairline `#E6E6DE`; amber only for warnings; red only for urgent action/errors.
- Type: elegant restrained serif (headings) plus crisp accessible sans-serif (body/data); use a legally distributable font stack. Avoid font file sharing.
- Core mobile journey: photograph → record verified details → choose channels → copy/create draft → open marketplace → mark self-published. Keep it usable one-handed at 390px.
- Data-dense desktop journey: inventory table → mass actions → channel availability → sale ledger → action-required queue. Support keyboard shortcuts only if discoverable.
- UX truthfulness: no fake AI spinner, invented sale counts, “automatic sync” labels for manual workflows, false scarcity, misleading pricing or prechecked opt-ins. Always distinguish example/demo data from real records.
- Accessibility WCAG 2.2 AA target: focus handling for dialogs, label inputs, color contrast, keyboard navigation, mobile touch targets, nonvisual error summaries, and preference for reduced motion.
- Loading, empty, error, offline, expired-session, permission-denied and conflict states must be explicitly designed.

## TECHNICAL QUALITY BAR

- Existing stack: FastAPI/Pydantic/SQLite/vanilla JS. Start here; propose upgrades only with measured benefits, estimated cost/risk and migration path. If migrating front-end, use a well-typed React/TypeScript framework and preserve test coverage. Do not run parallel incompatible apps indefinitely.
- Architecture: clear boundaries for domain logic, persistence, auth, listing-kit generation, billing, and marketplace adapters. Service-to-service capabilities are explicit and fully testable.
- Treat `user_id` ownership checks and CSRF on every sensitive endpoint as non-negotiable. Production sessions must be secure, HttpOnly, properly scoped and rotated. Rate limits need shared backing for horizontal scale.
- Protect against XSS, SSRF, open redirect, IDOR, path traversal, deserialization, token leakage, malicious CSV formulas, image decompression bombs, webhook replay, duplicate orders and multi-seller data bleed.
- Keep financial data as integer minor currency units or exact decimals, never binary floats. Profit metrics must state what costs are included and excluded; do not treat inventory asking value as revenue.
- Use signed Stripe webhook events and durable idempotency keys. Implement payment-state access gates server-side and reconcile out-of-order webhook arrivals.
- Encrypt tokens at rest with managed secret storage; least-privilege API scopes, revocation and disconnect, audit logs and no passwords for third-party marketplaces.
- Observability: privacy-safe structured logs, request IDs, exception grouping, slow query metrics, sync backlog and alert thresholds. No personal data in analytics events by default.
- Test levels: unit, API integration, browser E2E, accessibility, backup/restore, payment webhook replay, idempotent sale, upload validation, concurrency, negative access controls, realistic latency and failure injection.
- Runtime: document environment variables, one-command local startup, pre-commit checks and CI, migrations, staging deployment, secrets injection, production smoke tests, backup restore, disaster recovery.

## SUCCESSFUL SELLER JOURNEY — ACCEPTANCE TEST

Given a registered new seller with an empty account:

1. They sign in and see **zero**, not fictional numbers. Onboarding explains the manual nature of all integrations.
2. They upload one real photograph and create one garment with a unique SKU, known defects, cost and price. The photo remains private to this account.
3. They prepare a Grailed listing and a Depop listing. The listing kit uses only verified user-provided data; both actions are visibly **assisted**, not remote-posted.
4. They confirm they manually published on both platforms. Both channel statuses become **seller-reported published**, never API-verified.
5. They record a sale on Grailed for $200, with $20 fees, $10 shipping paid and $70 acquisition cost. Profit shown is **$100**. The same item cannot be sold again accidentally.
6. They see an urgent **Depop removal required** task; the app does not falsely claim to have removed the external listing.
7. They remove the Depop listing themselves, confirm in the app, and see the manual task clear with an audit trail.
8. They export their inventory and sales data in a spreadsheet-safe format.
9. A second account cannot read, edit, download, or enumerate any first-account items or photos.
10. The same flow works on a 390px mobile browser with appropriate screen-reader labels, clear errors and no UI overflow.

## PRODUCT METRICS AND TEST PLAN

Instrument these metrics without making up baseline data:
- Activation: % of registered sellers with ≥3 real items entered within 48h.
- First value: median minutes to create a verified, copy-ready listing vs baseline manual workflow.
- Workflow completion: % who copy a kit, publish manually, and report the channel correctly.
- Retention: % of activated sellers completing a meaningful action on week 2 and week 4.
- Reliability: item double-sale attempts, incorrect statuses, app errors, uncompleted delist tasks, sync failures if later integrated.
- Monetization: % of qualified sellers who accept a real paid pilot offer, then convert through approved checkout after value proof.
- Per-user LTV and gross margin: only forecast with explicit churn, pricing, payment fees, hosting and support assumptions. Never label modeled revenue “actual.”

Conduct discovery with 10 actual resellers and 5 usability tests before implementing expensive channel integrations. Maintain a feedback log sorted by pain severity, frequency, commercial value and complexity. Do not overfit to one founder's inventory.

## GO / NO-GO RULES

**Do not launch public paid subscriptions if:**
- Billing is not integrated and tested end-to-end with signed webhooks.
- There is no terms/privacy/cancellation process, secure hosting, backups or customer support path.
- A marketplace is advertised as automated without permission or verified functioning.
- Product data or photographs can be read across sellers.
- Sales or inventory transitions can duplicate or silently lose stock.
- Customer information is used for unconsented marketing or production secrets leak into code/logs.

**Do not expand feature scope if:** the core seller-to-sale journey is unreliable; instrumentation is missing; users aren't completing the workflow; no one has tested a willingness-to-pay offer; or marketplace partner approvals are unresolved.

## HOW TO WORK / DELIVERABLES

- Build in clear small milestones, each containing: changes, new tests, observed result, known risks, and next decision. Use branch commits when repository access exists.
- Minimize questions; make and document reversible technical defaults. Ask only when a decision materially affects cost, legal risk, product positioning, data destruction, payment activation or access permissions.
- Do not execute real payments, send marketing emails, deploy publicly, incur external charges or connect third-party seller accounts without explicit founder authorization.
- Keep the founder updated with concise outcomes, not long stream-of-consciousness process logs.
- Produce **working source code**, `docs/BUILD_STATUS.md`, screenshots from actual tested builds, full setup and deploy runbook, machine-readable test report, change log, security checklist, and backlog ranked by risk/return. If deployment access is available and authorized, provide staging URL; otherwise provide a runnable artifact and exact steps to deploy.
- At the end of each milestone, answer: (1) What is operational? (2) What was tested? (3) What blocks paid launch? (4) What exact choice/permission is needed from founder? (5) What 20% of next work creates 80% of customer value?

## START NOW

Begin with **Milestone 0: repo audit + green local execution + mobile/desktop UX smoke test**. Then implement **Milestone 1: trustworthy onboarding, seller data ownership, import/export and listing workflow polish**. Prioritize any serious bugs found over new features. Move next to **Milestone 2: secure deployable closed pilot**. Do not implement marketplace bots, subscription billing, or irreversible infrastructure changes ahead of the associated approvals. Show me an actual working MVP at every milestone.
