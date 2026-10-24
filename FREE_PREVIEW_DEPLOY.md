# Free Render Preview (no payment card) — disposable test site only

**The normal `render.yaml` intentionally requests paid staging resources.** This alternative Blueprint is strictly for experimentation, with no actual customer data, no real payment information, and no promises of durability.

## Plan limitations

- Render web service: Free plan, sleeps after ~15 minutes of inactivity, loses any local files at restart. Dockerized app uses managed PostgreSQL and private R2 for its durable inputs, not local files.
- Render PostgreSQL: Free plan, **expires 30 days after creation**, no managed backups, 1 GB storage, limited connections. Do **not** import a real inventory or invite actual sellers.
- Cloudflare R2 can incur usage-based billing beyond its allowances; keep usage low, optionally set billing alerts. Restrict token to only `form-private-beta`, Object Read & Write; keep public bucket access off.
- Render may suspend a free web service for unusually high outbound traffic, including object-storage requests. Preview is not a production reliability guarantee.
- Do not accept payments or use marketplace auto-posting in this preview.

## UI walkthrough

1. Open Render dashboard → New → Blueprint. Connect GitHub repository `houseofnuwave/dope-stuff` if not yet connected.
2. Select branch **`deployment/free-preview-no-card`**. Set **Blueprint Path** to `render.free-preview.yaml` (not the default paid `render.yaml`). Review the generated resources: *both* the web service and the PostgreSQL database must show **Free**.
3. Before creating, enter the four requested R2 secret settings **in Render only**. Use `FORM_S3_BUCKET=form-private-beta`, `FORM_S3_ENDPOINT=https://ACCOUNT_ID.r2.cloudflarestorage.com` (replace ACCOUNT_ID privately), plus R2 Access Key ID and Secret Access Key from Cloudflare. Never put credentials in GitHub, screenshots, chat, or a public document. The Blueprint auto-generates the app session secret and pilot code.
4. If Render prompts for a card or shows a paid plan, **stop**. Do not proceed; re-check branch/path, workspace requirements and plan configuration.
5. Deploy only the free preview. Its fresh empty PostgreSQL schema is initialized on first startup; subsequent restarts only inspect existing migrations. Schema changes require the protected explicit upgrade procedure; never enable automatic hosted upgrades.
6. Once Render reports Live, visit its actual assigned HTTPS `*.onrender.com` URL. Check `/readyz` and the login page. Test only with fictional items and non-sensitive photos, verifying photo reload, owner scoping, and exported archives. Delete test data afterward.
7. Before inviting a real seller, move to stable hosting with managed backups, recovery drills, email verification/recovery, and explicit operational readiness checks. Free preview is **not** the five-seller pilot deployment.

Never merge the free-preview Blueprint over the regular staging configuration. Never claim a live URL until Render itself shows a successful deployment.
