import json
import hashlib
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts.reconcile_retention_aggregate import (
    ReconcileError,
    apply_reconciliation,
    build_reconciled_aggregate,
    file_sha256,
    main,
)


ROOT = "/archive"
START = "2026-11-11T20:59:33.523599+07:00"
CREATED = "2026-11-12T06:47:49.100029Z"
NOW = 1794470000.0


def result_row(index, size):
    digest = hashlib.sha256(f"synthetic-row-{index}".encode()).hexdigest()
    return {
        "status": "DELETED",
        "stat": [1, 2, size, 4, 5],
        "local_sha256": digest,
        "remote": {"id": f"opaque-test-id-{index}", "size": size, "sha256": digest},
    }


def result_signatures():
    return {
        f"{ROOT}/events/cam1-events.jsonl": [1, 11, 100, 1_700_000_000_000_000_000, 1_700_000_000_000_000_001],
        f"{ROOT}/events/cam2-events.jsonl": [1, 12, 200, 1_700_000_000_000_000_000, 1_700_000_000_000_000_001],
        f"{ROOT}/events/recovery/cam1-event-logger-recovery.log": None,
        f"{ROOT}/events/recovery/cam2-event-logger-recovery.log": [1, 14, 50, 1_700_000_000_000_000_000, 1_700_000_000_000_000_001],
    }


def result_document(count=500):
    sizes = [7_830_327 + (index < 394) for index in range(count)]
    return {
        "schema": 1,
        "mode": "APPLY",
        "policy": "ARCHIVED_EVENTS",
        "root": ROOT,
        "remote": "tapo-gdrive:Tapo-Archive",
        "created": CREATED,
        "stopped_for_time_budget": False,
        "evidence_signatures": result_signatures(),
        "rows": [result_row(index, size) for index, size in enumerate(sizes)],
    }


def aggregate_document(prior_result_path, prior_hash):
    return {
        "date": "2026-11-11",
        "started": START,
        "finished": "2026-11-12T00:12:37.645896+07:00",
        "status": "BLOCKED",
        "jobs": [
            {"number": 1, "policy": "OTHER", "status": "PASS", "result": str(prior_result_path), "result_sha256": prior_hash},
            {"number": 2, "policy": "ARCHIVED_EVENTS", "status": "AUDITING"},
        ],
    }


class ReconcileRetentionAggregateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.results = self.root / "results"
        self.results.mkdir()
        self.result_id = "run-fixture"
        result_path = self.results / self.result_id / "result.json"
        result_path.parent.mkdir()
        result_path.write_text(json.dumps(result_document()), encoding="utf-8")
        self.result_path = result_path

        prior = self.results / "run-prior" / "result.json"
        prior.parent.mkdir()
        prior.write_text(json.dumps({
            "schema": 1, "mode": "APPLY", "policy": "OTHER", "root": ROOT,
            "remote": "tapo-gdrive:Tapo-Archive", "rows": [{"status": "DELETED"}],
        }), encoding="utf-8")
        self.prior_path = prior
        self.prior_hash = file_sha256(prior)
        self.aggregate = self.root / "latest.json"
        self.write_aggregate(aggregate_document(prior, self.prior_hash))

    def tearDown(self):
        self.temp.cleanup()

    def write_aggregate(self, document):
        self.aggregate.write_text(json.dumps(document), encoding="utf-8")

    def plan(self, current_evidence=False, expected_result_sha256=None):
        digest = file_sha256(self.aggregate)
        if current_evidence and expected_result_sha256 is None:
            expected_result_sha256 = file_sha256(self.result_path)
        return build_reconciled_aggregate(
            self.aggregate, self.results, self.result_id, str(self.root) if current_evidence else ROOT,
            digest, now=NOW, current_evidence=current_evidence,
            expected_result_sha256=expected_result_sha256,
        )

    def prepare_current_result(self):
        result = result_document()
        result["root"] = str(self.root)
        result["evidence_signatures"] = None
        self.result_path.write_text(json.dumps(result), encoding="utf-8")
        prior = json.loads(self.prior_path.read_text(encoding="utf-8"))
        prior["root"] = str(self.root)
        self.prior_path.write_text(json.dumps(prior), encoding="utf-8")
        self.prior_hash = file_sha256(self.prior_path)
        self.write_aggregate(aggregate_document(self.prior_path, self.prior_hash))
        for relative in (
            "events/cam1-events.jsonl", "events/cam2-events.jsonl",
            "events/recovery/cam1-event-logger-recovery.log",
            "events/recovery/cam2-event-logger-recovery.log",
        ):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic current evidence\n", encoding="utf-8")

    def test_valid_result_plans_without_writing_and_preserves_history(self):
        before = self.aggregate.read_bytes()
        result_before = self.result_path.read_bytes()
        historical = self.root / "2026-11-11.json"
        historical.write_bytes(b"historical fixture")
        historical_before = historical.read_bytes()
        reconciled, summary = self.plan()
        self.assertEqual(summary["outcome"], "READY_TO_ADOPT")
        self.assertEqual(summary["file_count"], 500)
        self.assertEqual(summary["byte_count"], 3915163894)
        self.assertEqual(reconciled["status"], "PASS")
        self.assertEqual(reconciled["jobs"][1]["status"], "PASS")
        self.assertEqual(reconciled["finished"], "2026-11-12T06:47:49.100029Z")
        self.assertEqual(self.aggregate.read_bytes(), before)
        self.assertEqual(self.result_path.read_bytes(), result_before)
        self.assertEqual(historical.read_bytes(), historical_before)

    def test_valid_500_rows_use_current_evidence_without_changing_result(self):
        self.prepare_current_result()
        before = self.result_path.read_bytes()
        reconciled, summary = self.plan(current_evidence=True)
        self.assertEqual(summary["outcome"], "READY_TO_ADOPT")
        self.assertEqual(summary["file_count"], 500)
        self.assertEqual(summary["byte_count"], 3_915_163_894)
        self.assertEqual(reconciled["status"], "VERIFIED_WITH_CURRENT_EVIDENCE")
        self.assertEqual(reconciled["verification"]["status"], "VERIFIED_WITH_CURRENT_EVIDENCE")
        self.assertFalse(reconciled["verification"]["historical_evidence_signatures_available"])
        self.assertEqual(reconciled["verification"]["method"], "current_filesystem_stat_revalidation")
        self.assertEqual(len(reconciled["verification"]["current_evidence_signatures"]), 4)
        self.assertEqual(summary["verification"], reconciled["verification"])
        self.assertEqual(summary["aggregate_status"], "VERIFIED_WITH_CURRENT_EVIDENCE")
        self.assertEqual(set(summary["verification"]["current_evidence_signatures"]), {
            "events/cam1-events.jsonl", "events/cam2-events.jsonl",
            "events/recovery/cam1-event-logger-recovery.log",
            "events/recovery/cam2-event-logger-recovery.log",
        })
        self.assertEqual(self.result_path.read_bytes(), before)
        self.assertIsNone(json.loads(before)["evidence_signatures"])

    def test_current_evidence_rejects_wrong_total_and_duplicate_remote_ids(self):
        self.prepare_current_result()
        result = json.loads(self.result_path.read_text())
        result["rows"][0]["stat"][2] += 1
        result["rows"][0]["remote"]["size"] += 1
        self.result_path.write_text(json.dumps(result))
        with self.assertRaisesRegex(ReconcileError, "result_byte_total_mismatch"):
            self.plan(current_evidence=True)
        result = result_document()
        result["root"] = str(self.root)
        result["evidence_signatures"] = None
        result["rows"][1]["remote"]["id"] = result["rows"][0]["remote"]["id"]
        self.result_path.write_text(json.dumps(result))
        with self.assertRaisesRegex(ReconcileError, "result_remote_id_duplicate"):
            self.plan(current_evidence=True)

    def test_current_evidence_rejects_row_count_and_remote_proof_errors(self):
        self.prepare_current_result()
        result = result_document(499)
        result["root"] = str(self.root)
        result["evidence_signatures"] = None
        self.result_path.write_text(json.dumps(result))
        with self.assertRaisesRegex(ReconcileError, "result_file_count_mismatch"):
            self.plan(current_evidence=True)
        for field, bad_value in (("sha256", "x" * 64), ("size", -1)):
            result = result_document()
            result["root"] = str(self.root)
            result["evidence_signatures"] = None
            result["rows"][0]["remote"][field] = bad_value
            self.result_path.write_text(json.dumps(result))
            with self.subTest(field=field), self.assertRaisesRegex(ReconcileError, "result_remote_proof_invalid"):
                self.plan(current_evidence=True)

    def test_current_evidence_rejects_missing_source_or_invalid_stat_tuple(self):
        self.prepare_current_result()
        missing = self.root / "events/cam2-events.jsonl"
        missing.unlink()
        with self.assertRaisesRegex(ReconcileError, "current_evidence_source_unavailable"):
            self.plan(current_evidence=True)
        missing.write_text("restored fixture\n")
        result = json.loads(self.result_path.read_text())
        result["rows"][0]["stat"][4] = True
        self.result_path.write_text(json.dumps(result))
        with self.assertRaisesRegex(ReconcileError, "result_stat_invalid"):
            self.plan(current_evidence=True)

    def test_current_evidence_requires_requested_result_and_pinned_sha256(self):
        self.prepare_current_result()
        with self.assertRaisesRegex(ReconcileError, "result_missing"):
            build_reconciled_aggregate(
                self.aggregate, self.results, "run-not-requested", str(self.root),
                file_sha256(self.aggregate), now=NOW, current_evidence=True,
                expected_result_sha256=file_sha256(self.result_path),
            )
        with self.assertRaisesRegex(ReconcileError, "result_hash_mismatch"):
            self.plan(current_evidence=True, expected_result_sha256="0" * 64)

    def test_current_evidence_cli_requires_expected_result_sha256(self):
        self.prepare_current_result()
        args = ["--aggregate", str(self.aggregate), "--results-root", str(self.results),
                "--result-id", self.result_id, "--expected-root", str(self.root),
                "--expected-aggregate-sha256", file_sha256(self.aggregate), "--current-evidence"]
        stderr = StringIO()
        with redirect_stderr(stderr):
            code = main(args)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stderr.getvalue())["reason"], "expected_result_sha256_missing")

    def test_historical_mode_remains_default_and_requires_historical_signatures(self):
        result = result_document()
        result["evidence_signatures"] = None
        self.result_path.write_text(json.dumps(result), encoding="utf-8")
        with self.assertRaisesRegex(ReconcileError, "result_evidence_invalid"):
            self.plan()

    def test_cli_default_is_plan_only_and_apply_requires_explicit_flag(self):
        before = self.aggregate.read_bytes()
        out = StringIO()
        with redirect_stdout(out):
            result = main(["--aggregate", str(self.aggregate), "--results-root", str(self.results),
                           "--result-id", self.result_id, "--expected-root", ROOT,
                           "--expected-aggregate-sha256", file_sha256(self.aggregate)])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(out.getvalue())["outcome"], "READY_TO_ADOPT")
        self.assertEqual(self.aggregate.read_bytes(), before)
        self.assertFalse(self.aggregate.with_name("latest.json.before-run-fixture").exists())
        self.assertFalse(self.aggregate.with_name("latest.json.reconcile.lock").exists())

    def test_current_evidence_plan_only_does_not_write_any_files(self):
        self.prepare_current_result()
        source_paths = [self.root / item for item in (
            "events/cam1-events.jsonl", "events/cam2-events.jsonl",
            "events/recovery/cam1-event-logger-recovery.log",
            "events/recovery/cam2-event-logger-recovery.log",
        )]
        before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in source_paths}
        aggregate_before = self.aggregate.read_bytes()
        result_before = self.result_path.read_bytes()
        out = StringIO()
        with redirect_stdout(out):
            code = main(["--aggregate", str(self.aggregate), "--results-root", str(self.results),
                         "--result-id", self.result_id, "--expected-root", str(self.root),
                         "--expected-aggregate-sha256", file_sha256(self.aggregate),
                         "--expected-result-sha256", file_sha256(self.result_path), "--current-evidence"])
        summary = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(summary["outcome"], "READY_TO_ADOPT")
        self.assertEqual(summary["verification"]["status"], "VERIFIED_WITH_CURRENT_EVIDENCE")
        self.assertEqual(set(summary["verification"]["current_evidence_signatures"]), {
            "events/cam1-events.jsonl", "events/cam2-events.jsonl",
            "events/recovery/cam1-event-logger-recovery.log",
            "events/recovery/cam2-event-logger-recovery.log",
        })
        self.assertEqual(self.aggregate.read_bytes(), aggregate_before)
        self.assertEqual(self.result_path.read_bytes(), result_before)
        self.assertEqual({path: (path.read_bytes(), path.stat().st_mtime_ns) for path in source_paths}, before)
        self.assertFalse(self.aggregate.with_name("latest.json.before-run-fixture").exists())
        self.assertFalse(self.aggregate.with_name("latest.json.reconcile.lock").exists())
        self.assertFalse(list(self.aggregate.parent.glob(".retention-reconcile-*")))

    def test_both_optional_recovery_signatures_may_be_absent(self):
        result = result_document()
        signatures = result_signatures()
        signatures[f"{ROOT}/events/recovery/cam2-event-logger-recovery.log"] = None
        result["evidence_signatures"] = signatures
        self.result_path.write_text(json.dumps(result), encoding="utf-8")

        reconciled, summary = self.plan()
        self.assertEqual(summary["outcome"], "READY_TO_ADOPT")
        self.assertEqual(summary["file_count"], 500)
        self.assertEqual(reconciled["jobs"][1]["status"], "PASS")

    def test_exact_repeat_is_noop(self):
        reconciled, summary = self.plan()
        self.write_aggregate(reconciled)
        before = self.aggregate.read_bytes()
        reconciled_again, summary = self.plan()
        self.assertEqual(summary["outcome"], "ALREADY_RECONCILED")
        self.assertEqual(self.aggregate.read_bytes(), before)
        self.assertEqual(reconciled_again, reconciled)

    def test_expected_sha_prevents_stale_plan(self):
        stale_hash = file_sha256(self.aggregate)
        self.write_aggregate({"changed": True})
        with self.assertRaisesRegex(ReconcileError, "aggregate_changed_since_review"):
            build_reconciled_aggregate(self.aggregate, self.results, self.result_id, ROOT, stale_hash, now=NOW)

    def test_partial_or_remote_mismatched_result_is_rejected(self):
        result = result_document()
        result["rows"][1]["status"] = "FAILED"
        self.result_path.write_text(json.dumps(result), encoding="utf-8")
        with self.assertRaisesRegex(ReconcileError, "result_not_fully_applied"):
            self.plan()

    def test_499_and_501_rows_are_rejected(self):
        for count in (499, 501):
            with self.subTest(count=count):
                self.result_path.write_text(json.dumps(result_document(count)), encoding="utf-8")
                with self.assertRaisesRegex(ReconcileError, "result_file_count_mismatch"):
                    self.plan()

    def test_every_stat_value_must_be_a_nonnegative_exact_int(self):
        invalid_values = (True, False, -1, "1", 1.0)
        for position in range(5):
            for value in invalid_values:
                with self.subTest(position=position, value=value):
                    result = result_document()
                    result["rows"][0]["stat"][position] = value
                    self.result_path.write_text(json.dumps(result), encoding="utf-8")
                    with self.assertRaisesRegex(ReconcileError, "result_stat_invalid"):
                        self.plan()

    def test_mismatched_remote_size_or_hash_is_rejected(self):
        original = result_document()
        for field in ("size", "sha256"):
            result = json.loads(json.dumps(original))
            row = result["rows"][0]
            row["remote"][field] = row["remote"][field] + 1 if field == "size" else "0" * 64
            self.result_path.write_text(json.dumps(result), encoding="utf-8")
            with self.subTest(field=field), self.assertRaisesRegex(ReconcileError, "result_remote_proof_invalid"):
                self.plan()

    def test_empty_or_malformed_evidence_signatures_are_rejected(self):
        original = result_document()
        invalid_signatures = [
            {},
            {key: value for key, value in result_signatures().items()
             if not key.endswith("cam2-events.jsonl")},
            {**result_signatures(), f"{ROOT}/events/unexpected.jsonl": [1, 2, 3, 4, 5]},
            {**result_signatures(), f"{ROOT}/events/cam1-events.jsonl": [1, 2, True, 4, 5]},
            {**result_signatures(), f"{ROOT}/events/cam1-events.jsonl": [1, 2, 3]},
            {**result_signatures(), f"{ROOT}/events/recovery/cam1-event-logger-recovery.log": "missing"},
        ]
        for signatures in invalid_signatures:
            with self.subTest(signatures=signatures):
                result = json.loads(json.dumps(original))
                result["evidence_signatures"] = signatures
                self.result_path.write_text(json.dumps(result), encoding="utf-8")
                with self.assertRaisesRegex(ReconcileError, "result_evidence_invalid"):
                    self.plan()

    def test_stale_result_is_rejected(self):
        result = result_document()
        result["created"] = "2026-11-10T06:47:49Z"
        self.result_path.write_text(json.dumps(result), encoding="utf-8")
        with self.assertRaisesRegex(ReconcileError, "result_outside_aggregate_window"):
            self.plan()

    def test_missing_result_is_rejected(self):
        self.result_path.unlink()
        with self.assertRaisesRegex(ReconcileError, "result_missing"):
            self.plan()

    def test_failed_or_dry_run_result_is_rejected(self):
        result = result_document()
        result["mode"] = "DRY_RUN"
        self.result_path.write_text(json.dumps(result), encoding="utf-8")
        with self.assertRaisesRegex(ReconcileError, "result_identity_or_policy_mismatch"):
            self.plan()

    def test_candidate_ambiguity_is_rejected(self):
        other = self.results / "run-another" / "result.json"
        other.parent.mkdir()
        other.write_text(json.dumps(result_document()), encoding="utf-8")
        with self.assertRaisesRegex(ReconcileError, "result_candidate_ambiguous_or_mismatched"):
            self.plan()

    def test_current_evidence_excludes_competing_result_with_different_total(self):
        self.prepare_current_result()
        other = result_document()
        other["root"] = str(self.root)
        other["evidence_signatures"] = None
        other_sizes = [6_148_248 if index < 61 else 6_148_247 for index in range(500)]
        for index, (row, size) in enumerate(zip(other["rows"], other_sizes)):
            row["remote"]["id"] = f"other-run-id-{index}"
            row["stat"][2] = size
            row["remote"]["size"] = size
        self.assertEqual(sum(other_sizes), 3_074_123_561)
        candidate = self.results / "run-different-total" / "result.json"
        candidate.parent.mkdir()
        candidate.write_text(json.dumps(other), encoding="utf-8")

        reconciled, summary = self.plan(current_evidence=True)

        self.assertEqual(summary["outcome"], "READY_TO_ADOPT")
        self.assertEqual(summary["result_id"], self.result_id)
        self.assertEqual(summary["byte_count"], 3_915_163_894)
        self.assertEqual(reconciled["status"], "VERIFIED_WITH_CURRENT_EVIDENCE")

    def test_current_evidence_rejects_fully_qualifying_duplicate_candidate(self):
        self.prepare_current_result()
        other = result_document()
        other["root"] = str(self.root)
        other["evidence_signatures"] = None
        candidate = self.results / "run-duplicate" / "result.json"
        candidate.parent.mkdir()
        candidate.write_text(json.dumps(other), encoding="utf-8")

        with self.assertRaisesRegex(ReconcileError, "result_candidate_ambiguous_or_mismatched"):
            self.plan(current_evidence=True)

    def test_apply_updates_only_pointer_and_keeps_backup(self):
        reconciled, summary = self.plan()
        expected = file_sha256(self.aggregate)
        before = self.aggregate.read_bytes()
        apply_reconciliation(self.aggregate, reconciled, expected, self.result_id, self.result_path,
                             summary["result_sha256"])
        self.assertEqual(self.aggregate.with_name("latest.json.before-run-fixture").read_bytes(), before)
        self.assertEqual(json.loads(self.aggregate.read_text())["status"], "PASS")
        self.assertTrue(self.aggregate.with_name("latest.json.reconcile.lock").exists())
        self.assertFalse(list(self.aggregate.parent.glob(".retention-reconcile-*")))

    def test_apply_rejects_result_changed_after_plan(self):
        reconciled, summary = self.plan()
        expected = file_sha256(self.aggregate)
        aggregate_before = self.aggregate.read_bytes()
        self.result_path.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ReconcileError, "result_changed_since_review"):
            apply_reconciliation(self.aggregate, reconciled, expected, self.result_id, self.result_path,
                                 summary["result_sha256"])
        self.assertEqual(self.aggregate.read_bytes(), aggregate_before)
        self.assertFalse(self.aggregate.with_name("latest.json.before-run-fixture").exists())

    def test_apply_rejects_aggregate_changed_after_plan(self):
        reconciled, summary = self.plan()
        expected = file_sha256(self.aggregate)
        self.aggregate.write_text('{"changed":true}', encoding="utf-8")
        changed = self.aggregate.read_bytes()
        with self.assertRaisesRegex(ReconcileError, "aggregate_changed_since_review"):
            apply_reconciliation(self.aggregate, reconciled, expected, self.result_id, self.result_path,
                                 summary["result_sha256"])
        self.assertEqual(self.aggregate.read_bytes(), changed)
        self.assertFalse(self.aggregate.with_name("latest.json.before-run-fixture").exists())

    def test_current_apply_rejects_recovery_stat_change_after_plan(self):
        self.prepare_current_result()
        reconciled, summary = self.plan(current_evidence=True)
        expected_aggregate = file_sha256(self.aggregate)
        aggregate_before = self.aggregate.read_bytes()
        result_before = self.result_path.read_bytes()
        recovery_log = self.root / "events/recovery/cam1-event-logger-recovery.log"
        recovery_log.write_text("changed after the plan\n", encoding="utf-8")
        with self.assertRaisesRegex(ReconcileError, "current_evidence_changed_since_review"):
            apply_reconciliation(
                self.aggregate, reconciled, expected_aggregate, self.result_id, self.result_path,
                summary["result_sha256"],
                expected_current_evidence=reconciled["verification"]["current_evidence_signatures"],
                expected_root=str(self.root),
            )
        self.assertEqual(self.aggregate.read_bytes(), aggregate_before)
        self.assertEqual(self.result_path.read_bytes(), result_before)
        self.assertFalse(self.aggregate.with_name("latest.json.before-run-fixture").exists())
        self.assertTrue(self.aggregate.with_name("latest.json.reconcile.lock").exists())
        self.assertFalse(list(self.aggregate.parent.glob(".retention-reconcile-*")))

    def test_atomic_replace_failure_keeps_pointer_unchanged_and_cleans_temp(self):
        reconciled, summary = self.plan()
        expected = file_sha256(self.aggregate)
        before = self.aggregate.read_bytes()
        with patch("scripts.reconcile_retention_aggregate.os.replace", side_effect=OSError("injected replace failure")):
            with self.assertRaisesRegex(OSError, "injected replace failure"):
                apply_reconciliation(self.aggregate, reconciled, expected, self.result_id, self.result_path,
                                     summary["result_sha256"])
        self.assertEqual(self.aggregate.read_bytes(), before)
        self.assertEqual(self.aggregate.with_name("latest.json.before-run-fixture").read_bytes(), before)
        self.assertTrue(self.aggregate.with_name("latest.json.reconcile.lock").exists())
        self.assertFalse(list(self.aggregate.parent.glob(".retention-reconcile-*")))

    def test_current_apply_requires_explicit_mode_and_keeps_result_and_backup(self):
        self.prepare_current_result()
        result_before = self.result_path.read_bytes()
        aggregate_before = self.aggregate.read_bytes()
        expected = file_sha256(self.aggregate)
        out = StringIO()
        with redirect_stdout(out):
            code = main(["--aggregate", str(self.aggregate), "--results-root", str(self.results),
                         "--result-id", self.result_id, "--expected-root", str(self.root),
                         "--expected-aggregate-sha256", expected,
                         "--expected-result-sha256", file_sha256(self.result_path),
                         "--current-evidence", "--apply"])
        self.assertEqual(code, 0)
        adopted = json.loads(self.aggregate.read_text())
        self.assertEqual(adopted["status"], "VERIFIED_WITH_CURRENT_EVIDENCE")
        backup = self.aggregate.with_name("latest.json.before-run-fixture")
        self.assertEqual(backup.read_bytes(), aggregate_before)
        self.assertTrue(self.aggregate.with_name("latest.json.reconcile.lock").exists())
        self.assertEqual(self.result_path.read_bytes(), result_before)


if __name__ == "__main__":
    unittest.main()
