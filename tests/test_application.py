"""Cross-component replay, selection and worker-lifecycle regression checks."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/planviz-qt-test-mpl")

from pathlib import Path
from dataclasses import replace
import time
import unittest
from unittest.mock import patch

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from planviz_qt.application.loading import LoadManager, LoadRequest, LoadResult
from planviz_qt.application.playback import PlaybackController
from planviz_qt.domain.analytics import AnalyticsIndex
from planviz_qt.domain.models import Task
from planviz_qt.domain.paths import MotionSequence, PathStore
from planviz_qt.io.loader import load_plan
from planviz_qt.ui.main_window import MainWindow, ViewOptions

ROOT = Path(__file__).resolve().parents[1]
APP = QApplication.instance() or QApplication([])


def wait_for(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    if not predicate():
        raise AssertionError("Timed out waiting for Qt worker/event delivery")


def request(name="warehouse_small_2026.json"):
    return LoadRequest(str(ROOT / "example/warehouse_small.map"), str(ROOT / "example" / name))


class PlaybackTests(unittest.TestCase):
    def test_clock_not_callback_count_and_end(self):
        controller = PlaybackController()
        changed = QSignalSpy(controller.timeChanged)
        controller.configure(10, 20, speed=4)
        controller.advance_seconds(.5)
        self.assertEqual(controller.time, 12)
        controller.advance_seconds(10)
        self.assertEqual(controller.time, 20)
        self.assertFalse(controller.playing)
        self.assertEqual(changed.count(), 3)
        controller.seek(-1)
        self.assertEqual(controller.time, 10)
        controller.step(2)
        self.assertEqual(controller.time, 12)

    def test_seek_while_playing_pauses_and_clamps(self):
        controller = PlaybackController()
        controller.configure(0, 9)
        controller.play()
        controller.seek(20)
        self.assertFalse(controller.playing)
        self.assertEqual(controller.position, 9)
        with self.assertRaises(ValueError):
            controller.set_speed(float("nan"))


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = load_plan(request().map_path, request().plan_path)

    def setUp(self):
        self.window = MainWindow(ViewOptions(end=200))
        self.window.request = request()
        self.window.accept_result(LoadResult(self.plan, AnalyticsIndex(self.plan)))
        self.window.show()
        QTest.qWait(25)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        APP.processEvents()

    def test_seek_back_is_same_snapshot_and_does_not_recreate_scene(self):
        window = self.window
        before = len(window.map_view.scene().items())
        window.playback.seek(30)
        expected = self.plan.paths.positions(30).copy()
        first_rows = window.events_model.rows
        window.playback.seek(180)
        window.playback.seek(30)
        np.testing.assert_allclose(window.map_view.positions, expected)
        self.assertEqual(window.events_model.rows, first_rows)
        self.assertEqual(len(window.map_view.scene().items()), before)
        self.assertEqual(window.time_edit.text(), "30")

    def test_controls_selection_planned_mode_and_productivity(self):
        window = self.window
        QTest.mouseClick(window.play_button, Qt.MouseButton.LeftButton)
        self.assertTrue(window.playback.playing)
        QTest.mouseClick(window.play_button, Qt.MouseButton.LeftButton)
        self.assertFalse(window.playback.playing)
        window.select_agent(0, center=True)
        window.select_agent(1, True)
        self.assertEqual(window.selected_agents, {0, 1})
        window.filter_agents.setChecked(True)
        window.playback.seek(100)
        self.assertTrue(all(record.agent_id in {0, 1} for record in window.events_model.records))
        window.planned.setChecked(True)
        np.testing.assert_allclose(window.map_view.positions, self.plan.paths.positions(100, planned=True))
        window.show_productivity()
        self.assertEqual(len(window._dialogs), 1)
        window.playback.seek(99)
        QTest.qWait(80)
        self.assertTrue(window._dialogs[0].isVisible())
        original_dialog = window._dialogs[0]
        original_dialog.close()
        window.show_productivity()
        self.assertEqual(window._dialogs, [original_dialog])
        window.clear_selection()
        self.assertEqual(window.selected_agents, set())

    def test_event_navigation_and_task_table_counts(self):
        window = self.window
        window.playback.seek(200)
        if window.events_model.records:
            event = window.events_model.records[0]
            window._event_activated(window.events_model.index(0, 0))
            self.assertEqual(window.playback.time, event.time)
            self.assertIn(event.agent_id, window.selected_agents)
        task_text = window.task_model.data(window.task_model.index(0, 3))
        self.assertNotIn("frozenset", task_text)

    def test_mapf_fractional_frames_preserve_absent_headings(self):
        plan = load_plan(ROOT / "example/random-32-32-20.map", ROOT / "example/mapf_plan_example.json")
        self.window.accept_result(LoadResult(plan, AnalyticsIndex(plan)))
        self.window._render_frame(.5)
        np.testing.assert_array_equal(self.window.map_view.positions[:, 2], -1)

    def test_playback_interpolates_within_tick_without_advancing_records(self):
        window = self.window
        self.assertEqual(window.playback.speed, 10)
        # Find an interval with real translation, rather than testing a wait.
        tick = next(t for t in range(100) if np.any(
            self.plan.paths.positions(t)[:, :2] != self.plan.paths.positions(t+1)[:, :2]))
        window.playback.seek(tick)
        start = self.plan.paths.positions(tick)
        end = self.plan.paths.positions(tick+1)
        records = window.events_model.rows
        for frame in range(1, 6):
            window.playback.advance_seconds(1 / 60)
            expected = start[:, :2] + (end[:, :2] - start[:, :2]) * (frame / 6)
            np.testing.assert_allclose(window.map_view.positions[:, :2], expected, atol=1e-6)
            self.assertEqual(window.playback.time, tick)
            self.assertEqual(window.events_model.rows, records)

    def test_task_visuals_reused_until_transition_and_restored_on_seek(self):
        window = self.window
        task = Task(0, 0, ((1, 2), (3, 4)), ((0, 0),), ((10, 0, 0),))
        plan = replace(self.plan, tasks=(task,), events=())
        window.accept_result(LoadResult(plan, AnalyticsIndex(plan)))
        window.select_agent(0)
        window.playback.seek(1)
        with patch.object(window.map_view, "set_tasks", wraps=window.map_view.set_tasks) as refresh:
            window.playback.seek(2)
            refresh.assert_not_called()
            self.assertEqual(len(window.map_view.tasks), 2)
            window.playback.seek(10)
            self.assertEqual(len(window.map_view.tasks), 1)
            window.playback.seek(1)
            self.assertEqual(len(window.map_view.tasks), 2)
            self.assertEqual(refresh.call_count, 2)
        # Reloading must populate the freshly cleared scene even at the same time.
        window.accept_result(LoadResult(plan, AnalyticsIndex(plan)))
        self.assertEqual(len(window.map_view.tasks), 2)

    def test_hidden_tasks_hide_sequences_and_long_paths_are_consecutive(self):
        window = self.window
        window.select_agent(0)
        window.task_mode.setCurrentIndex(window.task_mode.findData("none"))
        self.assertFalse(window.map_view.task_sequence_geometry)
        window.playback.configure(0, self.plan.max_time)
        window.playback.seek(2800)
        start, end = window._path_range
        self.assertLessEqual(end-start+1, 2000)
        self.assertLessEqual(start, 2800)
        self.assertGreaterEqual(end, 2800)
        self.assertEqual(start, 2800)
        preview = window.selection_paths.preview(0, start, window.playback.end)
        self.assertLessEqual(preview.end-start+1, 2000)
        np.testing.assert_allclose(preview.points[0, :2], self.plan.paths.positions(start)[0, :2])
        np.testing.assert_allclose(preview.points[-1, :2], self.plan.paths.positions(preview.end)[0, :2])

    def test_selected_path_survives_missing_initial_assignment_in_warehouse_log(self):
        window = self.window
        self.assertIsNone(window.analytics.active_task_context(0, 0))
        expected = window.analytics.next_recorded_errand(0, 0)
        self.assertIsNotNone(expected)
        window.select_agent(0)
        path = window.map_view.path_geometry[0]
        self.assertGreater(path.elementCount(), 1)
        np.testing.assert_allclose((path.currentPosition().y() - .5,
                                   path.currentPosition().x() - .5), expected["next_stop"])
        self.assertIn("target from completion record", window.selection_label.text())
        # Previewing a known future completion must not invent an assignment.
        self.assertIsNone(window.analytics.active_task_context(0, 0))
        self.assertEqual(window.analytics.counts(0).get("assigned", 0), 0)
        self.assertIn(0, window.map_view.task_sequence_targets)

    def test_selected_path_is_available_for_taskless_inputs(self):
        plan = replace(self.plan, tasks=(), events=())
        window = self.window
        window.accept_result(LoadResult(plan, AnalyticsIndex(plan)))
        window.select_agent(0)
        self.assertIn(0, window.map_view.path_geometry)
        self.assertIn("no upcoming errand record", window.selection_label.text())
        self.assertFalse(window.map_view.task_sequence_targets)

    def test_selected_path_stops_at_next_errand_and_advances_on_completion(self):
        paths = PathStore(np.array([[1., 1., -1.]]),
                          [MotionSequence(("U", "R", "D"), (2, 2, 2))], action_model="MAPF")
        tasks = (Task(0, 0, ((3, 1), (3, 3)), ((0, 0),), ((2, 0, 0), (4, 0, 1))),
                 Task(1, 4, ((1, 3),), ((4, 0),), ((6, 0, 0),)))
        plan = replace(self.plan, paths=paths, tasks=tasks, events=(), conflicts=(), delays={},
                       action_model="MAPF", time_unit="timestep", ticks_per_step=1, max_time=6)
        window = self.window
        window.accept_result(LoadResult(plan, AnalyticsIndex(plan)))
        window.select_agent(0)
        original_path = window.map_view.path_geometry[0]
        for time, end, target in ((0, 2, (3, 1)), (1, 2, (3, 1)),
                                  (2, 4, (3, 3)), (4, 6, (1, 3))):
            window.playback.seek(time)
            path = window.map_view.path_geometry[0]
            if time == 1:
                self.assertIs(path, original_path, 'Advancing inside a straight segment should reuse Qt geometry')
            np.testing.assert_allclose((path.elementAt(0).y - .5, path.elementAt(0).x - .5),
                                       paths.positions(time)[0, :2])
            np.testing.assert_allclose((path.currentPosition().y() - .5,
                                       path.currentPosition().x() - .5), target)
            self.assertEqual(path.elementCount(), 2)
            arrow = window.map_view.task_sequence_targets[0]
            np.testing.assert_allclose((arrow.y() - .5, arrow.x() - .5), target)
            self.assertTrue(window.map_view.task_sequence_geometry[0].isEmpty())
        window.playback.seek(6)
        self.assertFalse(window.map_view.path_geometry)
        self.assertFalse(window.map_view.task_sequence_targets)
        window.playback.seek(1)
        self.assertIn(0, window.map_view.path_geometry)

    def test_visual_settings_live_changes_survive_reopen_and_reload(self):
        window = self.window
        dialog = window.visual_settings
        self.assertFalse(dialog.isVisible())
        window.playback.play()
        window.visual_settings_action.trigger()
        APP.processEvents()
        self.assertTrue(dialog.isVisible())
        self.assertFalse(dialog.isModal())
        self.assertTrue(window.playback.playing)
        window.playback.pause()
        for name, check in dialog.layer_checks.items():
            check.click()
            self.assertEqual(window.map_view.options[name], check.isChecked())
            self.assertEqual(window.layer_actions[name].isChecked(), check.isChecked())
        # API/action changes flow back to the dialog as well as the map.
        window.layer_actions["grid"].setChecked(True)
        self.assertTrue(dialog.layer_checks["grid"].isChecked())
        self.assertTrue(window.map_view.options["grid"])
        selected = {name: check.isChecked() for name, check in dialog.layer_checks.items()}
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        self.assertFalse(dialog.isVisible())
        window.visual_settings_action.trigger()
        self.assertIs(window.visual_settings, dialog)
        window.accept_result(LoadResult(self.plan, AnalyticsIndex(self.plan)))
        self.assertTrue(dialog.isVisible())
        for name, value in selected.items():
            self.assertEqual(dialog.layer_checks[name].isChecked(), value)
            self.assertEqual(window.map_view.options[name], value)
        window.close()
        self.assertFalse(dialog.isVisible())

    def test_visual_settings_task_and_path_controls_update_the_scene(self):
        window = self.window
        plan = replace(self.plan, tasks=(
            Task(0, 0, ((1, 2), (3, 4)), ((0, 0),), ()),
            Task(1, 0, ((5, 6),), (), ()),
            Task(2, 100, ((7, 8),), (), ()),
        ), events=())
        window.accept_result(LoadResult(plan, AnalyticsIndex(plan)))
        window.playback.seek(5)
        window.show_visual_settings()
        dialog = window.visual_settings
        for mode, expected in (("next", 1), ("assigned", 2), ("all", 3), ("none", 0)):
            dialog.task_mode.setCurrentIndex(dialog.task_mode.findData(mode))
            self.assertEqual(len(window.map_view.tasks), expected)
        window.select_agent(0)
        self.assertIn(0, window.map_view.path_geometry)
        dialog.show_paths.click()
        self.assertFalse(window.map_view.path_geometry)
        dialog.show_paths.click()
        self.assertIn(0, window.map_view.path_geometry)
        dialog.task_mode.setCurrentIndex(dialog.task_mode.findData("all"))
        self.assertEqual(len(window.map_view.tasks), 2)
        dialog.planned.click()
        np.testing.assert_array_equal(window.map_view.positions, plan.paths.positions(5, planned=True))
        dialog.close()
        window.show_visual_settings()
        self.assertTrue(dialog.planned.isChecked())
        self.assertTrue(dialog.show_paths.isChecked())
        self.assertEqual(dialog.task_mode.currentData(), "all")

    def test_visual_settings_keyboard_input_does_not_trigger_playback(self):
        window = self.window
        window.show_visual_settings()
        APP.processEvents()
        dialog = window.visual_settings
        check = dialog.layer_checks["grid"]
        before = check.isChecked()
        check.setFocus()
        QTest.keyClick(check, Qt.Key.Key_Space)
        self.assertEqual(check.isChecked(), not before)
        self.assertFalse(window.playback.playing)
        dialog.task_mode.setFocus()
        QTest.keyClick(dialog.task_mode, Qt.Key.Key_Down)
        self.assertEqual(dialog.task_mode.currentData(), "all")
        QTest.keyClick(dialog.task_mode, Qt.Key.Key_Left)
        self.assertEqual(window.playback.time, 0)
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        APP.processEvents()
        self.assertFalse(dialog.isVisible())
        QTest.keyClick(window.map_view, Qt.Key.Key_Space)
        self.assertTrue(window.playback.playing)

    def test_agent_indices_checkbox_changes_fit_map_pixels(self):
        window = self.window
        self.assertLess(window.map_view.current_scale, 24)
        window.show_visual_settings()
        APP.processEvents()
        check = window.visual_settings.layer_checks["agent_ids"]
        check.setChecked(False)
        without_ids = window.map_view.viewport().grab().toImage()
        check.setFocus()
        QTest.keyClick(check, Qt.Key.Key_Space)
        self.assertTrue(check.isChecked())
        with_ids = window.map_view.viewport().grab().toImage()
        self.assertNotEqual(with_ids, without_ids)
        QTest.keyClick(check, Qt.Key.Key_Space)
        self.assertEqual(window.map_view.viewport().grab().toImage(), without_ids)

    def test_entered_out_of_range_time_is_visibly_clamped(self):
        window = self.window
        window.time_edit.setFocus()
        window.time_edit.setText("999999")
        window._time_entered()
        self.assertEqual(window.time_edit.text(), str(window.playback.end))

    def test_cancelled_close_drains_without_destroying_live_workers(self):
        window = self.window
        with patch("planviz_qt.io.loader.load_plan") as mock_load:
            def delayed(*args, **kwargs):
                for _ in range(100):
                    if kwargs["cancelled"]():
                        raise InterruptedError("Cancelled")
                    time.sleep(.005)
                return self.plan
            mock_load.side_effect = delayed
            window.load(request())
            QTest.qWait(20)
            window.close()
            wait_for(lambda: not window.loader.pending)
            wait_for(lambda: not window.isVisible())
            self.assertFalse(window.playback.playing)


class LoadTests(unittest.TestCase):
    def test_actual_async_load_and_stale_signal_rejection(self):
        manager = LoadManager()
        loaded = QSignalSpy(manager.loaded)
        failures = QSignalSpy(manager.failed)
        manager.load(request("warehouse_small_2024.json"))
        old_generation = manager._generation
        manager.load(request("warehouse_small_2026.json"))
        manager._loaded(old_generation, "stale")
        wait_for(lambda: not manager.pending)
        self.assertEqual(failures.count(), 0)
        self.assertEqual(loaded.count(), 1)
        self.assertEqual(loaded.at(0)[0].plan.version, "2026 LoRR")

    def test_heatmap_aggregation_and_unique_overlay_labels(self):
        from planviz_qt.io.overlays import Overlay
        manager = LoadManager()
        loaded = QSignalSpy(manager.loaded)
        failed = QSignalSpy(manager.failed)
        original = request("warehouse_small_2024.json")
        requested = LoadRequest(original.map_path, original.plan_path,
                                overlays=(("heatmap", "one"), ("heatmap", "two")))
        def fake_overlay(path, kind, map_data, **kwargs):
            return Overlay("duplicate", kind, np.ones(map_data.grid.shape))
        with patch("planviz_qt.io.overlays.load_overlay", side_effect=fake_overlay):
            manager.load(requested)
            wait_for(lambda: not manager.pending)
        self.assertEqual(failed.count(), 0)
        overlays = loaded.at(0)[0].overlays
        self.assertEqual([item.name for item in overlays], ["Combined heatmap", "duplicate", "duplicate (2)"])
        self.assertTrue(np.all(overlays[0].values[np.isfinite(overlays[0].values)] == 2))


if __name__ == "__main__":
    unittest.main()
