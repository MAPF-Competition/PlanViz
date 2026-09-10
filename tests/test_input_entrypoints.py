"""Input converters remain selectable across CLI, workers, and desktop exports."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/planviz-qt-test-mpl")

from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from planviz_qt.application.loading import LoadRequest, LoadResult, LoadWorker
from planviz_qt.domain.analytics import AnalyticsIndex
from planviz_qt.io.loader import load_plan
from planviz_qt.ui.main_window import MainWindow, OpenPlanDialog, ViewOptions


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
MAP = ROOT / "example/warehouse_small.map"
PLAN = ROOT / "example/warehouse_small_2026.json"
APP = QApplication.instance() or QApplication([])


def command(module, *arguments):
    # Exercise the public command while actively forbidding GUI imports. This
    # catches accidental Qt coupling even on machines where Qt is installed.
    runner = """
import importlib.abc
import runpy
import sys
class NoQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'PySide6' or fullname.startswith('PySide6.'):
            raise RuntimeError('Headless command tried to import Qt')
sys.meta_path.insert(0, NoQt())
module = sys.argv.pop(1)
runpy.run_module(module, run_name='__main__')
"""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(SOURCE)
    return subprocess.run([sys.executable, "-B", "-c", runner, module, *map(str, arguments)],
                          text=True, capture_output=True, env=environment, timeout=30)


class InputCommandTests(unittest.TestCase):
    def test_palette_validation_is_available_without_qt(self):
        with tempfile.TemporaryDirectory() as directory:
            palette = Path(directory) / "palette.yaml"
            palette.write_text('Agent:\n  Idle: "#342353"\n')
            args = ("--inspect", "--map", MAP, "--plan", PLAN, "--n", "2", "--palette", palette)
            result = command("planviz_qt", *args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["agents"], 2)
            palette.write_text('agent:\n  idle: "not-a-color"\n')
            result = command("planviz_qt", *args)
            self.assertEqual(result.returncode, 2)
            self.assertIn("Cannot load palette", result.stderr)

    def test_list_formats_needs_no_map_or_qt(self):
        result = command("planviz_qt", "--list-formats")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([line.split("\t")[0] for line in result.stdout.splitlines()],
                         ["auto", "lorr-2023", "lorr-2024", "lorr-2026", "planviz"])

    def test_inspect_explicit_converter_and_legacy_version(self):
        for options in (("--format", "lorr-2026"), ("--version", "2026 LoRR")):
            with self.subTest(options=options):
                result = command("planviz_qt", "--inspect", "--map", MAP, "--plan", PLAN,
                                 "--n", "2", *options)
                self.assertEqual(result.returncode, 0, result.stderr)
                stats = json.loads(result.stdout)
                self.assertEqual((stats["agents"], stats["action_model"], stats["time_unit"]),
                                 (2, "MAPF_T", "tick"))

    def test_normalize_then_inspect_and_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "normalized.json"
            converted = command("planviz_qt.converters", "normalize", "--map", MAP,
                                "--plan", PLAN, "--format", "lorr-2026", "--n", "2",
                                "--output", output)
            self.assertEqual(converted.returncode, 0, converted.stderr)
            inspected = command("planviz_qt", "--inspect", "--map", MAP, "--plan", output,
                                "--format", "planviz")
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            self.assertEqual(json.loads(inspected.stdout)["agents"], 2)
            original = load_plan(MAP, PLAN, team_size=2)
            restored = load_plan(MAP, output, input_format="planviz")
            self.assertEqual(restored.max_time, original.max_time)
            for planned in (False, True):
                for at in (0, 1, 50, original.max_time):
                    np.testing.assert_array_equal(restored.paths.positions(at, planned),
                                                  original.paths.positions(at, planned))

    def test_conflicting_converter_and_version_fails_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "bad.json"
            result = command("planviz_qt.converters", "normalize", "--map", MAP,
                             "--plan", PLAN, "--format", "lorr-2026", "--version", "2023 LoRR",
                             "--output", output)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("Conversion failed", result.stderr)
            self.assertFalse(output.exists())


class DesktopInputTests(unittest.TestCase):
    def test_dialog_returns_converter_id_and_preserves_request_positions(self):
        legacy = LoadRequest("map", "plan", "2023 LoRR", 5, (("highway", "hwy"),))
        self.assertEqual((legacy.input_format, legacy.overlays), ("auto", (("highway", "hwy"),)))
        dialog = OpenPlanDialog(map_path=str(MAP), plan_path=str(PLAN))
        self.addCleanup(dialog.deleteLater)
        self.assertEqual(dialog.request().input_format, "auto")
        dialog.input_format.setCurrentIndex(dialog.input_format.findData("lorr-2026"))
        dialog.agents.setValue(2)
        selected = dialog.request()
        self.assertEqual((selected.input_format, selected.version, selected.team_size),
                         ("lorr-2026", None, 2))

    def test_worker_passes_selected_converter(self):
        request = LoadRequest(str(MAP), str(PLAN), team_size=2, input_format="lorr-2026")
        worker = LoadWorker(7, request)
        loaded, failed, finished = (QSignalSpy(worker.signals.loaded), QSignalSpy(worker.signals.failed),
                                    QSignalSpy(worker.signals.finished))
        with patch("planviz_qt.io.loader.load_plan", wraps=load_plan) as loader:
            worker.run()
        self.assertEqual(failed.count(), 0)
        self.assertEqual((loaded.count(), finished.count()), (1, 1))
        self.assertEqual(loader.call_args.kwargs["input_format"], "lorr-2026")
        self.assertEqual(loaded.at(0)[1].plan.team_size, 2)

    def test_normalized_export_saves_full_loaded_plan_and_reports_io_errors(self):
        window = MainWindow(ViewOptions(end=50))
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        self.assertFalse(window.export_plan_action.isEnabled())
        plan = load_plan(MAP, PLAN, team_size=2)
        window.request = LoadRequest(str(MAP), str(PLAN), team_size=2)
        window.accept_result(LoadResult(plan, AnalyticsIndex(plan)))
        self.assertTrue(window.export_plan_action.isEnabled())
        self.assertEqual(window.playback.speed, 10)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "export.json"
            with patch("planviz_qt.ui.main_window.QFileDialog.getSaveFileName",
                       return_value=(str(output), "")):
                window.export_plan()
                restored = load_plan(MAP, output, input_format="planviz")
                self.assertEqual((restored.team_size, restored.max_time), (2, plan.max_time))
                np.testing.assert_array_equal(restored.paths.positions(plan.max_time),
                                              plan.paths.positions(plan.max_time))
                with patch("planviz_qt.converters.exchange.dump_plan", side_effect=OSError("disk full")), \
                        patch("planviz_qt.ui.main_window.QMessageBox.warning") as warning:
                    window.export_plan()
                self.assertIn("disk full", warning.call_args.args[2])


if __name__ == "__main__":
    unittest.main()
