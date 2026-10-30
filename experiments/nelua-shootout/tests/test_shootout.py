import contextlib
import csv
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("shootout", ROOT / "shootout.py")
shootout = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(shootout)


class ShootoutTests(unittest.TestCase):
    def test_frozen_matrix_and_real_tabs(self):
        pins = shootout.read_pins()
        self.assertEqual(tuple(pins), shootout.TOP5)
        self.assertEqual(len(shootout.read_cases()), 6)
        self.assertNotIn("\\t", (ROOT / "pins.tsv").read_text())

    def test_rejects_lower_ranked_substitute(self):
        with tempfile.TemporaryDirectory() as temporary:
            file = Path(temporary) / "cases.tsv"
            names = list(shootout.ALL_NAMES)
            names[2] = "c-epoll-substitute"
            shootout.write_tsv(file, [{"name": name, "launcher": "/bin/true"} for name in names],
                               ("name", "launcher"))
            with self.assertRaisesRegex(ValueError, "exactly Nelua"):
                shootout.read_cases(file)

    def test_binary_cases_and_comparator_pins(self):
        with tempfile.TemporaryDirectory() as temporary:
            file = Path(temporary) / "cases.tsv"
            pins = shootout.read_pins()
            rows = [{"name": name, "binary": "/bin/true",
                     "sourcepin": pins.get(name, {}).get("source_commit", "")}
                    for name in shootout.ALL_NAMES]
            shootout.write_tsv(file, rows, ("name", "binary", "sourcepin"))
            self.assertEqual(len(shootout.read_cases(file)), 6)
            rows[1]["sourcepin"] = "wrong"
            shootout.write_tsv(file, rows, ("name", "binary", "sourcepin"))
            with self.assertRaisesRegex(ValueError, "sourcepin"):
                shootout.read_cases(file)

    def test_cpu_samples_are_in_core_equivalents(self):
        with patch.object(shootout.os, "sysconf", return_value=100):
            self.assertEqual(shootout.app_cpu([{"time": 10, "cpu_jiffies": 100},
                                               {"time": 12, "cpu_jiffies": 400}]), 1.5)

    def test_williams_positions_and_all_directed_carryovers(self):
        names = shootout.ALL_NAMES
        orders = shootout.balanced_orders(names, 6, 2309)
        self.assertEqual(orders, shootout.balanced_orders(names, 6, 2309))
        self.assertNotEqual(orders, shootout.balanced_orders(names, 6, 2310))
        for position in range(6):
            self.assertEqual({row[position] for row in orders}, set(names))
        pairs = [(a, b) for row in orders for a, b in zip(row, row[1:])]
        self.assertEqual(len(set(pairs)), 30)
        self.assertEqual(set(pairs), {(a, b) for a in names for b in names if a != b})

    def test_variants_are_only_numeric_native_knobs(self):
        variants = shootout.parse_variants(["base:READ_GATHER_SERIAL=0,READ_PIPELINE=0",
                                           "candidate:READ_GATHER_SERIAL=1,READ_PIPELINE=1"])
        self.assertEqual(variants["candidate"]["READ_PIPELINE"], "1")
        for value in ("bad:DATABASE_URL=1", "bad:READ_PIPELINE=-1", "x:", "x:READ_PIPELINE=1,x=2"):
            if value == "x:":
                self.assertEqual(shootout.parse_variants([value]), {"x": {}})
                continue
            with self.assertRaises(ValueError):
                shootout.parse_variants([value])

    def test_blocked_and_loadgen_limited_are_ineligible(self):
        rows = [{"round": 1, "users": 1000, "name": name, "variant": "default",
                 "status": "pass", "lg_limited": False} for name in shootout.ALL_NAMES]
        self.assertTrue(shootout.complete_matrix(rows, 1, [1000]))
        rows[2]["lg_limited"] = True
        self.assertFalse(shootout.complete_matrix(rows, 1, [1000]))
        rows[2].update(lg_limited=False, status="blocked")
        self.assertFalse(shootout.complete_matrix(rows, 1, [1000]))
        self.assertFalse(shootout.complete_matrix(rows[:2] + rows[3:], 1, [1000]))

    def test_native_variants_do_not_create_other_comparators(self):
        variants = {"base": {}, "candidate": {"READ_PIPELINE": "1"}}
        rows = [{"round": 1, "users": 1000, "name": name, "variant": variant,
                 "status": "pass", "lg_limited": False}
                for name in shootout.ALL_NAMES
                for variant in (variants if name == shootout.OUR_NAME else ("default",))]
        self.assertEqual(len(rows), 7)
        self.assertTrue(shootout.complete_matrix(rows, 1, [1000], variants))
        self.assertFalse(shootout.complete_matrix(rows[:-1], 1, [1000], variants))

    def test_descriptor_limit_clamps_without_privilege(self):
        with patch.object(shootout.resource, "getrlimit", return_value=(1024, 16384)), \
                patch.object(shootout.resource, "setrlimit") as setter:
            shootout.child_limits()
            setter.assert_called_once_with(shootout.resource.RLIMIT_NOFILE, (16384, 16384))
        with patch.object(shootout.resource, "getrlimit", return_value=(1024, 1048576)), \
                patch.object(shootout.resource, "setrlimit") as setter:
            shootout.child_limits()
            setter.assert_called_once_with(shootout.resource.RLIMIT_NOFILE, (200000, 200000))

    def test_database_identifiers_reject_sql(self):
        for value in ("seed;DROP DATABASE x", "Seed", "a'", "a" * 64):
            with self.assertRaises(ValueError):
                shootout.identifier(value)

    def test_fake_host_continues_after_blocked_comparators(self):
        """Exercise orchestration/reporting without PostgreSQL, sockets or real load."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            args = SimpleNamespace(output=root / "results", cases=None, template="conduit_seed",
                                   articles=500000, users=[1000], rounds=1, seed=2309, port=3110,
                                   secret="test", variants={"default": {}}, conformance=Path("conformance"),
                                   warmup=1, measure=20, ramp=5, tail=3, think_scale=0.1)
            events = []
            class FakeServer:
                def __init__(self, case, database, port, directory, secret, settings):
                    self.name = case["name"]
                    self.database = database
                    self.process = SimpleNamespace(pid=123, poll=lambda: None)
                    self.url = "http://fake"
                def __enter__(self):
                    if self.name == shootout.TOP5[4]:
                        raise RuntimeError("Native AOT build blocked")
                    events.append(("start", self.name))
                    return self
                def __exit__(self, *_):
                    events.append(("stop", self.name))
            class FakeMonitor:
                def __init__(self, *_):
                    self.samples = [{"connections": 20, "rss_mb": 30}]
                def __enter__(self):
                    return self
                def __exit__(self, *_):
                    return None
            def load(args, server, users, directory, label, warmup=False):
                if warmup:
                    return None
                return {"overall": {"rps": 100, "p50_ms": 1, "p95_ms": 2,
                                    "p99_ms": 3, "errors": 0, "error_rate": 0},
                        "verdict": {"pass": True, "lg_limited": server.name == shootout.TOP5[2]},
                        "boxes": [{"cpu_avg_measure_pct": 30, "proc_cpu_avg_measure_pct": 10}]}
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(shootout, "environment_metadata", return_value={"io_uring": "blocked: EPERM"}))
                stack.enter_context(patch.object(shootout, "source_metadata", return_value=[]))
                stack.enter_context(patch.object(shootout, "create_database", side_effect=lambda db, template: events.append(("create", db))))
                stack.enter_context(patch.object(shootout, "drop_database", side_effect=lambda db: events.append(("drop", db))))
                stack.enter_context(patch.object(shootout, "Server", FakeServer))
                stack.enter_context(patch.object(shootout, "Monitor", FakeMonitor))
                stack.enter_context(patch.object(shootout, "command", return_value=SimpleNamespace(returncode=0)))
                stack.enter_context(patch.object(shootout, "load_run", side_effect=load))
                self.assertEqual(shootout.run(args), 2)
            with (args.output / "runs.tsv").open() as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual(len(rows), 6)
            by_name = {row["name"]: row for row in rows}
            self.assertEqual(by_name[shootout.TOP5[1]]["status"], "blocked")
            self.assertEqual(by_name[shootout.TOP5[4]]["status"], "blocked")
            self.assertEqual(by_name[shootout.TOP5[2]]["lg_limited"], "True")
            self.assertEqual(by_name[shootout.TOP5[3]]["status"], "pass")
            summary = (args.output / "SUMMARY.md").read_text()
            self.assertIn("Complete eligible matrix: **no**", summary)
            self.assertIn("No shootout winner is declared", summary)
            self.assertEqual(sum(event[0] == "create" for event in events), 9)
            self.assertEqual(sum(event[0] == "drop" for event in events), 9)
            self.assertEqual(sum(event[0] == "start" for event in events), 8)
            # Every successful server stops before another is started.
            active = 0
            for event in events:
                if event[0] == "start": active += 1
                if event[0] == "stop": active -= 1
                self.assertIn(active, (0, 1))


if __name__ == "__main__":
    unittest.main()
