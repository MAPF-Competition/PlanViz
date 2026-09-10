"""Palette files, live legend controls, and recorded-state colors agree."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/planviz-qt-test-mpl")

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from planviz_qt.application.loading import LoadResult
from planviz_qt.domain.analytics import AnalyticsIndex
from planviz_qt.domain.models import Conflict, Event, Task
from planviz_qt.io.loader import load_plan
from planviz_qt.palette import load_palette
from planviz_qt.ui.main_window import MainWindow


ROOT = Path(__file__).resolve().parents[1]
APP = QApplication.instance() or QApplication([])


class PaletteApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = load_plan(ROOT / "example/warehouse_small.map",
                           ROOT / "example/warehouse_small_2026.json", team_size=5)
        tasks = tuple(Task(agent, 0, ((agent + 1, 1), (agent + 1, 2)),
                           ((0 if agent in (0, 3, 4) else 1, agent),),
                           ((1, agent, 0),) if agent in (3, 4) else ()) for agent in range(5))
        cls.plan = replace(source, tasks=tasks, events=(
            Event(1, 1, 1, "assigned"), Event(1, 2, 2, "assigned"),
            Event(1, 3, 3, "errand_finished", 0), Event(1, 4, 4, "errand_finished", 0),
        ), delays={agent: ((1, 1),) for agent in (2, 3, 4)},
            conflicts=(Conflict(1, (4,), "Recorded conflict"),))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "custom.yaml"
        self.path.write_text('''agent:
  idle: "#112233"
  newly_assigned: "#223344"
  delayed: "#334455"
  errand_completed: "#445566"
  collision: "#556677"
task:
  assigned: "#abcdef"
errand:
  assigned: "#654321"
''')
        self.window = MainWindow(palette=load_palette(self.path))
        self.window.accept_result(LoadResult(self.plan, AnalyticsIndex(self.plan)))
        self.window.show()
        APP.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        APP.processEvents()

    def test_recorded_state_priority_and_live_palette_preserve_replay(self):
        window = self.window
        window.layer_actions["collisions"].setChecked(True)
        window.playback.seek(1)
        np.testing.assert_array_equal(window._colors,
                                      ["#112233", "#223344", "#334455", "#445566", "#556677"])
        window.select_agent(0)
        markers = {marker["kind"]: marker for marker in window.map_view.tasks}
        self.assertEqual(markers["task"]["brush"].color().name(), "#abcdef")
        self.assertEqual(markers["errand"]["brush"].color().name(), "#654321")
        position = window.playback.position
        window.playback.play()
        window.apply_palette(load_palette())
        self.assertTrue(window.playback.playing)
        self.assertEqual(window.playback.position, position)
        self.assertEqual(window.selected_agents, {0})
        self.assertIs(window.plan, self.plan)
        self.assertEqual(window._colors[4], window.palette.color("agent", "collision"))
        window.playback.pause()

    def test_legend_load_reload_save_copy_and_invalid_input_retention(self):
        window = self.window
        window.visual_settings.palette_button.click()
        legend = window.legend_dialog
        self.assertTrue(legend.isVisible())
        window.show_palette_legend()
        self.assertIs(window.legend_dialog, legend)
        self.path.write_text('Agent:\n  Idle: "#342353"\n')
        legend.reload_button.click()
        self.assertEqual(window.palette.color("agent", "idle"), "#342353")
        self.assertEqual(window._colors[0], "#342353")
        before = window.palette
        self.path.write_text('agent:\n  idle: "invalid"\n')
        with patch("planviz_qt.ui.main_window.QMessageBox.warning") as warning:
            legend.reload_button.click()
            warning.assert_called_once()
        self.assertIs(window.palette, before)
        self.assertEqual(window._colors[0], "#342353")
        copy = (Path(self.temp.name) / "saved.yaml").resolve()
        with patch("planviz_qt.ui.main_window.QFileDialog.getSaveFileName", return_value=(str(copy), "")):
            legend.save_button.click()
        self.assertEqual(window.palette.source, copy)
        self.assertEqual(load_palette(copy).color("agent", "idle"), "#342353")
        legend.defaults_button.click()
        self.assertIsNone(window.palette.source)
        with patch("planviz_qt.ui.main_window.QFileDialog.getOpenFileName", return_value=(str(copy), "")):
            legend.load_button.click()
        self.assertEqual(window.palette.source, copy)
        window.accept_result(LoadResult(self.plan, AnalyticsIndex(self.plan)))
        self.assertEqual(window.palette.source, copy)
        self.assertEqual(window._colors[0], "#342353")
        self.assertTrue(legend.isVisible())
        QTest.keyClick(legend, Qt.Key.Key_Escape)
        APP.processEvents()
        self.assertFalse(legend.isVisible())
        QTest.keyClick(window.map_view, Qt.Key.Key_Space)
        self.assertTrue(window.playback.playing)


if __name__ == "__main__":
    unittest.main()
