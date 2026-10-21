import dataclasses
import io
import json
import os
import shutil
import tarfile
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from ops import recovery
from ops.recovery_archive import FORMAT, RecoveryError, create_bundle
from ops.recovery_prune import (
    STAMP_FORMAT,
    Bundle,
    apply_prune,
    confirm_removable,
    plan_prune,
    render_plan,
    select,
)

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)  # quarta-feira, semana ISO 43
DAY = timedelta(days=1)
HOUR = timedelta(hours=1)
MARKER = "SECRET-MANIFEST-MARKER"
KEY = "00000000000000000000000000000001.wav"
PAYLOAD = b"synthetic-audio-for-prune-test"


def at(month, day, hour=9, year=2026):
    return datetime(year, month, day, hour, tzinfo=UTC)


def bundle_id(moment, index=0):
    return f"aulas-{moment.strftime(STAMP_FORMAT)}-{index:032x}"


def make_bundle(root, moment, index=0, size=16, manifest=None):
    path = root / bundle_id(moment, index)
    path.mkdir(mode=0o700)
    (path / "database.dump").write_bytes(b"d" * size)
    (path / "voice.tar").write_bytes(b"v" * size)
    value = {
        "format": FORMAT,
        "bundle_id": path.name,
        "created_at": moment.isoformat(),
        "snapshot": {"revision": [MARKER], "counts": {"users": 1}, "audio": []},
    }
    value.update(manifest or {})
    (path / "manifest.json").write_text(json.dumps(value), encoding="utf-8")
    return path


def make_partial(root, moment, touched, index=0):
    path = root / f".partial-{bundle_id(moment, index)}"
    path.mkdir(mode=0o700)
    (path / "database.dump").write_bytes(b"partial")
    seconds = touched.timestamp()
    os.utime(path / "database.dump", (seconds, seconds))
    os.utime(path, (seconds, seconds))
    return path


def real_capture(path):
    (path / "database.dump").write_bytes(b"synthetic-custom-dump")
    with tarfile.open(path / "voice.tar", "w") as archive:
        member = tarfile.TarInfo(KEY)
        member.size = len(PAYLOAD)
        archive.addfile(member, io.BytesIO(PAYLOAD))
    return {
        "snapshot": {
            "revision": ["test-revision"],
            "counts": {"users": 1},
            "audio": [{"id": 1, "key": KEY, "size": len(PAYLOAD), "status": "ready"}],
        },
        "source": {"kind": "lab"},
        "application": {"worktree_head": "test"},
    }


class PruneRetentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "recovery"
        self.root.mkdir(mode=0o700)

    def test_seven_daily_plus_four_weekly_from_iso_weeks_before_the_dailies(self):
        moments = {
            "oct21_new": at(10, 21, 11),
            "oct21_old": at(10, 21, 2),
            "oct20": at(10, 20),
            "oct19": at(10, 19),
            "oct18_new": at(10, 18, 20),
            "oct18_old": at(10, 18, 3),
            "oct17": at(10, 17),
            "oct16": at(10, 16),
            "oct15": at(10, 15),  # sétimo dia; semana ISO 42
            "oct14": at(10, 14),  # semana 42: mesma do diário mais antigo, não vira semanal
            "oct13": at(10, 13),
            "oct11": at(10, 11),  # semana 41
            "oct09": at(10, 9),
            "oct02": at(10, 2),  # semana 40
            "sep24": at(9, 24),  # semana 39
            "sep18": at(9, 18),  # semana 38
            "sep10": at(9, 10),  # semana 37: quinta semana, descartada
            "sep01": at(9, 1),
        }
        names = {
            label: make_bundle(self.root, moment, index).name
            for index, (label, moment) in enumerate(moments.items())
        }
        plan = plan_prune(self.root, now=NOW)
        kept = {bundle.name: reasons for bundle, reasons in plan.keep}
        expected = {
            "oct21_new",
            "oct20",
            "oct19",
            "oct18_new",
            "oct17",
            "oct16",
            "oct15",
            "oct11",
            "oct02",
            "sep24",
            "sep18",
        }
        self.assertEqual(set(kept), {names[label] for label in expected})
        self.assertEqual(
            {bundle.name for bundle in plan.remove},
            {names[label] for label in set(moments) - expected},
        )
        self.assertEqual(plan.newest, names["oct21_new"])
        self.assertEqual(kept[names["oct21_new"]], ("mais recente", "diário"))
        self.assertEqual(kept[names["oct15"]], ("diário",))
        for label in ("oct11", "oct02", "sep24", "sep18"):
            self.assertEqual(kept[names[label]], ("semanal",), label)
        self.assertEqual(
            [bundle.name for bundle, _ in plan.keep][:3],
            [names["oct21_new"], names["oct20"], names["oct19"]],
        )

    def test_fewer_than_seven_days_keeps_only_newest_of_each_day(self):
        for hour in (1, 5, 9):
            make_bundle(self.root, at(10, 14, hour), hour)
        for hour in (2, 8):
            make_bundle(self.root, at(10, 15, hour), 10 + hour)
        make_bundle(self.root, at(10, 16), 20)
        plan = plan_prune(self.root, now=NOW)
        self.assertEqual(
            [bundle.name for bundle, _ in plan.keep],
            [bundle_id(at(10, 16), 20), bundle_id(at(10, 15, 8), 18), bundle_id(at(10, 14, 9), 9)],
        )
        self.assertEqual(len(plan.remove), 3)
        self.assertFalse(any("semanal" in reasons for _, reasons in plan.keep))

    def test_weekly_selection_orders_iso_weeks_across_year_boundary(self):
        bundles = [
            Bundle(bundle_id(at(1, 5), 1), at(1, 5), 1),  # 2026-W02
            Bundle(bundle_id(at(12, 30, year=2025), 2), at(12, 30, year=2025), 1),  # 2026-W01
            Bundle(bundle_id(at(12, 25, year=2025), 3), at(12, 25, year=2025), 1),  # 2025-W52
            Bundle(bundle_id(at(12, 24, year=2025), 4), at(12, 24, year=2025), 1),  # 2025-W52
        ]
        keep, remove = select(bundles, keep_daily=1, keep_weekly=4)
        self.assertEqual(
            [(b.name, r) for b, r in keep],
            [
                (bundles[0].name, ("mais recente", "diário")),
                (bundles[1].name, ("semanal",)),
                (bundles[2].name, ("semanal",)),
            ],
        )
        self.assertEqual([b.name for b in remove], [bundles[3].name])

    def test_newest_bundle_protected_even_when_policy_keeps_nothing(self):
        bundles = [Bundle(bundle_id(at(10, day), day), at(10, day), 1) for day in (1, 2, 3)]
        keep, remove = select(bundles, keep_daily=0, keep_weekly=0)
        self.assertEqual([(b.name, r) for b, r in keep], [(bundles[2].name, ("mais recente",))])
        self.assertEqual([b.name for b in remove], [bundles[1].name, bundles[0].name])
        for day in (1, 2, 3):
            make_bundle(self.root, at(10, day), day)
        plan = plan_prune(self.root, now=NOW)
        forged = dataclasses.replace(plan, remove=plan.remove + tuple(b for b, _ in plan.keep))
        with self.assertRaisesRegex(RecoveryError, "mais recente"):
            confirm_removable(forged, plan.newest)
        self.assertTrue((self.root / plan.newest).is_dir())

    def test_partial_under_24h_protected_and_older_removable(self):
        make_bundle(self.root, at(10, 20))
        fresh_stamp = make_partial(self.root, NOW - 2 * HOUR, NOW - 2 * HOUR, 1)
        touched_recently = make_partial(self.root, NOW - 3 * DAY, NOW - 1 * HOUR, 2)
        boundary = make_partial(self.root, NOW - 24 * HOUR, NOW - 24 * HOUR, 3)
        stale = make_partial(self.root, NOW - 3 * DAY, NOW - 3 * DAY, 4)
        odd = self.root / ".partial-incomplete"
        odd.mkdir()
        plan = plan_prune(self.root, now=NOW)
        self.assertEqual(
            {p.name: plan.partial_removable(p) for p in plan.partials},
            {
                fresh_stamp.name: False,
                touched_recently.name: False,
                boundary.name: True,
                stale.name: True,
            },
        )
        self.assertIn(odd.name, {f.name for f in plan.foreign})
        self.assertEqual(set(plan.targets()), {boundary.name, stale.name})
        self.assertEqual(plan.remove, ())

    def test_out_of_policy_entries_listed_and_untouched_by_apply(self):
        valid = make_bundle(self.root, at(10, 20, 9), 1)
        older = make_bundle(self.root, at(10, 20, 3), 2)
        receipts = self.root / "restore-receipts"
        receipts.mkdir()
        (receipts / f"{valid.name}.json").write_text("{}")
        (self.root / "upgrade-receipts").mkdir()
        application = self.root / "sprint39-application-before-20261015T152736"
        application.mkdir()
        (application / "manifest.json").write_text("{}")
        (application / "api.tar").write_bytes(b"a" * 64)
        (self.root / "roles-prod.env").write_text("ROLE_PASSWORD=do-not-print")
        (self.root / f"rehearse-{valid.name}.json").write_text("{}")
        (self.root / ".DS_Store").write_bytes(b"\x00")
        no_manifest = self.root / bundle_id(at(10, 19), 3)
        no_manifest.mkdir()
        wrong_identity = make_bundle(self.root, at(10, 18), 4, manifest={"bundle_id": "aulas-x"})
        wrong_format = make_bundle(self.root, at(10, 17), 5, manifest={"format": "aulas-x-v9"})
        link = self.root / bundle_id(at(10, 16), 6)
        link.symlink_to(valid, target_is_directory=True)
        expected_foreign = {
            receipts.name,
            "upgrade-receipts",
            application.name,
            "roles-prod.env",
            f"rehearse-{valid.name}.json",
            ".DS_Store",
            no_manifest.name,
            wrong_identity.name,
            wrong_format.name,
            link.name,
        }

        plan = plan_prune(self.root, now=NOW)
        self.assertEqual({f.name for f in plan.foreign}, expected_foreign)
        self.assertEqual([b.name for b, _ in plan.keep], [valid.name])
        self.assertEqual([b.name for b in plan.remove], [older.name])
        self.assertEqual(
            next(f for f in plan.foreign if f.name == application.name).size, 64 + 2
        )
        self.assertEqual(apply_prune(plan), [older.name])
        self.assertEqual(
            {p.name for p in self.root.iterdir()}, expected_foreign | {valid.name}
        )
        self.assertTrue(link.is_symlink() and (valid / "manifest.json").is_file())
        self.assertNotIn("do-not-print", render_plan(plan) + render_plan(plan, as_json=True))

    def test_output_contains_only_name_date_and_size(self):
        make_bundle(self.root, at(10, 20, 9), 1)
        make_bundle(self.root, at(10, 20, 3), 2)
        make_partial(self.root, NOW - 2 * DAY, NOW - 2 * DAY, 3)
        plan = plan_prune(self.root, now=NOW)
        for text in (render_plan(plan), render_plan(plan, as_json=True), render_plan(plan, [])):
            for forbidden in (MARKER, "snapshot", "users", "revision", "created_at"):
                self.assertNotIn(forbidden, text)
        report = json.loads(render_plan(plan, as_json=True))
        self.assertEqual(set(report["keep"][0]), {"name", "date", "size", "reasons"})
        self.assertEqual(set(report["remove"][0]), {"name", "date", "size"})
        self.assertEqual(
            set(report["partials"][0]), {"name", "date", "size", "age_hours", "action"}
        )

    def test_real_create_bundle_output_is_recognised_with_its_utc_stamp(self):
        bundle = create_bundle(self.root, real_capture)
        plan = plan_prune(self.root)
        ((kept, reasons),) = plan.keep
        self.assertEqual((kept.name, plan.newest), (bundle.name, bundle.name))
        self.assertEqual(reasons, ("mais recente", "diário"))
        self.assertLess(abs(datetime.now(UTC) - kept.stamp), timedelta(minutes=5))
        self.assertEqual(kept.size, sum(p.stat().st_size for p in bundle.iterdir()))
        self.assertEqual(plan.remove, ())


class PruneCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "recovery"
        self.root.mkdir(mode=0o700)
        # Retenção não depende do relógio; só a idade dos parciais depende, e usa o `now` real.
        now = datetime.now(UTC)
        self.kept_newest = make_bundle(self.root, at(10, 20, 9), 1)
        self.removable = make_bundle(self.root, at(10, 20, 3), 2)
        self.kept_other_day = make_bundle(self.root, at(10, 19), 3)
        self.stale_partial = make_partial(self.root, now - 3 * DAY, now - 3 * DAY, 4)
        self.fresh_partial = make_partial(self.root, now - 1 * HOUR, now - 1 * HOUR, 5)
        receipts = self.root / "restore-receipts"
        receipts.mkdir()
        (receipts / "receipt.json").write_text("{}")
        (self.root / "roles-lab.env").write_text("x=1")

    def snapshot(self):
        return sorted(
            (str(p.relative_to(self.root)), p.lstat().st_mtime_ns, p.lstat().st_size)
            for p in self.root.rglob("*")
        )

    def run_main(self, *argv, root=None):
        output, errors = io.StringIO(), io.StringIO()
        with (
            patch.object(recovery, "BACKUPS", root or self.root),
            redirect_stdout(output),
            redirect_stderr(errors),
        ):
            code = recovery.main(["prune", *argv])
        return code, output.getvalue(), errors.getvalue()

    def test_dry_run_is_default_and_changes_nothing_on_disk(self):
        before = self.snapshot()
        code, out, err = self.run_main()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(self.snapshot(), before)
        self.assertIn("Nada foi alterado em disco", out)
        self.assertIn(f"Remover (1):\n  {self.removable.name}", out)
        self.assertIn("protegido (< 24 h)", out)
        code, out, _ = self.run_main("--dry-run", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(self.snapshot(), before)
        report = json.loads(out)
        self.assertEqual((report["mode"], report["removed"]), ("dry-run", []))
        self.assertEqual(
            [e["name"] for e in report["keep"]],
            [self.kept_newest.name, self.kept_other_day.name],
        )
        self.assertEqual([e["name"] for e in report["remove"]], [self.removable.name])
        self.assertEqual(
            {p["name"]: p["action"] for p in report["partials"]},
            {self.fresh_partial.name: "protect", self.stale_partial.name: "remove"},
        )
        self.assertEqual(
            {e["name"] for e in report["out_of_policy"]}, {"restore-receipts", "roles-lab.env"}
        )

    def test_apply_removes_exactly_the_plan(self):
        plan = plan_prune(self.root)
        expected_removed = {self.removable.name, self.stale_partial.name}
        self.assertEqual(set(plan.targets()), expected_removed)
        code, out, err = self.run_main("--apply", "--json")
        self.assertEqual((code, err), (0, ""))
        report = json.loads(out)
        self.assertEqual((report["mode"], set(report["removed"])), ("apply", expected_removed))
        self.assertEqual(
            {p.name for p in self.root.iterdir()},
            {
                self.kept_newest.name,
                self.kept_other_day.name,
                self.fresh_partial.name,
                "restore-receipts",
                "roles-lab.env",
            },
        )
        code, out, _ = self.run_main("--apply")
        self.assertEqual(code, 0)
        self.assertIn("Removidos (0): nenhum", out)

    def test_dry_run_and_apply_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            recovery.main(["prune", "--dry-run", "--apply"])

    def test_refuses_missing_empty_or_foreign_only_directory(self):
        missing = Path(self.tmp.name) / "missing"
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        foreign_only = Path(self.tmp.name) / "foreign"
        foreign_only.mkdir()
        (foreign_only / "restore-receipts").mkdir()
        (foreign_only / "roles-prod.env").write_text("x=1")
        make_partial(foreign_only, NOW - 3 * DAY, NOW - 3 * DAY)
        for root in (missing, empty, foreign_only):
            for argv in ((), ("--apply",)):
                with self.subTest(root=root.name, argv=argv):
                    before = sorted(p.name for p in root.iterdir()) if root.exists() else None
                    code, out, err = self.run_main(*argv, root=root)
                    self.assertEqual((code, out), (1, ""))
                    self.assertIn("recusada", err)
                    after = sorted(p.name for p in root.iterdir()) if root.exists() else None
                    self.assertEqual(after, before)
        self.assertFalse(missing.exists())

    def test_apply_rechecks_pattern_root_and_links_before_each_removal(self):
        decoy = Path(self.tmp.name) / "decoy"
        decoy.mkdir()
        (decoy / "keep-me").write_text("x")
        plan = plan_prune(self.root)
        self.assertEqual(confirm_removable(plan, self.removable.name), self.removable)
        refused = (
            "restore-receipts",
            plan.newest,
            f"../{self.removable.name}",
            self.kept_other_day.name,
        )
        for name in refused:
            with self.subTest(name=name), self.assertRaises(RecoveryError):
                confirm_removable(plan, name)
        shutil.rmtree(self.removable)
        self.removable.symlink_to(decoy, target_is_directory=True)
        with self.assertRaisesRegex(RecoveryError, "recusada"):
            apply_prune(plan)
        self.assertTrue((decoy / "keep-me").is_file())
        self.assertTrue(self.stale_partial.is_dir())


if __name__ == "__main__":
    unittest.main()
