# Dọn file trùng — 01/11/2026

Owner requested a small Homepage entry opening a separate tool page. `/don-file-trung/`
opens in a new tab from the existing shortcuts. Plain HTML/JS; no new service or database.

First increment is read-only, as agreed. Choose Google Drive OR Koofr and load one
rclone `lsjson --recursive --files-only --hash` inventory. Each submission replaces
the prior results. Cloud changes clear the file and results; never cross-cloud grouping.
Files are processed in tab memory, not uploaded, cached or stored. No external scripts.
Names/paths render with textContent. The page has no network requests or mutation API.

Identity: ID where present (preserves Drive files sharing the same path), otherwise path.
Duplicate key: size + algorithm + checksum (SHA256 preferred, MD5 otherwise). Missing
hashes, malformed records and repeated identities are excluded and counted. No content
download to synthesize hashes; unsupported files cannot be declared unique. Checksums
are inventory evidence, not fresh pre-deletion verification. Savings assume one copy kept.

Existing `backup-drive/.github/workflows/duplicate-audit.yml` produces separate inventories;
its old Koofr scope is `/GoogleBackup`, not the entire Koofr account. A report's cloud label
is supplied by the owner; raw rclone JSON does not prove cloud identity or complete scope.
The new `scripts/duplicate_inventory.py` is an optional standalone read-only collector,
requires preconfigured rclone, writes private 0600 JSON atomically without overwrite.
Neither collector was run against real cloud data in this change.

Limits: 30 MiB / 200,000 records; 50 groups rendered per page, paths only on expansion.
Direct NAS scanning and selected cleanup are not connected/implemented. The UI explicitly
states this; no simulated data or working deletion claim. Homepage source changes do not
install/change NAS services, sync engines, retention or Google triggers.

Next increment: authenticated async NAS scan transport with explicit provider roots,
freshness/scope proof and private reports. Cleanup additionally needs recheck, retain-one
server enforcement, sync-aware exclusions, recoverable action and audit receipts. Do not
reuse Guides credentials, report keys or Terminal shell access for a generic cloud proxy.
