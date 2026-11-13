# Retention reconciliation with current evidence

## Decision

The standalone 500-file APPLY result remains the source result and is never
rewritten by reconciliation. Its original `evidence_signatures` field is not
backfilled. The original retention run did not preserve the complete source
stat snapshot required by the historical verification path, so creating that
field later would falsely attribute newly observed facts to the old run.

The explicit `VERIFIED_WITH_CURRENT_EVIDENCE` mode revalidates the archived
result and records a fresh stat snapshot for the four source files at
reconciliation time. It does not claim the files had those metadata values
when retention ran, and it is not a cryptographic signature or proof of the
historical contents of those source files.

## Validation contract

The mode requires all existing aggregate identity, policy, root, candidate,
result hash, timestamp/window, prior-job hash, and lock/backup checks. Supply
`--expected-result-sha256` to pin the explicitly requested result file; the
reconciler rejects a missing, malformed, or mismatched pin. Candidate discovery
in this mode also validates each broad-identity candidate's complete row proof
and exact byte total before treating it as competing. A candidate with another
total is not eligible for this requested result; multiple fully qualifying
candidates still fail closed. Historical mode retains its original broad
identity ambiguity behavior. The mode also
requires exactly 500 result rows; each row must be fully applied, have a unique
nonempty remote ID, a nonnegative five-integer stat tuple, a remote size equal
to `stat[2]`, and matching valid lowercase SHA-256 values for local and remote
content. The byte sum must be exactly **3,915,163,894**.

The four required source files are `events/cam1-events.jsonl`,
`events/cam2-events.jsonl`, `events/recovery/cam1-event-logger-recovery.log`,
and `events/recovery/cam2-event-logger-recovery.log` under the expected root.
Each must be an available regular file and yield a stable five-integer
`[device, inode, size, mtime_ns, ctime_ns]` tuple during collection. The
aggregate records the UTC `evidence_collected_at`, method and version, current
tuples, and `historical_evidence_signatures_available: false`. The tuple map
uses the four relative source names under the validated result root, not
absolute host paths. Source paths and row-level data are not published to the
Homepage status feed.

The old historical verification path remains the default. It continues to
require the original result's producer-defined `evidence_signatures` object,
including its established optional recovery-file semantics. There is no
automatic fallback from a failed historical check to current evidence.

## Safe invocation

First inspect the exact runtime paths and identities, then run the script with
all required arguments in its default plan-only mode. Example template:

```sh
python3 scripts/reconcile_retention_aggregate.py \
  --aggregate /verified/runtime/path/latest.json \
  --results-root /verified/runtime/path/results \
  --result-id run-EXPECTED_ID \
  --expected-root /verified/archive/root \
  --expected-aggregate-sha256 EXPECTED_AGGREGATE_SHA256 \
  --expected-result-sha256 EXPECTED_RESULT_SHA256 \
  --current-evidence
```

Review the complete plan, candidate uniqueness, all identities and hashes,
500-file/byte totals, current evidence tuples, and the exact pointer-only write
scope. If and only if separately authorized after review, repeat the exact
command with explicit `--apply`. Apply rechecks the aggregate and source result
hashes under the existing exclusive lock, recollects source stat metadata and
rejects if it changed, preserves the original aggregate backup, then uses a
same-directory atomic replacement. The result file is not modified. Plan mode
is the default and creates neither the lock nor the backup.

## Audit inspection and stop conditions

Inspect the private aggregate's `verification` and `reconciliation` objects,
the target job's result reference/hash/counts/status, and the preserved
`latest.json.before-<result-id>` backup. Compare backup bytes with the
pre-reconciliation aggregate and independently hash the referenced result.
The public status snapshot exposes only the verification label, collection
time, safe result reference, and aggregate counts.

STOP if a required path is missing, not a regular file, or changes while
collected; a stat value is invalid; the row count, IDs, hashes, sizes, or exact
byte sum differ; the candidate is absent or ambiguous; aggregate identity,
policy, root, or time window differs; hashes/pointer change after review; or
the plan proposes any mutation beyond the aggregate pointer and its existing
backup/lock protocol. Do not run retention, replay, publisher, upload, or
other production operations as part of this reconciliation.

Never fabricate, infer, or backfill historical `evidence_signatures`.
