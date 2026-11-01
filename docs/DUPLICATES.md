# Dọn file trùng — NAS, 01/11/2026

`/don-file-trung/` opens from a small Homepage shortcut in a new tab. The owner selected
NAS for large inventories. Scanning is read-only. Version 3 adds explicitly selected recoverable cleanup: Drive
Trash or Koofr GoogleBackup-Trash. No permanent delete or retention/sync changes.
Drive and Koofr are independent scan scopes.

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
No new provider login or key copying is performed. Mutation tickets additionally require
a fresh Homepage password and a signed cleanup grant, checked for exact expiry at the relay.

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
copies the agent/scanner/cleanup module (version 3), restarts only `homepage-terminal.service` (tmux shells survive).
Installation enables cleanup in the private scanner config but starts no scan or cleanup. `/vol1` is checked before SQLite connections, avoiding
new root-disk state when the HDD is unavailable. Invalid scanner config disables only the
scanner; terminal remains available.

## Scanner behavior

Only fixed `rclone lsjson <allowlisted-remote:scope> --hash` metadata calls, one directory
and one scan at a time; two API transactions/second, bounded retries and ten-minute
per-directory ceiling. No shell or generic remote command. Folder inputs reject remote
selectors, controls and traversal. Names are text, not HTML. Native Google documents
without binary checksums are counted as unhashed. Duplicate key: size + MD5 (preferred),
otherwise SHA256. Files lacking either are excluded from grouping and explicitly counted.
Checksums are scan evidence; cleanup independently revalidates the target and a retained copy.

Streaming JSON parser and SQLite WAL keep file inventory off browser RAM. A worker-local
connection avoids reopening SQLite per file, with short committed transactions. IDs
distinguish Drive files with identical names/paths; repeated IDs do not inflate copies.
Checkpoint is by directory: interrupted directory is enumerated again, replacing its
partial records. Completed directories are retained. Resume rejects changed remote/root
allowlist; do not change underlying remote accounts during a scan. Failed/incomplete
listings cannot be marked complete. Provider errors are sanitized; no file payload logs.

Folder picker v2 browses read-only metadata, offers parent/root navigation and a
“Quét thư mục này” action; no manual path is needed. NAS-issued opaque location handles
are bound to provider and configured backend. Browser input cannot supply arbitrary
Drive IDs or remotes. Drive traversal uses returned provider folder IDs, including
same-named sibling folders; names remain display-only. Koofr uses provider-relative paths.
Folder lists are capped at 5,000 per directory and paginated at five per response, with
a 15-second listing ceiling and explicit retry on incomplete results. Pagination binds
an immutable local listing generation; a refreshed generation invalidates old pages.

Existing queue checkpoints are migrated additively with display_path/provider_id fields;
a private SQLite snapshot is saved before migrating an existing database. Existing
scans and file records are retained. Legacy queued paths remain readable; new Drive child
nodes are keyed by ID, so resuming one duplicate-name node cannot delete another node's
local inventory. Migration affects local metadata only, never provider files.

Metadata paths over 1024 characters and records over 2 MiB fail explicitly. This version does not claim a point-in-
time provider snapshot; cleanup revalidates every selection, but cannot make an atomic transaction against concurrent edits in external apps.

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


## Recoverable cleanup v3

Owner authorized selected cleanup and Koofr GoogleBackup-Trash fallback. The UI starts
unchecked. Select at most 20 file handles, re-enter Homepage password (15-minute separate
cleanup grant), request a server plan, review the action/count and explicitly confirm.
No cloud write is performed by installation, scanning, planning or tests.

The relay allows prepare/apply only with a signed, unexpired cleanup grant; ordinary scan
and terminal tickets cannot mutate. No raw source, destination, provider ID or permanent-
delete option is accepted from the browser. Plans bind the existing completed scan,
provider configuration and selected identities. Server keeps at least one unselected,
unremoved, non-protected copy in every group, even across separate prepared plans.
Profile/state, guide storage and GoogleBackup-Trash files cannot be selected or used as
the sole retained copy. Foreign/stale handles and changed provider config are rejected.

Drive refreshes its existing rclone OAuth session, reads credentials in local memory only,
then uses fixed-host Drive v2 metadata/trash endpoints on exact IDs. It requires current
name/parent/size/MD5 and an ETag, sends If-Match and verifies trashed=true. It never calls
permanent DELETE and never guesses a file by a duplicate filename. SHA-only files,
shortcuts/non-single IDs or missing version evidence fail closed. Authorization headers
are never logged; redirects are forbidden. Sources:
https://developers.google.com/workspace/drive/api/reference/rest/v2/files
https://developers.google.com/workspace/drive/api/reference/rest/v2/files/trash

Koofr validates the native provider and server-side Move feature, rechecks identity and
size/checksum, then moves within the same remote/mount to
GoogleBackup-Trash/<plan>/<file-handle>/<original-name>. Destination directories must be
empty and --immutable forbids overwriting changed content. Destination checksum and
source absence must verify before reporting done. This preserves the bytes for recovery;
it does not reduce Koofr storage usage. No permanent deletion fallback exists.

SQLite journals each pending/applying/done/uncertain item before and after its mutation.
A failed/ambiguous write is not retried by the tool; after restart running plans are
interrupted and applying items become uncertain. Inspect the cloud or run a new scan to
reconcile. Already-applied plan IDs return status only. Successful items are tombstoned
in that scan's inventory, preventing a later plan from selecting a removed keeper.
The worker is exclusive with scans and checks for agent shutdown before each write.
Snapshot inventory.before-cleanup.sqlite3 is preserved before additive schema migration.

Concurrent cloud edits and external sync jobs remain outside the tool's transaction;
the UI explains possible propagation. No sync engine is changed or paused by this feature.
Rollback requires matching prior agent/scanner modules plus the pre-cleanup database,
not just restoring an older scanner against a newer schema. Keep configs/keys/receipts.

Owner-reported v2 runtime evidence: Drive 9 files/1 folder at 23:48:10 and Koofr 10 files/
4 folders at 23:49:27 on 01/11/2026, all with checksums and no duplicate groups. These
prove basic scan paths only. Cleanup tests use fake providers/HTTP fixtures, including
retain-one, changed keeper, unknown outcomes, plan replay, restart, protected namespaces,
conditional exact-ID Drive trash and Koofr destination conflict handling. No real cloud
file has been removed or moved in the authoring session; v3 host activation and live
cleanup qualification remain pending owner-selected files.

## Reload/resume UI fix — 02/11/2026

Authenticated tool pages now automatically reconnect to the NAS and restore its latest
scan, without starting or resuming a job on page load. Resume rechecks the same scan ID:
running/complete jobs are displayed as-is; paused/interrupted/failed jobs receive an
explicit resume command. Operation errors remain in a separate status field so normal
five-second polling cannot hide them. Action buttons lock while awaiting a reply.

The duplicate Start scan button/form submission is removed; only the folder picker's
“Quét thư mục này” starts a scan. Manual reconnect is available when the NAS socket is
offline. This update changes only web UI; no NAS agent reinstall is needed. Regression
fixtures simulate new tabs with paused/running jobs and a resume error surviving polling.
These checks do not identify every possible host/provider failure without runtime output.

## Unknown metadata size and checkpoint resume — 02/11/2026

Owner reported a failed full-Drive scan at 211 files and 37/69 discovered folders.
The resume command reached the NAS, but the worker stopped again on its size guard.
Unknown sizes (-1, absent or null) now remain size=-1 and have no duplicate key;
they count toward files and unknownSize/unhashed but cannot enter cleanup groups.
They are never normalized to zero. Native Google documents also stay outside groups.
Malformed size types and other negative sizes still stop the scan explicitly.

This requires reinstalling the NAS scanner. Resume retains completed directory
checkpoints and re-enumerates the failed directory. Regression fixtures verify this
without rereading the completed root, and distinguish real zero-byte duplicates from
unknown-size files. UI reports incomplete metadata and replaces stale resume success
when polling observes a failed worker. Actual offending cloud metadata has not been
retrieved; live recovery remains to be verified after owner installs and resumes.

## Drive directory shortcut IDs — 02/11/2026

Owner reported 13,601 files, 192/250 discovered directories before the old ID guard
stopped. That guard conflated absent IDs with valid rclone composite IDs. Host metadata
has not been retrieved, so a shortcut is a covered explanation, not a confirmed host diagnosis.
Rclone defines directory shortcut IDs as target ID + TAB + shortcut ID:
https://github.com/rclone/rclone/blob/master/backend/drive/drive.go (joinID/splitID).

Scanner and picker now validate both components and enumerate the target by exact ID.
Queue identity uses that target, deduplicating aliases and terminating cycles. Truly
absent or malformed IDs still fail the scan; partial groups remain unavailable.
No filename fallback or shortcut skipping is introduced. Descendants discovered through
an alias are scan-only, inherited through the picker and scan queue: server cleanup
rejects them as either selected targets or the only retained keeper. To clean these
files, select and scan the original folder directly. When a real target was already
queued directly, its existing path and permissions remain authoritative.

Additive read_only columns on queue/locations default to false for existing entries;
inventory.before-shortcuts.sqlite3 is created (0600) before migration. Installation
retains keys/configuration and all completed checkpoints and starts no scan or cleanup.
Resume re-enumerates only the unfinished directory. Tests cover composite ID validation,
picker start, recursive inheritance, repeated targets/cycles, migration snapshot,
checkpoint resume, truly missing IDs, and server cleanup refusal. Live continuation
after owner installation remains to be verified.
