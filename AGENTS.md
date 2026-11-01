# Homepage NAS — AI tiếp quản

Repository: hunghvt-cyber/web-home (formerly Homepage-nas). Current documentation addendum: 2026-10-30 (Notes Firestore and verified backup evidence; dated reports retain their measurement dates).

Read [docs/OPERATIONS.md](docs/OPERATIONS.md) and
[docs/data-sources.json](docs/data-sources.json) before changing a backend,
deployment, data source, authentication or reporting workflow. Re-check current
configuration and production evidence; dated reports are not live status.

- Keep plain HTML/CSS/JavaScript; Python builds static pages into dist. Source content is in content/, images in public/images/. Build with python3 scripts/build.py; QR requires requirements.txt and a confirmed HTTPS PORTAL_BASE_URL.
- Homepage production is Vercel project homepage-nas / main. Never deploy into home-ai, hunghvt-notes or a lab project.
- NAS, Drive and Photos Daily aggregate reads currently use GAS/Drive via Vercel API adapters. Defaults and production use /api/nas-report and /api/backup-report; no Blob fallback. Verify generated config.js and backup-config.js.
- Photos Backfill progress is separate: /api/backfill-progress reads allowlisted GitHub reports/backfill JSON and current run metadata. Preserve original snapshot timestamps and label prior snapshots; do not mix its run sequence into GAS Daily. See docs/BACKFILL-PROGRESS-20261022.md.
- NAS timer checks every five minutes; GAS publishing uses event changes plus a 30-minute heartbeat. Preserve freshness timestamps, pending mutation identity, generation and sequence. Do not add collectors, timers or fabricate measurements.
- Supabase is the Homepage login attempt counter in the isolated homepage_login schema of CongchungVND. Password verification/encrypted sessions stay on Vercel. Do not modify exam tables, users or policies. Never bypass the limiter or silently fall back between counter stores.
- Homepage is the shared password authority for Notes since the 2026-10-26 rollout; cookies remain separate, not SSO. Owner accepted the login/revocation item on 2026-10-27; see docs/SHARED-PASSWORD-DECISION-20261026.md. Do not keep presenting this as pending user acceptance or Notes-on-Blob.
- Legacy Homepage Notes APIs are retired (410). /notes/ opens the independent Firestore Notes project. Its canonical source is hunghvt-cyber/web-notes on main; release/minimal-notes is a retained legacy/Code Inbox ref, not the current app source. Koofr is the Notes backup destination, not the live Notes datastore. GAS/Drive remains for reports only. Do not restore legacy Notes writers, import caches as authoritative data or assume deleted Blob Notes can be rolled back.
- Guide overrides/history are active in the isolated Koofr guide adapter after the owner approved all six static originals on 2026-10-21 and import/readback/save/reopen passed. KOOFR_GUIDES_READY=true. Old Blob overrides/history were not recovered; owner accepted Git originals for initialization. Preserve old Blob objects/credentials; do not rerun initialization or overwrite the live namespace. See docs/QR-KOOFR-20261019.md and docs/QR-KOOFR-COMPLETE-20261021.md. Public QR reading stays independent of login; unavailable Koofr returns explicitly labelled static originals and fails closed for writes. Preserve revisions, shared-password checks and printed slugs.
- Expense/Gemini bridge, reporting GAS and active Telegram webhook GAS are separate deployments. Active bot is @PoormanTest0219_bot using doPost; do not bootstrap the legacy polling bot.
- NAS Terminal is deployed at /nas/terminal/; read docs/NAS-TERMINAL.md before changing its API, agent or shared relay. Live NAS PTY qualification passed on 2026-11-01; historical candidate/offline claims are superseded. Preserve tmux persistence, key whitespace normalization and separate terminal/duplicates scopes. Never print keys or reinitialize NAS configuration for documentation work.
- Home-AI is a shortcut to an independent application, not a Homepage database/API dependency.
- No credentials, private keys, share tokens, raw events, recording paths or private data in repo/public output. Document secret names and storage locations only.
- Preserve local changes. No reset/clean/force-push/history rewrite. Inspect the exact diff and run checks appropriate to the change; build, JS syntax and local links for runtime source edits.
- Do not change NAS services, cameras, recordings, retention, tunnels, Google triggers or backup/sync engines as part of Homepage source/documentation work.
- Report deployment and verification limits truthfully. A selected report backend, READY deployment or successful report publish does not prove the underlying backup succeeded.



