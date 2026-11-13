#!/usr/bin/env python3
"""Explicitly reconcile one verified standalone APPLY into a pending aggregate.

This is an operator-invoked recovery path, not part of the publisher or timer.
It defaults to a read-only plan. ``--apply`` updates only the aggregate pointer
after an expected-SHA check and preserves the previous pointer as a backup.
"""

import argparse
import fcntl
import hashlib
import json
import math
import os
import re
import stat as stat_module
import sys
import tempfile
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


MAX_WINDOW_SECONDS = 24 * 60 * 60
MAX_FILES = 500
MAX_BYTES = 24 * 1024**3
EXPECTED_CURRENT_BYTES = 3_915_163_894
CURRENT_EVIDENCE_METHOD = "current_filesystem_stat_revalidation"
CURRENT_EVIDENCE_VERSION = 1
EVIDENCE_RELATIVE_SOURCES = (
    "events/cam1-events.jsonl",
    "events/cam2-events.jsonl",
    "events/recovery/cam1-event-logger-recovery.log",
    "events/recovery/cam2-event-logger-recovery.log",
)
FUTURE_SKEW_SECONDS = 5 * 60
EXPECTED_REMOTE = "tapo-gdrive:Tapo-Archive"
RUN_ID_RE = re.compile(r"run-[A-Za-z0-9_-]{1,80}\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
LOCAL_ZONE = ZoneInfo("Asia/Ho_Chi_Minh")


class ReconcileError(ValueError):
    """A safe, stable rejection reason that contains no payload data."""


def require(condition, reason):
    if not condition:
        raise ReconcileError(reason)


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_object(path, reason):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ReconcileError(reason) from None
    require(isinstance(value, dict), reason)
    return value


def load_hashed_object(path, reason):
    try:
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ReconcileError(reason) from None
    require(isinstance(value, dict), reason)
    return value, hashlib.sha256(payload).hexdigest()


def timestamp_epoch(value):
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            result = float(value)
        elif isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            require(parsed.tzinfo is not None, "timestamp_timezone_missing")
            result = parsed.timestamp()
        else:
            raise ReconcileError("timestamp_invalid")
    except (ValueError, OverflowError, OSError):
        raise ReconcileError("timestamp_invalid") from None
    require(math.isfinite(result), "timestamp_invalid")
    return result


def timestamp_text(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def resolve_result_path(results_root, result_id):
    require(bool(RUN_ID_RE.fullmatch(result_id)), "result_id_invalid")
    try:
        root = results_root.resolve(strict=True)
        path = (root / result_id / "result.json").resolve(strict=True)
    except FileNotFoundError:
        raise ReconcileError("result_missing") from None
    except OSError:
        raise ReconcileError("result_path_unavailable") from None
    require(path.is_relative_to(root) and path.parent.parent == root, "result_path_outside_root")
    require(path.is_file(), "result_missing")
    return root, path


def _validate_archived_rows(report, current_evidence=False):
    rows = report.get("rows")
    require(isinstance(rows, list) and len(rows) > 0, "result_rows_missing")
    require(len(rows) == MAX_FILES, "result_file_count_mismatch")
    total_bytes = 0
    remote_ids = set()
    for row in rows:
        require(isinstance(row, dict), "result_row_invalid")
        stat = row.get("stat")
        require(isinstance(stat, list) and len(stat) == 5, "result_stat_invalid")
        require(
            all(type(value) is int and value >= 0 for value in stat),
            "result_stat_invalid",
        )
        size = stat[2]
        require(row.get("status") == "DELETED", "result_not_fully_applied")
        remote = row.get("remote")
        remote_hash = remote.get("sha256") if isinstance(remote, dict) else None
        local_hash = row.get("local_sha256")
        require(
            isinstance(remote, dict)
            and isinstance(remote.get("id"), str)
            and bool(remote.get("id"))
            and type(remote.get("size")) is int
            and remote.get("size") == size
            and isinstance(remote_hash, str)
            and bool(SHA256_RE.fullmatch(remote_hash))
            and local_hash == remote_hash,
            "result_remote_proof_invalid",
        )
        if current_evidence:
            require(remote["id"] not in remote_ids, "result_remote_id_duplicate")
            remote_ids.add(remote["id"])
        total_bytes += size
    require(total_bytes <= MAX_BYTES, "result_byte_limit_exceeded")
    if current_evidence:
        require(total_bytes == EXPECTED_CURRENT_BYTES, "result_byte_total_mismatch")
    require(report.get("stopped_for_time_budget") is False, "result_partial_time_budget")
    return len(rows), total_bytes


def _collect_current_evidence(expected_root, collected_at=None):
    """Capture stable current filesystem metadata; this is not historical evidence."""
    signatures = {}
    try:
        root = Path(expected_root)
        require(root.is_absolute(), "current_evidence_root_invalid")
        for relative in EVIDENCE_RELATIVE_SOURCES:
            path = root / relative
            before = path.stat(follow_symlinks=False)
            require(stat_module.S_ISREG(before.st_mode), "current_evidence_source_invalid")
            signature = [before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns]
            require(all(type(value) is int and value >= 0 for value in signature), "current_evidence_stat_invalid")
            after = path.stat(follow_symlinks=False)
            after_signature = [after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns]
            require(signature == after_signature, "current_evidence_changed_during_collection")
            signatures[relative] = signature
    except (OSError, OverflowError):
        raise ReconcileError("current_evidence_source_unavailable") from None
    stamp = timestamp_text(datetime.now(timezone.utc).timestamp() if collected_at is None else collected_at)
    return {"status": "VERIFIED_WITH_CURRENT_EVIDENCE", "method": CURRENT_EVIDENCE_METHOD,
            "version": CURRENT_EVIDENCE_VERSION, "evidence_collected_at": stamp,
            "historical_evidence_signatures_available": False,
            "current_evidence_signatures": signatures}


def _validate_evidence_signatures(report, expected_root):
    """Validate the producer's filesystem-stat snapshot shape, not a crypto signature."""
    signatures = report.get("evidence_signatures")
    require(isinstance(signatures, dict) and bool(signatures), "result_evidence_invalid")
    relative_sources = (
        "events/cam1-events.jsonl",
        "events/cam2-events.jsonl",
        "events/recovery/cam1-event-logger-recovery.log",
        "events/recovery/cam2-event-logger-recovery.log",
    )
    expected_paths = {str(Path(expected_root) / item) for item in relative_sources}
    require(set(signatures) == expected_paths, "result_evidence_invalid")
    optional_paths = {str(Path(expected_root) / item) for item in relative_sources[2:]}
    for path, value in signatures.items():
        if value is None and path in optional_paths:
            continue
        require(
            isinstance(value, list)
            and len(value) == 5
            and all(type(part) is int and part >= 0 for part in value),
            "result_evidence_invalid",
        )


def _candidate_identity(report, expected_root, policy, start, end):
    if not isinstance(report, dict):
        return False
    if (
        report.get("schema") != 1
        or report.get("mode") != "APPLY"
        or report.get("policy") != policy
        or report.get("root") != expected_root
        or report.get("remote") != EXPECTED_REMOTE
    ):
        return False
    try:
        created = timestamp_epoch(report.get("created"))
    except ReconcileError:
        return False
    return start <= created <= end


def _matching_candidate_ids(results_root, expected_root, policy, start, end):
    matches = []
    try:
        children = list(results_root.iterdir())
    except OSError:
        raise ReconcileError("results_root_unreadable") from None
    for child in children:
        if not child.is_dir() or child.is_symlink() or not RUN_ID_RE.fullmatch(child.name):
            continue
        result_path = child / "result.json"
        if not result_path.is_file() or result_path.is_symlink():
            continue
        try:
            report = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if _candidate_identity(report, expected_root, policy, start, end):
            matches.append(child.name)
    return matches


def _verify_prior_job(job, expected_root, results_root):
    require(isinstance(job, dict) and job.get("status") == "PASS", "prior_job_not_pass")
    result_name, expected_hash = job.get("result"), job.get("result_sha256")
    require(isinstance(result_name, str) and isinstance(expected_hash, str), "prior_job_reference_missing")
    path = Path(result_name).resolve(strict=True)
    require(path.is_relative_to(results_root) and path.name == "result.json", "prior_job_reference_outside_root")
    require(SHA256_RE.fullmatch(expected_hash) and file_sha256(path) == expected_hash, "prior_job_hash_mismatch")
    report = load_object(path, "prior_job_result_invalid")
    require(
        report.get("schema") == 1
        and report.get("mode") == "APPLY"
        and report.get("policy") == job.get("policy")
        and report.get("root") == expected_root
        and report.get("remote") == EXPECTED_REMOTE,
        "prior_job_result_identity_mismatch",
    )
    rows = report.get("rows")
    require(isinstance(rows, list) and all(isinstance(row, dict) and row.get("status") == "DELETED" for row in rows),
            "prior_job_result_partial")


def build_reconciled_aggregate(
    aggregate,
    results_root,
    result_id,
    expected_root,
    expected_aggregate_sha256,
    now=None,
    current_evidence=False,
):
    """Return a new aggregate plus safe evidence metadata; never writes files."""
    require(SHA256_RE.fullmatch(expected_aggregate_sha256 or "") is not None, "expected_aggregate_hash_invalid")
    report, aggregate_hash = load_hashed_object(aggregate, "aggregate_invalid")
    require(aggregate_hash == expected_aggregate_sha256, "aggregate_changed_since_review")
    results_root, result_path = resolve_result_path(results_root, result_id)
    result, result_hash = load_hashed_object(result_path, "result_invalid")

    # A repeat of the exact successful reconciliation is a byte-preserving no-op.
    existing_ref = report.get("reconciliation", {}).get("source_result") if isinstance(report.get("reconciliation"), dict) else None
    existing_hash = report.get("reconciliation", {}).get("source_sha256") if isinstance(report.get("reconciliation"), dict) else None
    if (report.get("status") in {"PASS", "VERIFIED_WITH_CURRENT_EVIDENCE"}
            and existing_ref == f"{result_id}/result.json" and existing_hash == result_hash):
        return report, {"outcome": "ALREADY_RECONCILED", "result_id": result_id, "result_sha256": result_hash}

    require(report.get("status") == "BLOCKED", "aggregate_not_blocked")
    started = timestamp_epoch(report.get("started"))
    finished = timestamp_epoch(report.get("finished"))
    require(finished >= started, "aggregate_window_invalid")
    require(report.get("date") == datetime.fromtimestamp(started, LOCAL_ZONE).date().isoformat(), "aggregate_date_mismatch")
    window_end = started + MAX_WINDOW_SECONDS
    now = datetime.now(timezone.utc).timestamp() if now is None else float(now)
    created = timestamp_epoch(result.get("created"))
    require(created <= now + FUTURE_SKEW_SECONDS, "result_timestamp_in_future")
    require(started <= created <= window_end, "result_outside_aggregate_window")

    jobs = report.get("jobs")
    require(isinstance(jobs, list) and bool(jobs), "aggregate_jobs_missing")
    pending = [(index, job) for index, job in enumerate(jobs)
               if isinstance(job, dict) and job.get("status") == "AUDITING" and not job.get("result")]
    require(len(pending) == 1, "pending_job_ambiguous")
    target_index, target = pending[0]
    require(target.get("policy") == "ARCHIVED_EVENTS", "pending_job_policy_mismatch")
    for job in jobs:
        if job is target:
            continue
        _verify_prior_job(job, expected_root, results_root)

    require(
        result.get("schema") == 1
        and result.get("mode") == "APPLY"
        and result.get("policy") == target.get("policy")
        and result.get("root") == expected_root
        and result.get("remote") == EXPECTED_REMOTE,
        "result_identity_or_policy_mismatch",
    )
    file_count, byte_count = _validate_archived_rows(result, current_evidence=current_evidence)
    verification = _collect_current_evidence(expected_root, now) if current_evidence else None
    if not current_evidence:
        _validate_evidence_signatures(result, expected_root)
    candidates = _matching_candidate_ids(results_root, expected_root, target["policy"], started, window_end)
    require(candidates == [result_id], "result_candidate_ambiguous_or_mismatched")

    reconciled = deepcopy(report)
    reconciled_target = reconciled["jobs"][target_index]
    reconciled_target.update(
        status="PASS",
        result=str(result_path),
        result_sha256=result_hash,
        deleted_files=file_count,
        deleted_bytes=byte_count,
        reconciled_from="standalone_verified_apply_current_evidence" if current_evidence else "standalone_verified_apply",
    )
    if current_evidence:
        reconciled_target["verification_status"] = verification["status"]
    reconciled["status"] = verification["status"] if current_evidence else "PASS"
    reconciled["finished"] = timestamp_text(created)
    reconciled.pop("error", None)
    reconciled["reconciliation"] = {
        "kind": "standalone_verified_apply_current_evidence" if current_evidence else "standalone_verified_apply",
        "source_result": f"{result_id}/result.json",
        "source_sha256": result_hash,
        "previous_aggregate_sha256": expected_aggregate_sha256,
        "reconciled_at": timestamp_text(now),
    }
    if current_evidence:
        reconciled["verification"] = verification
    summary = {
        "outcome": "READY_TO_ADOPT",
        "result_id": result_id,
        "result_sha256": result_hash,
        "created": timestamp_text(created),
        "file_count": file_count,
        "byte_count": byte_count,
        "aggregate_status": reconciled["status"],
        "job_status": reconciled_target["status"],
    }
    if current_evidence:
        summary["verification"] = verification
    return reconciled, summary


def _atomic_write(path, payload):
    fd, temp_name = tempfile.mkstemp(prefix=".retention-reconcile-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def apply_reconciliation(aggregate, reconciled, expected_sha256, result_id, result_path, expected_result_sha256,
                         expected_current_evidence=None, expected_root=None):
    """Atomically preserve the old latest pointer and replace that pointer only."""
    aggregate = Path(aggregate)
    require(not aggregate.is_symlink() and aggregate.is_file(), "aggregate_path_invalid")
    backup = aggregate.with_name(f"{aggregate.name}.before-{result_id}")
    lock_path = aggregate.with_name(aggregate.name + ".reconcile.lock")
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        require(file_sha256(aggregate) == expected_sha256, "aggregate_changed_since_review")
        require(file_sha256(result_path) == expected_result_sha256, "result_changed_since_review")
        if expected_current_evidence is not None:
            current = _collect_current_evidence(expected_root, datetime.now(timezone.utc).timestamp())
            require(current["current_evidence_signatures"] == expected_current_evidence,
                    "current_evidence_changed_since_review")
        original = aggregate.read_bytes()
        if backup.exists():
            require(not backup.is_symlink() and backup.read_bytes() == original, "backup_conflict")
        else:
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(original)
                stream.flush()
                os.fsync(stream.fileno())
        payload = (json.dumps(reconciled, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        _atomic_write(aggregate, payload)
        fcntl.flock(lock, fcntl.LOCK_UN)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aggregate", type=Path, required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--result-id", required=True)
    parser.add_argument("--expected-root", required=True)
    parser.add_argument("--expected-aggregate-sha256", required=True)
    parser.add_argument("--apply", action="store_true", help="write the reviewed aggregate pointer; default is read-only")
    parser.add_argument("--current-evidence", action="store_true",
                        help="explicitly verify the result using current source-file stat evidence")
    args = parser.parse_args(argv)
    try:
        reconciled, summary = build_reconciled_aggregate(
            args.aggregate,
            args.results_root,
            args.result_id,
            args.expected_root,
            args.expected_aggregate_sha256,
            current_evidence=args.current_evidence,
        )
        if args.apply and summary["outcome"] == "READY_TO_ADOPT":
            result_path = resolve_result_path(args.results_root, args.result_id)[1]
            apply_reconciliation(
                args.aggregate,
                reconciled,
                args.expected_aggregate_sha256,
                args.result_id,
                result_path,
                summary["result_sha256"],
                expected_current_evidence=reconciled.get("verification", {}).get("current_evidence_signatures")
                if args.current_evidence else None,
                expected_root=args.expected_root if args.current_evidence else None,
            )
            summary["outcome"] = "ADOPTED"
        print(json.dumps(summary, sort_keys=True))
        return 0
    except ReconcileError as exc:
        print(json.dumps({"outcome": "REJECTED", "reason": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    except OSError:
        print(json.dumps({"outcome": "REJECTED", "reason": "filesystem_error"}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
