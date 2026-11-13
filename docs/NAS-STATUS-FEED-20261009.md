# Homepage AIO status feed

## Quick read

- **Purpose:** publish a small, allowlisted NAS status snapshot for Homepage. The publisher reads existing monitoring/maintenance evidence; it does not start another NAS scan.
- **Retention input:** the parser reads the coordinator aggregate `state/retention-auto/latest.json` and verifies only result files referenced by that aggregate.
- **Important limitation:** a standalone APPLY result that is not referenced by the aggregate is invisible to this parser. Therefore Homepage can show `unknown` even when a separate APPLY result has independently passed verification.
- **Nov 12 audit finding:** the standalone 500-file APPLY result was PASS, but the Nov 11 aggregate did not reference it; the local snapshot consequently showed retention `unknown`.
- **Runtime distinction:** the NAS host was running the publisher from a separate `Homepage-nas` checkout using the GAS/Drive backend. This repository documents the canonical `web-home` implementation; do not assume this exact checkout or transport is installed on the NAS.

## Publisher design

Implemented a Python publisher that reads the existing 15-second FnNAS monitoring cache and the last maintenance summary. It does not start another NAS scan or include collector payloads in the upload. The allowlisted schema contains only `schema`, source `updated_at`, camera/NAS states, maintenance/retention states with their own measurement time, and minimal filesystem, RAM, and swap metrics. Missing, invalid, failed, or older-than-15-minute health measurements become `null`; schema version remains 1 and the UI accepts older payloads without `health`.

## Publishing

- Vercel's official Python Blob SDK (`vercel==0.11.6`) writes the fixed public pathname `nas-status.json`, with overwrite enabled, no random suffix, JSON content type, and a 300-second cache lifetime.
- The publisher reads its token at runtime from `~/.config/homepage-nas/blob-token`; no credential is stored in this repository.
- A nonblocking file lock prevents overlapping runs. The SDK call has a 25-second deadline and the systemd unit a 35-second limit. Upload errors exit nonzero without touching the monitoring collector.
- Runtime snapshot output is under `~/.local/state/homepage-status/` and is not tracked by Git.

## Evidence and freshness

- NAS state is derived from collector root and volume filesystem measurements. The overall cache timestamp is preserved as `updated_at`.
- The Collector cache provides filesystem `status`, `total_bytes`, and `available_bytes` for `/` and `/vol1`, plus `host.memory.status`, `available_bytes`, `total_bytes`, `swap_total_bytes`, and `swap_used_bytes`. The publisher maps those exact aggregate swap fields to `health.swap.total_bytes` and `health.swap.used_bytes`; it does not require or infer a source `free_bytes` field.
- Camera state uses existing per-camera cache evidence: recent `last_video_at`, `status=recording`, `recorder_active`, and `sample_growth`. A running container alone is insufficient. If the camera cache or recording evidence is missing or stale, its state is `unknown`.
- Maintenance reads only `LAST_UPDATE` and `STATUS` from its summary. It preserves that result and its measurement time regardless of age; the summary's `RETENTION=DRY_RUN` is never used as a verified retention result.
- Verified retention reads the coordinator aggregate at `STATUS_VERIFIED_RETENTION` (default `/vol1/Docker/tapo-nas-lab/state/retention-auto/latest.json`). It validates the aggregate date and timezone-aware `started`/`finished`, overall status and `jobs[]`, then verifies each referenced result's SHA-256, schema and `mode=APPLY` under `STATUS_VERIFIED_RETENTION_RESULTS` (default `/vol1/Docker/tapo-nas-lab/state/verified-retention`). A dry run or incomplete/inconsistent result becomes `unknown`; valid results use aggregate `finished` as `measured_at`. This parser does not scan the result directory or discover an unreferenced standalone APPLY result.
- The page marks camera/NAS telemetry stale when snapshot `updated_at` is older than 15 minutes. That stale marker does not replace the historical maintenance/retention result; their latest state and measurement time remain visible.
- The payload is limited to the allowlisted fields and does not expose IPs, recording paths, events, secrets, or administrator details.

## Verification

- Two successful uploads used the same returned Blob URL. Listing the dedicated store found exactly one object, `nas-status.json`.
- The public URL returned HTTP 200 and `application/json`. A request carrying the Homepage origin received `Access-Control-Allow-Origin: *`.
- Homepage `status_url` points at that returned URL. UI source preserves the existing camera/NAS five-minute refresh, loads maintenance/retention on page open, and marks only telemetry stale from the snapshot timestamp.
- QR assets and Home-AI shortcut markup were not changed by the status feed implementation.
- Snapshot fixtures cover previous-day and current-day result timestamps, verified retention dry-run, old telemetry snapshots, fresh recording evidence, and missing sources.

## Issue #53 — verified aggregate recovery

`scripts/reconcile_retention_aggregate.py` is an explicit recovery helper for a single verified standalone APPLY result and a blocked aggregate. It never runs a retention operation. Its default invocation prints a read-only plan; `--apply` is a separate operator action that updates only `latest.json`, after rechecking the reviewed aggregate SHA under a lock, and preserves the prior pointer as `latest.json.before-<run-id>`. Dated historical aggregates and standalone results are not edited. The helper fails closed unless exactly one pending `ARCHIVED_EVENTS` job and exactly one matching result exist, the result is within 24 hours of aggregate start, rows are complete and within existing 500-file/24-GiB bounds, and local/remote size and SHA evidence match.

The normal publisher remains aggregate-only and does not discover standalone results. On a successful referenced result it may include the safe run ID, file count, and byte count in the status payload; it never includes row contents or local paths. Schema 1 consumers accept the optional retention fields. The UI displays aggregate measurement time and verified totals. This repository change does not reconcile live state, invoke a publisher, upload a report, or establish that this checkout is installed on the NAS.

## Schedule

The user-level `homepage-status-publish.timer` runs one minute after boot and then every five minutes. It is separate from the collector and maintenance timers. It does not push GitHub or trigger a deployment on each run.

## Runtime reporting audit — 2026-11-12

Read-only inspection confirmed the user-level five-minute publisher timer is
active. Its latest observed service invocation completed successfully at
17:19:54 +07; the local snapshot at 10:19:41Z contained
`retention.state=unknown` with no `measured_at`.

The host's unit invokes
`/vol1/Docker/projects/Homepage-nas/scripts/publish_status.py` (SHA-256
`8257909ddaeacad03e856ec8484c2425ec1d83287ba2e8854f9160f8a23a22b1`) from a
checkout whose remote is `hunghvt-cyber/Homepage-nas`, branch
`feat/gas-reports-after-notes-retirement-20261018`, commit
`2be7d188c27cbd72f0b9df3abb29a101c3b9b4c2`. The canonical `web-home/main`
publisher file at audit commit `df15c613f11c3b57a75c515f0f9717e4e0045484`
has SHA-256 `387f8c38588c446b1620e29db217fab0c9f3cc8a3be86d23033b038ef73e5b14`.
The full files differ in transport/backend code, but the inspected
`read_verified_retention()` implementation is the same. The installed
`gas-drive.conf` selects `STATUS_BACKEND=gas-drive`; no retention input-path
override was found in the service or its drop-ins. This confirms the current
parser contract, but does not mean `web-home/main` itself is the running file.

The verified Nov 12 standalone APPLY is
`state/verified-retention/run-gklw3h1e/result.json` (SHA-256
`9ca95ae1df964ed814c8d36ce4a145757eb40c5cf786514912199806e552677f`). It
contains `mode=APPLY`, `policy=ARCHIVED_EVENTS`, 500 rows, 3,915,163,894 bytes,
and completion `2026-11-12T06:47:49.100029Z`. The aggregate the parser reads is
still the Nov 11 coordinator report (SHA-256
`54d7478df89a4ad306cf274578fd8764698581ece3697bbcbfb260a9835abb3c`): status
`BLOCKED`, job 1 and 2 `PASS`, and job 3 `AUDITING` without a result reference.
It does not reference the Nov 12 standalone APPLY, so the parser correctly
returns `unknown` under its documented aggregate contract.

No publisher, GAS endpoint, or browser was manually invoked in this audit; the
live remote acknowledgment was not verified. The result and aggregate were
read and hashed only. This section records the observed integration gap; it
does not change the parser contract or authorize editing runtime state.
