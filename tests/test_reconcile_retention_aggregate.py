import json
import tempfile
import unittest
from pathlib import Path

from scripts.reconcile_retention_aggregate import (
    ReconcileError,
    apply_reconciliation,
    build_reconciled_aggregate,
    file_sha256,
)


ROOT = "/archive"
START = "2026-11-11T20:59:33.523599+07:00"
CREATED = "2026-11-12T06:47:49.100029Z"
NOW = 1794470000.0


def result_row(size=19):
    digest = "a" * 64
    return {
        "status": "DELETED",
        "stat": [1, 2, size, 4, 5],
        "local_sha256": digest,
        "remote": {"id": "opaque-test-id", "size": size, "sha256": digest},
    }


def result_document():
    return {
        "schema": 1,
        "mode": "APPLY",
        "policy": "ARCHIVED_EVENTS",
        "root": ROOT,
        "remote": "tapo-gdrive:Tapo-Archive",
        "created": CREATED,
        "stopped_for_time_budget": False,
        "evidence_signatures": {"fixture": "synthetic"},
        "rows": [result_row(), result_row(size=23)],
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

    def plan(self):
        digest = file_sha256(self.aggregate)
        return build_reconciled_aggregate(
            self.aggregate, self.results, self.result_id, ROOT, digest, now=NOW
        )

    def test_valid_result_plans_without_writing_and_preserves_history(self):
        before = self.aggregate.read_bytes()
        historical = self.root / "2026-11-11.json"
        historical.write_bytes(b"historical fixture")
        historical_before = historical.read_bytes()
        reconciled, summary = self.plan()
        self.assertEqual(summary["outcome"], "READY_TO_ADOPT")
        self.assertEqual(summary["file_count"], 2)
        self.assertEqual(summary["byte_count"], 42)
        self.assertEqual(reconciled["status"], "PASS")
        self.assertEqual(reconciled["jobs"][1]["status"], "PASS")
        self.assertEqual(reconciled["finished"], "2026-11-12T06:47:49.100029Z")
        self.assertEqual(self.aggregate.read_bytes(), before)
        self.assertEqual(historical.read_bytes(), historical_before)

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

    def test_candidate_ambiguity_is_rejected(self):
        other = self.results / "run-another" / "result.json"
        other.parent.mkdir()
        other.write_text(json.dumps(result_document()), encoding="utf-8")
        with self.assertRaisesRegex(ReconcileError, "result_candidate_ambiguous_or_mismatched"):
            self.plan()

    def test_apply_updates_only_pointer_and_keeps_backup(self):
        reconciled, summary = self.plan()
        expected = file_sha256(self.aggregate)
        before = self.aggregate.read_bytes()
        apply_reconciliation(self.aggregate, reconciled, expected, self.result_id, self.result_path,
                             summary["result_sha256"])
        self.assertEqual(self.aggregate.with_name("latest.json.before-run-fixture").read_bytes(), before)
        self.assertEqual(json.loads(self.aggregate.read_text())["status"], "PASS")
        self.assertTrue(self.aggregate.with_name("latest.json.reconcile.lock").exists())

    def test_apply_rejects_result_changed_after_plan(self):
        reconciled, summary = self.plan()
        expected = file_sha256(self.aggregate)
        self.result_path.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ReconcileError, "result_changed_since_review"):
            apply_reconciliation(self.aggregate, reconciled, expected, self.result_id, self.result_path,
                                 summary["result_sha256"])


if __name__ == "__main__":
    unittest.main()
