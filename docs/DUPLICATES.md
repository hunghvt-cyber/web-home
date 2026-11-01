# Dọn file trùng — NAS, 01/11/2026

`/don-file-trung/` opens from a small Homepage shortcut in a new tab. The owner selected
NAS for large inventories. This increment is **read-only**; no delete, move, quarantine,
retention/sync changes or content downloads. Drive and Koofr are independent scan scopes.

## Transport and access

Owner session -> POST `/api/auth?service=duplicates` -> five-minute HMAC ticket with
`aud=nas-duplicates` -> existing outbound WebSocket relay -> NAS agent -> typed scanner.
No new port, tunnel, database service or cloud credential in Vercel/browser. The signing
and agent keys use existing terminal transport configuration; no new secret is introduced.
The relay rejects terminal commands from scan tickets and scan commands from terminal
tickets. Homepage owner authentication and same-origin checks remain mandatory. Scan
access does not grant terminal step-up. Disconnecting any browser leaves background
scans running; NAS/agent restart marks running checkpoints interrupted for explicit resume.

`NAS_TERMINAL_ENABLED`, `NAS_TERMINAL_RELAY_URL`, `NAS_TERMINAL_TICKET_KEY` remain the
transport configuration. `nas-terminal-relay.yml` now deploys reviewed main pushes that
change Worker/protocol files; its check job runs terminal and scan scope tests first.
No new provider login or key copying is performed.

## Host installation

Run as the NAS `admin` account from a pinned reviewed checkout:

`python3 nas-agent/install_duplicates.py`

The installer requires mounted `/vol1`, the existing Homepage terminal agent and existing
native rclone Drive/Koofr remotes. It inspects rclone configuration in memory, prints no
credentials and chooses one unambiguous remote per provider. If multiple exist, pass
`--drive-remote NAME` / `--koofr-remote NAME`. Missing providers are not invented; the
UI disables them. No new credentials are requested or stored by this installer.

It creates owner-only `~/.config/homepage-duplicates/config.json` with provider allowlist,
absolute rclone binary and HDD state directory `/vol1/homepage-duplicates-<uid>`.
It preserves terminal credentials and the first previous `agent.py.before-duplicates`,
copies the agent/scanner, restarts only `homepage-terminal.service` (tmux shells survive).
No scan is started by installation. `/vol1` is checked before SQLite connections, avoiding
new root-disk state when the HDD is unavailable. Invalid scanner config disables only the
scanner; terminal remains available.

## Scanner behavior

Only fixed `rclone lsjson <allowlisted-remote:scope> --hash` metadata calls, one directory
and one scan at a time; two API transactions/second, bounded retries and ten-minute
per-directory ceiling. No shell or generic remote command. Folder inputs reject remote
selectors, controls and traversal. Names are text, not HTML. Native Google documents
without binary checksums are counted as unhashed. Duplicate key: size + MD5 (preferred),
otherwise SHA256. Files lacking either are excluded from grouping and explicitly counted.
Checksums are scan evidence, not fresh authorization for a later cleanup feature.

Streaming JSON parser and SQLite WAL keep file inventory off browser RAM. A worker-local
connection avoids reopening SQLite per file, with short committed transactions. IDs
distinguish Drive files with identical names/paths; repeated IDs do not inflate copies.
Checkpoint is by directory: interrupted directory is enumerated again, replacing its
partial records. Completed directories are retained. Resume rejects changed remote/root
allowlist; do not change underlying remote accounts during a scan. Failed/incomplete
listings cannot be marked complete. Provider errors are sanitized; no file payload logs.

Drive folders with identical names are currently rejected as ambiguous rather than
silently skipped: traversal by folder ID is a future addition. Metadata paths over 1024
characters and records over 2 MiB fail explicitly. This version does not claim a point-in-
time provider snapshot; a future cleanup must independently revalidate every selection.

Only completed scans expose groups (20/page); member paths are fetched on expansion
(5/page) so large groups don't exceed relay message limits. The UI reports discovered
folders, never a fabricated whole-library percentage. All private results clear on logout.
Optional JSON inventory analysis remains local-only, supports one cloud inventory at a
time and never posts it to the server. Local JSON's cloud label is supplied by the owner.

## Verification and remaining runtime steps

Local checks: JS suite, Python scanner cases (recursive listing, same path/different IDs,
cloud isolation, pause/resume, restart, changed backend, incomplete/ambiguous listings),
terminal regression cases, build, syntax and local links. A synthetic 10,000-file local
fixture completed in 0.84s after worker-connection reuse versus 23.37s before. This is
not a cloud/NAS speed claim. No real provider scan has been run in the authoring environment.

After code/relay publication: install on NAS, confirm cloud roots are available, run a
small explicit folder from each provider, verify status complete and counts, pause/resume
a longer scope, close/reopen the page and verify the same job, then expand scope. Do not
report host/cloud qualification until those observations exist.

Rollback scanner integration: stop the agent service, restore the preserved prior agent
file, then start only that service. Keep SQLite/config for diagnosis; do not delete cloud
files or terminal keys. Full terminal functionality is covered by the existing relay tests.
