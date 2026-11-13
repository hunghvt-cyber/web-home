import json
import hashlib
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.publish_status import make_snapshot, read_maintenance, read_verified_retention


LOCAL = timezone(timedelta(hours=7))
NOW = datetime(2026, 10, 9, 12, 0, tzinfo=LOCAL).timestamp()


def write_retention(path, day, results_root, status="PASS", job_status="PASS", mode="APPLY"):
    results_root.mkdir(parents=True, exist_ok=True)
    jobs = []
    for number in range(1, 2):
        policy = "TEST_POLICY"
        result_path = results_root / f"run-fixture-{number}" / "result.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_bytes = json.dumps({
            "schema": 1, "mode": mode, "policy": policy, "root": "/archive",
            "evidence_signatures": {
                "/archive/events/cam1-events.jsonl": [1, 2, 3, 4, 5],
                "/archive/events/cam2-events.jsonl": [1, 2, 3, 4, 5],
                "/archive/events/recovery/cam1-event-logger-recovery.log": None,
                "/archive/events/recovery/cam2-event-logger-recovery.log": [1, 2, 3, 4, 5],
            },
        }).encode()
        result_path.write_bytes(result_bytes)
        jobs.append({
            "status": job_status,
            "policy": policy,
            "result": str(result_path),
            "result_sha256": hashlib.sha256(result_bytes).hexdigest(),
            "deleted_files": 500,
            "deleted_bytes": 3915163894,
        })
    path.write_text(json.dumps({
        "date": day,
        "started": f"{day}T04:19:08+07:00",
        "finished": f"{day}T05:26:41+07:00",
        "status": status,
        "jobs": jobs,
    }), encoding="utf-8")


def write_cache(path, updated_at, camera_at):
    path.write_text(json.dumps({
        "updated_at": updated_at,
        "host": {
            "filesystems": [
                {"path": "/", "status": "ok", "total_bytes": 100, "available_bytes": 20},
                {"path": "/vol1", "status": "ok", "total_bytes": 200, "available_bytes": 40},
            ],
            "memory": {"status": "ok", "total_bytes": 800, "available_bytes": 300,
                       "swap_total_bytes": 1000, "swap_used_bytes": 250},
        },
        "tapo": {"cameras": {
            name: {
                "updated_at": updated_at,
                "last_video_at": camera_at,
                "status": "recording",
                "recorder_active": True,
                "sample_growth": True,
            } for name in ("cam1", "cam2")
        }},
    }), encoding="utf-8")


class StatusSnapshotTests(unittest.TestCase):
    def test_maintenance_and_verified_retention_keep_previous_day_result(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            maintenance = root / "latest.env"
            retention = root / "latest.json"
            maintenance.write_text(
                "LAST_UPDATE=2026-10-08T01:43:17+07:00\nSTATUS=PASS\nRETENTION=DRY_RUN\n",
                encoding="utf-8",
            )
            results_root = root / "verified"
            write_retention(retention, "2026-10-08", results_root)
            self.assertEqual(read_maintenance(maintenance)["maintenance"]["state"], "pass")
            result = read_verified_retention(retention, results_root)["retention"]
            self.assertEqual(result["state"], "pass")
            self.assertEqual(result["measured_at"], "2026-10-07T22:26:41Z")
            self.assertEqual(result["result_ref"], "run-fixture-1")
            self.assertEqual(result["file_count"], 500)
            self.assertEqual(result["byte_count"], 3915163894)
            self.assertEqual(result["verification_status"], "HISTORICALLY_VERIFIED")

    def test_current_day_verified_retention_pass_is_used(self):
        with tempfile.TemporaryDirectory() as temp:
            retention = Path(temp) / "latest.json"
            results_root = Path(temp) / "verified"
            write_retention(retention, "2026-10-09", results_root)
            result = read_verified_retention(retention, results_root)["retention"]
            self.assertEqual(result["state"], "pass")
            self.assertEqual(result["measured_at"], "2026-10-08T22:26:41Z")

    def test_current_evidence_is_published_distinctly_without_local_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            retention = root / "latest.json"
            results_root = root / "verified"
            write_retention(retention, "2026-10-09", results_root)
            aggregate = json.loads(retention.read_text())
            aggregate["status"] = "VERIFIED_WITH_CURRENT_EVIDENCE"
            result_path = results_root / "run-fixture-1" / "result.json"
            result = json.loads(result_path.read_text())
            result["root"] = str(root)
            result["evidence_signatures"] = None
            result_path.write_text(json.dumps(result))
            payload = result_path.read_bytes()
            aggregate["jobs"][0].update({
                "result_sha256": hashlib.sha256(payload).hexdigest(),
                "verification_status": "VERIFIED_WITH_CURRENT_EVIDENCE",
            })
            expected = [path for path in (
                "events/cam1-events.jsonl", "events/cam2-events.jsonl",
                "events/recovery/cam1-event-logger-recovery.log",
                "events/recovery/cam2-event-logger-recovery.log",
            )]
            aggregate["verification"] = {
                "status": "VERIFIED_WITH_CURRENT_EVIDENCE",
                "method": "current_filesystem_stat_revalidation", "version": 1,
                "evidence_collected_at": "2026-10-08T22:26:41.123456Z",
                "historical_evidence_signatures_available": False,
                "current_evidence_signatures": {path: [1, 2, 3, 4, 5] for path in expected},
            }
            aggregate["reconciliation"] = {
                "kind": "standalone_verified_apply_current_evidence",
                "source_result": "run-fixture-1/result.json",
                "source_sha256": hashlib.sha256(payload).hexdigest(),
            }
            retention.write_text(json.dumps(aggregate))
            observed = read_verified_retention(retention, results_root)["retention"]
            self.assertEqual(observed["state"], "pass")
            self.assertEqual(observed["verification_status"], "VERIFIED_WITH_CURRENT_EVIDENCE")
            self.assertEqual(observed["evidence_collected_at"], "2026-10-08T22:26:41.123456Z")
            self.assertFalse(any(path in json.dumps(observed) for path in expected))
            del aggregate["verification"]["evidence_collected_at"]
            retention.write_text(json.dumps(aggregate))
            self.assertEqual(read_verified_retention(retention, results_root)["retention"]["state"], "unknown")

    def test_pass_without_historical_signatures_is_not_labeled_historically_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            retention = root / "latest.json"
            results_root = root / "verified"
            write_retention(retention, "2026-10-09", results_root)
            result_path = results_root / "run-fixture-1" / "result.json"
            result = json.loads(result_path.read_text())
            result.pop("evidence_signatures")
            payload = json.dumps(result).encode()
            result_path.write_bytes(payload)
            aggregate = json.loads(retention.read_text())
            aggregate["jobs"][0]["result_sha256"] = hashlib.sha256(payload).hexdigest()
            retention.write_text(json.dumps(aggregate))
            observed = read_verified_retention(retention, results_root)["retention"]
            self.assertEqual(observed["state"], "pass")
            self.assertNotIn("verification_status", observed)

    def test_dry_run_is_not_verified_retention(self):
        with tempfile.TemporaryDirectory() as temp:
            retention = Path(temp) / "latest.json"
            results_root = Path(temp) / "verified"
            write_retention(retention, "2026-10-09", results_root, status="DRY_RUN", job_status="DRY_RUN", mode="DRY_RUN")
            result = read_verified_retention(retention, results_root)["retention"]
            self.assertEqual(result["state"], "unknown")
            self.assertIsNone(result["measured_at"])

    def test_old_snapshot_keeps_history_but_camera_freshness_is_unknown(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cache, maintenance, retention = root / "cache.json", root / "latest.env", root / "latest.json"
            write_cache(cache, NOW - 3600, NOW - 60)
            maintenance.write_text("LAST_UPDATE=2026-10-08T01:43:17+07:00\nSTATUS=PASS\n", encoding="utf-8")
            results_root = root / "verified"
            write_retention(retention, "2026-10-08", results_root)
            snapshot = make_snapshot(NOW, cache, maintenance, retention, results_root)
            self.assertEqual(snapshot["updated_at"], "2026-10-09T04:00:00Z")
            self.assertEqual(snapshot["cam1"]["state"], "unknown")
            self.assertEqual(snapshot["nas"]["state"], "unknown")
            self.assertEqual(snapshot["health"]["root"], {"used_percent": None, "available_bytes": None})
            self.assertEqual(snapshot["health"]["vol1"], {"used_percent": None, "available_bytes": None})
            self.assertEqual(snapshot["maintenance"]["state"], "pass")
            self.assertEqual(snapshot["retention"]["state"], "pass")

    def test_fresh_recording_evidence_marks_cameras_ok(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cache, maintenance, retention = root / "cache.json", root / "latest.env", root / "latest.json"
            write_cache(cache, NOW - 10, NOW - 30)
            maintenance.write_text("LAST_UPDATE=2026-10-09T01:43:17+07:00\nSTATUS=PASS\n", encoding="utf-8")
            results_root = root / "verified"
            write_retention(retention, "2026-10-09", results_root)
            snapshot = make_snapshot(NOW, cache, maintenance, retention, results_root)
            self.assertEqual(snapshot["cam1"]["state"], "ok")
            self.assertEqual(snapshot["cam2"]["state"], "ok")
            self.assertEqual(snapshot["health"]["root"], {"used_percent": 80.0, "available_bytes": 20})
            self.assertEqual(snapshot["health"]["vol1"], {"used_percent": 80.0, "available_bytes": 40})
            self.assertEqual(snapshot["health"]["ram"]["available_bytes"], 300)
            self.assertEqual(snapshot["health"]["swap"], {"used_bytes": 250, "total_bytes": 1000})

    def test_missing_swap_metrics_are_unknown(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cache = root / "cache.json"
            write_cache(cache, NOW - 10, NOW - 30)
            data = json.loads(cache.read_text())
            data["host"] = {"filesystems": [], "memory": {"status": "unavailable"}}
            cache.write_text(json.dumps(data), encoding="utf-8")
            snapshot = make_snapshot(NOW, cache, root / "missing-maintenance", root / "missing-retention", root / "missing-verified")
            self.assertEqual(snapshot["nas"]["state"], "unknown")
            self.assertEqual(snapshot["health"]["root"], {"used_percent": None, "available_bytes": None})
            self.assertEqual(snapshot["health"]["vol1"], {"used_percent": None, "available_bytes": None})
            self.assertIsNone(snapshot["health"]["ram"]["available_bytes"])
            self.assertEqual(snapshot["health"]["swap"], {"used_bytes": None, "total_bytes": None})

    def test_invalid_swap_values_are_suppressed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cache = root / "cache.json"
            write_cache(cache, NOW - 10, NOW - 30)
            data = json.loads(cache.read_text())
            for invalid in (float("nan"), -1, 1001):
                data["host"]["memory"]["swap_used_bytes"] = invalid
                cache.write_text(json.dumps(data), encoding="utf-8")
                snapshot = make_snapshot(NOW, cache, root / "missing-maintenance", root / "missing-retention", root / "missing-verified")
                self.assertEqual(snapshot["health"]["swap"], {"used_bytes": None, "total_bytes": None})

    def test_nan_negative_and_invalid_filesystems_are_suppressed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cache = root / "cache.json"
            write_cache(cache, NOW - 10, NOW - 30)
            data = json.loads(cache.read_text())
            data["host"]["filesystems"][0]["available_bytes"] = float("nan")
            data["host"]["filesystems"][1]["available_bytes"] = -1
            data["host"]["memory"]["available_bytes"] = float("nan")
            cache.write_text(json.dumps(data), encoding="utf-8")
            snapshot = make_snapshot(NOW, cache, root / "missing-maintenance", root / "missing-retention", root / "missing-verified")
            self.assertEqual(snapshot["nas"]["state"], "unknown")
            self.assertEqual(snapshot["health"]["root"], {"used_percent": None, "available_bytes": None})
            self.assertEqual(snapshot["health"]["vol1"], {"used_percent": None, "available_bytes": None})
            self.assertIsNone(snapshot["health"]["ram"]["available_bytes"])

    def test_filesystem_error_status_suppresses_metrics(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cache = root / "cache.json"
            write_cache(cache, NOW - 10, NOW - 30)
            data = json.loads(cache.read_text())
            data["host"]["filesystems"][1]["status"] = "unavailable"
            cache.write_text(json.dumps(data), encoding="utf-8")
            snapshot = make_snapshot(NOW, cache, root / "missing-maintenance", root / "missing-retention", root / "missing-verified")
            self.assertEqual(snapshot["nas"]["state"], "unknown")
            self.assertEqual(snapshot["health"]["vol1"], {"used_percent": None, "available_bytes": None})

    def test_health_metrics_are_null_when_snapshot_is_stale(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cache = root / "cache.json"
            write_cache(cache, NOW - 16 * 60, NOW - 30)
            snapshot = make_snapshot(NOW, cache, root / "missing-maintenance", root / "missing-retention", root / "missing-verified")
            self.assertEqual(snapshot["nas"]["state"], "unknown")
            self.assertIsNone(snapshot["health"]["root"]["used_percent"])
            self.assertIsNone(snapshot["health"]["ram"]["available_bytes"])
            self.assertEqual(snapshot["health"]["swap"], {"used_bytes": None, "total_bytes": None})

    def test_swap_used_cannot_exceed_total(self):
        from scripts.publish_status import validate
        base = {
            "schema": 1, "updated_at": None, "cam1": {"state": "unknown"},
            "cam2": {"state": "unknown"}, "nas": {"state": "unknown"},
            "maintenance": {"state": "unknown", "measured_at": None},
            "retention": {"state": "unknown", "measured_at": None},
            "health": {
                "root": {"used_percent": None, "available_bytes": None},
                "vol1": {"used_percent": None, "available_bytes": None},
                "ram": {"available_bytes": None}, "swap": {"used_bytes": None, "total_bytes": None},
            },
        }
        import copy
        data = copy.deepcopy(base)
        data["health"]["swap"] = {"used_bytes": 1001, "total_bytes": 1000}
        with self.assertRaises(AssertionError):
            validate(data)

    def test_missing_sources_are_unknown_without_rejecting_partial_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            snapshot = make_snapshot(NOW, root / "missing-cache", root / "missing-maintenance", root / "missing-retention", root / "missing-verified")
            self.assertIsNone(snapshot["updated_at"])
            self.assertEqual(snapshot["nas"]["state"], "unknown")
            self.assertEqual(snapshot["cam1"]["state"], "unknown")
            self.assertEqual(snapshot["maintenance"], {"state": "unknown", "measured_at": None})
            self.assertEqual(snapshot["retention"], {"state": "unknown", "measured_at": None})


if __name__ == "__main__":
    unittest.main()
