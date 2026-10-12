"""Pure fixtures and mocked controls only: never run a real CLI/profile."""
import csv
import hashlib
import io
import json
from pathlib import Path
import signal
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

import profile_cli_resources as profile


class FakeMonitor:
    def __init__(self, exit_at=0.15, exit_code=0, rss=1234, affinity=None):
        self.time = 0.0
        self.exit_at = exit_at
        self.exit_code = exit_code
        self.rss = rss
        self.affinity = [2, 3] if affinity is None else affinity
        self.signals = []
        self.reaped = []

    def wait4(self, pid, flags):
        if self.time < self.exit_at:
            return 0, 0, None
        self.reaped.append(pid)
        usage = SimpleNamespace(ru_utime=.13, ru_stime=.02, ru_maxrss=5000,
                                ru_minflt=31, ru_majflt=0, ru_nvcsw=20, ru_nivcsw=2)
        status = self.exit_code * 256 if self.exit_code >= 0 else -self.exit_code
        return pid, status, usage

    def sample(self, pid):
        return {"rssKiB": self.rss, "affinity": self.affinity, "coreclrPaths": []}

    def signal(self, pid, number):
        self.signals.append((pid, number, self.time))

    def sleep(self, interval):
        self.time += interval

    def run(self, *, cancellation=False, timeout=120):
        limits = {"rssLimitMiB": 768, "pollSeconds": .05, "cancelAfterSeconds": 1, "cancelGraceSeconds": 10}
        return profile.monitor_process(4321, 0, limits, timeout, [2, 3], cancellation=cancellation,
                                       wait4=self.wait4, sample=self.sample, send_signal=self.signal,
                                       now=lambda: self.time, sleep=self.sleep)


class ResourceProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = profile.strict_json(profile.PROTOCOL.read_text(encoding="utf-8"))

    def test_frozen_protocol_and_input_hashes(self):
        profile.validate_protocol(self.protocol)
        for item in self.protocol["datasets"]:
            data = profile.generate_dataset(item["entitiesPerGroup"], item["measurementsPerEntity"])
            self.assertEqual(hashlib.sha256(data).hexdigest(), item["sha256"])

    def test_generator_positive_nonconstant_unique_entities_real_sequence(self):
        for item in self.protocol["datasets"]:
            data = profile.generate_dataset(item["entitiesPerGroup"], item["measurementsPerEntity"])
            rows = list(csv.DictReader(io.StringIO(data.decode())))
            self.assertEqual(len(rows), item["rows"])
            entities = {}
            for row in rows:
                self.assertGreater(float(row["value"]), 0)
                self.assertEqual(row["unit"], "synthetic-unit")
                entities.setdefault(row["entity"], []).append(row)
            self.assertEqual(len(entities), item["entitiesTotal"])
            for entity_rows in entities.values():
                self.assertEqual(len({r["group"] for r in entity_rows}), 1)
                self.assertEqual([int(r["sequence"]) for r in entity_rows], list(range(1, item["measurementsPerEntity"] + 1)))
                self.assertGreater(len({r["value"] for r in entity_rows}), 1)

    def test_protocol_rejects_expanded_budget(self):
        for section, key, value in [("limits", "cpus", 3), ("limits", "rssLimitMiB", 1024),
                                    ("calibration", "repetitions", 101), ("cancellation", "repetitions", 100001)]:
            altered = json.loads(json.dumps(self.protocol))
            altered[section][key] = value
            with self.assertRaises(ValueError):
                profile.validate_protocol(altered)

    def test_strict_json_rejects_extra_output_duplicate_and_nonfinite(self):
        for text in ['{} {}', 'progress\n{}', '{"a":1,"a":2}', '{"a":NaN}']:
            with self.assertRaises(ValueError):
                profile.strict_json(text)

    def test_affinity_first_two_and_child_only_setter(self):
        self.assertEqual(profile.select_affinity({7, 3, 9}), [3, 7])
        self.assertEqual(profile.select_affinity({7}), [7])
        with self.assertRaises(RuntimeError):
            profile.select_affinity(set())
        with patch.object(profile.os, "sched_setaffinity") as setter:
            profile.child_affinity([3, 7])
        setter.assert_called_once_with(0, {3, 7})

    def test_optional_runtime_and_backup_overrides_removed_without_values(self):
        env, removed = profile.clean_environment({"MVS_BACKUP_JOB": "private", "MVS_DEBUG": "1", "DOTNET_PROCESSOR_COUNT": "99",
                                                   "COMPlus_gcServer": "1", "KEEP": "yes"}, {"DOTNET_ROOT": "/sdk", "MVS_DISABLE_BACKUPS": "1"})
        self.assertEqual(removed, ["COMPlus_gcServer", "DOTNET_PROCESSOR_COUNT", "MVS_BACKUP_JOB", "MVS_DEBUG"])
        self.assertEqual(env, {"KEEP": "yes", "DOTNET_ROOT": "/sdk", "MVS_DISABLE_BACKUPS": "1"})

    def test_linux_only_clear_failure(self):
        with patch.object(profile.sys, "platform", "darwin"):
            with self.assertRaisesRegex(RuntimeError, "Unsupported platform"):
                profile.require_linux()

    def test_wait4_exact_pid_cpu_and_peak_are_separate_from_samples(self):
        fixture = FakeMonitor()
        result = fixture.run()
        self.assertEqual(fixture.reaped, [4321])
        self.assertEqual(result["peakRssKiB"], 5000)
        self.assertEqual(result["sampledPeakRssKiB"], 1234)
        self.assertAlmostEqual(result["cpuTotalSeconds"], .15)
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(fixture.signals, [])

    def test_cancellation_sends_one_sigint_and_waits_for_exit(self):
        fixture = FakeMonitor(exit_at=1.2, exit_code=1)
        result = fixture.run(cancellation=True)
        self.assertEqual([(pid, sig) for pid, sig, _ in fixture.signals], [(4321, signal.SIGINT)])
        self.assertTrue(result["cancellationSignalSent"])
        self.assertLess(result["cancellationLatencySeconds"], .25)
        self.assertFalse(result["forcedKill"])

    def test_cancellation_early_exit_is_not_a_cancel_pass(self):
        fixture = FakeMonitor(exit_at=.5)
        result = fixture.run(cancellation=True)
        self.assertFalse(result["cancellationSignalSent"])
        self.assertEqual(fixture.signals, [])

    def test_cancel_grace_kills_owned_session_once(self):
        fixture = FakeMonitor(exit_at=11.3, exit_code=-9)
        result = fixture.run(cancellation=True)
        self.assertEqual([s for _, s, _ in fixture.signals], [signal.SIGINT, signal.SIGKILL])
        self.assertTrue(all(pid == 4321 for pid, _, _ in fixture.signals))
        self.assertIn("cancellation_grace_expired", result["violations"])
        self.assertGreaterEqual(fixture.signals[1][2] - fixture.signals[0][2], 10)
        self.assertEqual(result["returncode"], -9)

    def test_rss_watchdog_kills_once_and_no_sigint(self):
        fixture = FakeMonitor(rss=768 * 1024 + 1, exit_code=-9)
        result = fixture.run(cancellation=True)
        self.assertEqual([s for _, s, _ in fixture.signals], [signal.SIGKILL])
        self.assertEqual(result["violations"], ["rss_watchdog"])

    def test_timeout_kills_once(self):
        fixture = FakeMonitor(exit_at=.3, exit_code=-9)
        result = fixture.run(timeout=.1)
        self.assertEqual([s for _, s, _ in fixture.signals], [signal.SIGKILL])
        self.assertEqual(result["violations"], ["timeout"])

    def test_affinity_drift_fails_and_kills(self):
        fixture = FakeMonitor(affinity=[2, 3, 4], exit_code=-9)
        result = fixture.run()
        self.assertEqual(result["violations"], ["affinity_changed"])
        self.assertEqual([s for _, s, _ in fixture.signals], [signal.SIGKILL])

    def test_cancel_payload_and_no_completed_state(self):
        payload = {"schemaVersion": profile.SCHEMA, "exitCode": 1, "status": "error", "command": "calibrate", "engineVersion": "1.6.2",
                   "error": {"type": "OperationCanceledException"}, "outputDirectory": None, "manifestPath": None, "artifacts": []}
        record = {"returncode": 1, "command": ["/cli", "calibrate"], "cancellationSignalSent": True}
        self.assertEqual(profile.check_payload(payload, record, cancellation=True), [])
        altered = dict(payload, status="completed")
        self.assertTrue(profile.check_payload(altered, record, cancellation=True))
        record["cancellationSignalSent"] = False
        self.assertIn("Process finished before planned cancellation", profile.check_payload(payload, record, cancellation=True))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertEqual(profile.check_output(payload, root, {}, cancellation=True), [])
            (root / "calibration_state.json").write_text("{}")
            self.assertTrue(profile.check_output(payload, root, {}, cancellation=True))

    def test_archive_raw_bytes_crc_inventory_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "run"
            root.mkdir()
            (root / "input.csv").write_bytes(b"a,b\n1,2\n")
            archive = Path(temp) / "evidence.zip"
            result = profile.archive_evidence(root, archive)
            self.assertTrue(result["crcVerified"] and result["inventoryHashesVerified"])
            with zipfile.ZipFile(archive) as zipped:
                self.assertEqual(zipped.read("cli-resource-profile-round17/input.csv"), b"a,b\n1,2\n")
            with self.assertRaises(FileExistsError):
                profile.archive_evidence(root, archive)

    def test_archive_rejects_compiled_binaries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "run"
            root.mkdir()
            (root / "core.dll").write_bytes(b"not-for-delivery")
            with self.assertRaisesRegex(ValueError, "Compiled binary"):
                profile.archive_evidence(root, Path(temp) / "evidence.zip")

    def test_existing_evidence_prevents_process_launch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cli = root / "mvs"
            cli.write_bytes(b"fixture")
            existing = root / "existing"
            existing.mkdir()
            with patch.object(profile, "require_linux"), patch.object(profile.subprocess, "Popen") as launch:
                with self.assertRaises(FileExistsError):
                    profile.run_profile(cli, existing, root / "summary.json", root / "evidence.zip")
            launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
