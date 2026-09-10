"""Offscreen integration checks for scene bounds, batching, LOD and interaction."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace
from pathlib import Path
from copy import deepcopy
import json
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from planviz_qt.ui.map_view import MapView
from planviz_qt.ui.minimap import MiniMap
from planviz_qt.palette import load_palette


ROOT = Path(__file__).resolve().parents[1]


def plan(width=80, height=50, count=10):
    grid = np.ones((height, width), dtype=np.uint8)
    grid[0, :] = 0
    starts = np.column_stack((np.arange(count) % height, np.arange(count) % width, np.arange(count) % 4))
    return SimpleNamespace(map=SimpleNamespace(grid=grid, width=width, height=height),
                           paths=SimpleNamespace(starts=starts))


def marker(task_id, stop_index=0, *, row=2, col=2, kind="task", state="assigned", release_time=0):
    return dict(row=row, col=col, label=f"{task_id}:{stop_index}", task_id=task_id,
                stop_index=stop_index, kind=kind, state=state, release_time=release_time)


class SceneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.view = MapView()
        self.view.resize(640, 480)
        self.view.show()  # Offscreen platform: no desktop window is opened.
        self.app.processEvents()

    def tearDown(self):
        self.view.close()
        self.view.deleteLater()
        self.app.processEvents()

    def test_selection_pulse_is_transient_and_only_restarts_for_new_agents(self):
        self.view.set_plan(plan())
        before = self.view.positions.copy()
        self.view.set_selected_agents({0})
        self.assertEqual(self.view._pulse_agents, {0})
        animation = self.view._selection_pulse
        animation.setCurrentTime(150)
        self.view.set_selected_agents({0})
        self.assertEqual(animation.currentTime(), 150)
        self.assertGreater(self.view._pulse_progress, 0)
        self.view.set_selected_agents({0, 1})
        self.assertEqual(self.view._pulse_agents, {1})
        self.assertEqual(animation.currentTime(), 0)
        animation.setCurrentTime(animation.duration())
        self.assertFalse(self.view._pulse_agents)
        self.assertEqual(self.view.selected_agents, {0, 1})
        np.testing.assert_array_equal(self.view.positions, before)
        self.view.set_selected_agents({2})
        self.view.set_selected_agents(set())
        self.assertFalse(self.view._pulse_agents)
        self.assertEqual(animation.state(), animation.State.Stopped)
        self.view.set_selected_agents({2})
        self.view.set_plan(plan(count=1))
        self.assertFalse(self.view._pulse_agents)
        self.assertEqual(animation.state(), animation.State.Stopped)

    def test_agent_label_rasters_match_fresh_render_after_zoom_color_and_dpr_changes(self):
        self.view.set_plan(plan(count=30))
        self.view.set_options(agent_ids=True)

        def render(dpr):
            size = self.view.viewport().size()
            image = QImage(size.width()*dpr, size.height()*dpr, QImage.Format.Format_ARGB32)
            image.setDevicePixelRatio(dpr)
            image.fill(QColor('white'))
            painter = QPainter(image)
            self.view.render(painter, QRectF(0, 0, size.width(), size.height()), self.view.viewport().rect())
            painter.end()
            return image

        render(1)
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'labels.yaml'
            source.write_text('agent:\n  index: "#aa0088"\n')
            self.view.set_palette(load_palette(source))
            for dpr, zoom in ((1, 1), (2, 1), (2, 2), (1, .5)):
                self.view.scale(zoom, zoom)
                cached = render(dpr)
                self.view._layer._agent_rasters.clear()
                self.assertEqual(cached, render(dpr))
        self.view._layer._agent_rasters.clear()
        self.view._layer._agent_rasters.max_bytes = 0
        fallback = render(1)
        self.view.set_options(agent_ids=False)
        self.assertNotEqual(fallback, render(1), 'Exhausted raster cache must not hide labels')

    def render_view(self):
        # Keep paint pixels aligned with mapFromScene's viewport coordinates.
        image = QImage(self.view.viewport().size(), QImage.Format.Format_ARGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        self.view.render(painter, QRectF(image.rect()), self.view.viewport().rect())
        painter.end()
        return image

    def test_large_map_and_agents_are_constant_scene_item_count(self):
        self.view.set_plan(plan(1000, 1000, 10000))
        self.assertEqual(len(self.view.scene().items()), 2)
        self.assertEqual(self.view.map_image.size().width(), 1000)
        self.assertEqual(self.view.world_rect.width(), 1000)
        self.view.zoom_at(self.view.viewport().rect().center(), 20)
        self.view.center_agent(25)
        self.render_view()
        self.assertLess(self.view._layer.last_painted_agents, 10000)
        self.assertGreater(self.view._layer.last_painted_agents, 0)

    def test_zoom_preserves_world_data_and_cursor_anchor(self):
        self.view.set_plan(plan(300, 200))
        self.view.zoom_at(self.view.viewport().rect().center(), 3)
        anchor = self.view.viewport().rect().center()
        anchor.setX(anchor.x() + 40)
        before = self.view.mapToScene(anchor)
        positions = self.view.positions.copy()
        self.view.zoom_at(anchor, 1.7)
        after = self.view.mapToScene(anchor)
        self.assertLess(abs(before.x() - after.x()), 2 / self.view.current_scale)
        self.assertLess(abs(before.y() - after.y()), 2 / self.view.current_scale)
        np.testing.assert_array_equal(self.view.positions, positions)

    def test_finite_hit_testing_and_click_signals(self):
        self.view.set_plan(plan())
        positions = np.array([[5, 5, 0], [np.nan, np.nan, 0], [8, 8, 3]])
        self.view.set_frame(positions, 3)
        self.assertEqual(self.view.agent_at(QPointF(5.5, 5.5)), 0)
        selected = QSignalSpy(self.view.agentSelected)
        clicked = QSignalSpy(self.view.locationSelected)
        QTest.mouseClick(self.view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier,
                         self.view.mapFromScene(QPointF(5.5, 5.5)))
        self.assertEqual(selected.at(0), [0, True])
        QTest.mouseClick(self.view.viewport(), Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier,
                         self.view.mapFromScene(QPointF(20.5, 20.5)))
        self.assertEqual(selected.at(1), [-1, False])
        self.assertEqual(clicked.count(), 0)
        QTest.mouseClick(self.view.viewport(), Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier,
                         self.view.mapFromScene(QPointF(5.5, 5.5)))
        self.assertEqual(selected.at(2), [0, False])
        self.assertEqual(clicked.count(), 0)
        QTest.mouseClick(self.view.viewport(), Qt.MouseButton.RightButton, Qt.KeyboardModifier.ControlModifier,
                         self.view.mapFromScene(QPointF(5.5, 5.5)))
        self.assertEqual(clicked.at(0), [5, 5])
        self.assertEqual(selected.count(), 3)
        QTest.mouseClick(self.view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         self.view.mapFromScene(QPointF(20.5, 20.5)))
        self.assertEqual(clicked.at(1), [20, 20])

    def test_hover_label_toggle_keeps_coordinate_signal_and_scene_batching(self):
        hovered = QSignalSpy(self.view.hovered)
        QTest.mouseMove(self.view.viewport(), self.view.viewport().rect().center())
        self.assertEqual(self.view.hovered_cell, (-1, -1))
        self.assertEqual(hovered.at(hovered.count() - 1), [-1, -1])
        self.view.set_plan(plan(1000, 1000, 10000))
        point = self.view.mapFromScene(QPointF(500.5, 500.5))
        QTest.mouseMove(self.view.viewport(), point)
        expected = self.view.mapToScene(point)
        cell = (int(expected.y()), int(expected.x()))
        self.assertEqual(self.view.hovered_cell, cell)
        self.assertEqual(hovered.at(hovered.count() - 1), list(cell))
        self.assertFalse(self.view.options["hover_location"])
        self.assertFalse(self.view._hover_label.isVisible())
        self.view.set_options(hover_location=True)
        self.assertTrue(self.view._hover_label.isVisible())
        self.assertEqual(self.view._hover_label.text(), f"Row {cell[0]} · Col {cell[1]}")
        label_size = self.view._hover_label.size()
        self.view.zoom_at(point, 8)
        self.assertEqual(self.view._hover_label.size(), label_size)
        self.assertTrue(self.view.viewport().rect().contains(self.view._hover_label.geometry()))
        self.assertEqual(len(self.view.scene().items()), 2)
        self.view.set_options(hover_location=False)
        self.assertFalse(self.view._hover_label.isVisible())
        self.assertNotEqual(self.view.hovered_cell, (-1, -1))

    def test_hover_normalizes_map_boundaries_and_clears_on_leave_or_reload(self):
        self.view.set_plan(plan(4, 3, 0))
        self.view.zoom_at(self.view.viewport().rect().center(), .5)
        self.view.set_options(hover_location=True)
        hovered = QSignalSpy(self.view.hovered)
        for col, row, expected in (
            (.5, .5, (0, 0)), (3.5, 2.5, (2, 3)),
            (-.5, .5, (-1, -1)), (4.5, .5, (-1, -1)),
            (.5, -.5, (-1, -1)), (.5, 3.5, (-1, -1)),
        ):
            with self.subTest(col=col, row=row):
                point = self.view.mapFromScene(QPointF(col, row))
                self.assertTrue(self.view.viewport().rect().contains(point))
                QTest.mouseMove(self.view.viewport(), point)
                self.assertEqual(self.view.hovered_cell, expected)
                self.assertEqual(hovered.at(hovered.count() - 1), list(expected))
                self.assertEqual(self.view._hover_label.isVisible(), expected != (-1, -1))
        QTest.mouseMove(self.view.viewport(), self.view.mapFromScene(QPointF(.5, .5)))
        QApplication.sendEvent(self.view.viewport(), QEvent(QEvent.Type.Leave))
        self.assertEqual(self.view.hovered_cell, (-1, -1))
        self.assertEqual(hovered.at(hovered.count() - 1), [-1, -1])
        self.assertFalse(self.view._hover_label.isVisible())
        QTest.mouseMove(self.view.viewport(), self.view.mapFromScene(QPointF(1.5, 1.5)))
        self.assertTrue(self.view._hover_label.isVisible())
        self.view.set_plan(plan(2, 2, 0))
        self.assertEqual(self.view.hovered_cell, (-1, -1))
        self.assertEqual(hovered.at(hovered.count() - 1), [-1, -1])
        self.assertFalse(self.view._hover_label.isVisible())
        self.assertTrue(self.view.options["hover_location"])

    def test_task_sequence_connection_follows_fractional_agent_frame(self):
        from planviz_qt.ui import map_view
        self.view.set_plan(plan(20, 15, 1))
        self.view.set_task_sequences({0: np.array([[0, 0], [3, 4], [5, 6]])})
        self.view.set_frame(np.array([[.3, .7, 0]]), .3)
        with patch.object(map_view, "_arrow_segment", wraps=map_view._arrow_segment) as arrow:
            self.render_view()
        calls = [(call.args[1], call.args[2]) for call in arrow.call_args_list]
        self.assertIn((QPointF(1.2, .8), QPointF(4.5, 3.5)), calls)

    def test_coincident_agents_remain_filled_at_collision(self):
        self.view.set_plan(plan(10, 10, 2))
        self.view.set_frame([[2, 2, -1], [2, 2, -1]], 2)
        image = QImage(400, 400, QImage.Format.Format_ARGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        self.view.scene().render(painter, QRectF(0, 0, 400, 400), self.view.world_rect)
        painter.end()
        self.assertEqual(image.pixelColor(100, 100), QColor("#00bfff"))

    def test_translucent_agent_overlap_keeps_single_group_blend(self):
        self.view.set_plan(plan(10, 10, 2))
        colors = [QColor(0, 191, 255, 100)] * 2
        self.view.set_frame([[2, 2, -1], [5, 5, -1]], 0, colors=colors)
        separated = self.render_view()
        self.view.set_frame([[2, 2, -1], [2, 2, -1]], 1, colors=colors)
        coincident = self.render_view()
        center = self.view.mapFromScene(QPointF(2.5, 2.5))
        self.assertEqual(separated.pixelColor(center), coincident.pixelColor(center))

    def test_start_cache_matches_direct_pixels_at_export_sizes_and_dpr(self):
        source = plan(20, 15, 0)
        source.paths.starts = np.array([[2, 2, -1], [2, 2, -1], [2.25, 2.5, -1],
                                        [8, 9, -1], [8, 15, -1]])
        self.view.set_plan(source)
        self.view.set_options(starts=True, headings=False)
        self.view.set_frame([], 0)  # Expose starts without bodies covering them.

        def render(width, height, dpr):
            image = QImage(width * dpr, height * dpr, QImage.Format.Format_ARGB32)
            image.setDevicePixelRatio(dpr)
            image.fill(QColor("white"))
            painter = QPainter(image)
            self.view.render(painter, QRectF(0, 0, width, height), self.view.viewport().rect())
            painter.end()
            return image

        layer = self.view._layer
        with patch.object(layer, "_draw_starts", wraps=layer._draw_starts) as rasterize:
            for index, (width, height, dpr) in enumerate(((640, 480, 1), (640, 480, 2),
                                                        (835, 627, 1), (835, 627, 2)), 1):
                with self.subTest(width=width, height=height, dpr=dpr):
                    cached = render(width, height, dpr)
                    self.assertEqual(rasterize.call_count, index)
                    self.assertLessEqual(layer._start_cache.width(), cached.width() + 8 * dpr)
                    self.assertLessEqual(layer._start_cache.height(), cached.height() + 8 * dpr)
                    # Compare against the original vector fill and outline,
                    # bypassing the cache while retaining all scene transforms.
                    with patch.object(layer, "_paint_starts", side_effect=rasterize._mock_wraps):
                        direct = render(width, height, dpr)
                    before = np.frombuffer(direct.constBits(), np.uint8).reshape(-1, 4).astype(np.int16)
                    after = np.frombuffer(cached.constBits(), np.uint8).reshape(-1, 4).astype(np.int16)
                    delta = np.abs(before - after)
                    # A premultiplied transparent intermediate adds integer
                    # rounding to antialiased fill/outline compositing. Permit
                    # only tiny channel differences on a small edge-pixel set.
                    self.assertLessEqual(int(delta.max()), 3)
                    self.assertLess(np.count_nonzero(np.any(delta, axis=1)) / len(delta), .005)

    def test_coincident_start_markers_keep_single_translucent_fill(self):
        images = []
        for count in (1, 4):
            source = plan(10, 10, 0)
            source.paths.starts = np.tile([2, 2, -1], (count, 1))
            self.view.set_plan(source)
            self.view.set_options(starts=True, headings=False)
            self.view.set_frame([], 0)
            images.append(self.render_view())
        center = self.view.mapFromScene(QPointF(2.5, 2.5))
        self.assertEqual(images[0].pixelColor(center), images[1].pixelColor(center))
        self.assertNotEqual(images[0].pixelColor(center), QColor("#f7f8fa"))
        self.assertNotEqual(images[0].pixelColor(center), QColor("#7b8491"))

    def test_start_raster_is_reused_during_movement_and_visibility_toggles(self):
        source = plan(20, 15, 0)
        source.paths.starts = np.array([[2, 2, -1], [4, 7, -1]])
        self.view.set_plan(source)
        self.view.set_options(starts=True, headings=False)
        layer = self.view._layer
        with patch.object(layer, "_draw_starts", wraps=layer._draw_starts) as rasterize:
            frames = []
            for tick in range(4):
                self.view.set_frame(source.paths.starts + [5, tick, 0], tick)
                frames.append(self.render_view())
            self.assertEqual(rasterize.call_count, 1)
            self.assertNotEqual(frames[0], frames[-1])
            self.view.set_options(starts=False)
            hidden = self.render_view()
            self.assertNotEqual(hidden, frames[-1])
            self.view.set_options(starts=True)
            self.assertEqual(self.render_view(), frames[-1])
            self.assertEqual(rasterize.call_count, 1)

    def test_start_cache_invalidates_camera_changes_and_same_size_plan_reload(self):
        source = plan(100, 80, 0)
        source.paths.starts = np.array([[20, 20, -1], [40, 40, -1], [60, 70, -1]])
        self.view.set_plan(source)
        self.view.set_frame([], 0)
        self.view.set_options(starts=True, headings=False)
        layer = self.view._layer
        with patch.object(layer, "_draw_starts", wraps=layer._draw_starts) as rasterize:
            self.render_view()
            for change in (
                lambda: self.view.zoom_at(self.view.viewport().rect().center(), 2),
                lambda: self.view.center_world(30, 30),
                lambda: self.view.resize(800, 530),
            ):
                previous = rasterize.call_count
                change()
                self.render_view()
                self.assertGreater(rasterize.call_count, previous)
            self.view.fit_map()
            before = self.render_view()
            transform = self.view.transform()
            previous = rasterize.call_count
            replacement = plan(100, 80, 0)
            replacement.paths.starts = source.paths.starts + [2, 3, 0]
            self.view.set_plan(replacement)
            self.view.set_frame([], 0)
            self.assertEqual(self.view.transform(), transform)
            self.assertTrue(layer._start_cache.isNull())
            self.assertNotEqual(self.render_view(), before)
            self.assertGreater(rasterize.call_count, previous)

    def test_task_batch_preserves_overlap_order_and_changed_markers(self):
        self.view.set_plan(plan(10, 10, 0))
        markers = [dict(row=2, col=2, color=color) for color in ("red", "blue", "red")]
        self.view.set_tasks(markers)
        center = self.view.mapFromScene(QPointF(2.5, 2.5))
        first = self.render_view()
        self.assertEqual(first.pixelColor(center), QColor("red"))
        self.assertEqual(self.render_view(), first)
        markers[-1]["color"] = "green"
        self.view.set_tasks(markers)
        self.assertEqual(self.render_view().pixelColor(center), QColor("green"))
        markers[-1].update(row=3, col=3)
        self.view.set_tasks(markers)
        moved = self.render_view()
        self.assertEqual(moved.pixelColor(center), QColor("blue"))
        self.assertEqual(moved.pixelColor(self.view.mapFromScene(QPointF(3.5, 3.5))), QColor("green"))
        self.view.set_tasks([])
        self.assertEqual(self.render_view().pixelColor(center), QColor("#f7f8fa"))

    def test_semantic_task_square_errand_diamond_and_agent_circle(self):
        self.view.set_plan(plan(10, 10, 1))
        self.view.set_frame([[5, 2, -1]], 0)
        self.view.set_tasks([marker(1), marker(2, col=5, kind="errand")])
        image = self.render_view()

        def color(row, col):
            return image.pixelColor(self.view.mapFromScene(QPointF(col, row)))

        self.assertEqual(color(2.5, 2.5), QColor(self.view.palette.color("task", "assigned")))
        self.assertEqual(color(2.5, 5.5), QColor(self.view.palette.color("errand", "assigned")))
        self.assertEqual(color(2.17, 2.17), QColor(self.view.palette.color("task", "assigned")))
        self.assertEqual(color(2.17, 5.17), QColor("#f7f8fa"))
        self.assertEqual(color(5.5, 2.5), QColor(self.view.palette.color("agent", "idle")))
        self.assertEqual(color(5.17, 2.17), QColor("#f7f8fa"))
        polygon = self.view.tasks[1]["geometry"]
        self.view.set_frame([[5, 3, -1]], 1)
        self.view.set_tasks([marker(1), marker(2, col=5, kind="errand")])
        self.assertIs(self.view.tasks[1]["geometry"], polygon)
        self.assertEqual(len(self.view.scene().items()), 2)

    def test_latest_task_at_location_uses_release_then_id_then_stop_without_mutation(self):
        self.view.set_plan(plan(10, 10, 0))
        markers = [marker(100, release_time=1), marker(9, release_time=2),
                   marker(3, release_time=3)]
        original = deepcopy(markers)
        self.view.set_tasks(markers)
        first = self.render_view()
        self.assertEqual(len(self.view.tasks), 1)
        self.assertEqual(self.view.tasks[0]["task_id"], 3)
        self.assertEqual(self.view.tasks[0]["label"], "3:0*")
        self.assertEqual(self.view.tasks[0]["overlapping_task_ids"], (3, 9, 100))
        self.view.set_tasks(list(reversed(markers)))
        self.assertEqual(self.view.tasks[0]["task_id"], 3)
        self.assertEqual(self.render_view(), first)
        self.assertEqual(markers, original)
        # When release times match, task ID wins even if the input order differs.
        self.view.set_tasks([marker(9, release_time=3), marker(3, release_time=3)])
        self.assertEqual(self.view.tasks[0]["label"], "9:0*")
        # Repeated stops belonging to one task are not multiple task IDs.
        self.view.set_tasks([marker(9, 4, kind="task"), marker(9, 1, kind="errand")])
        self.assertEqual(self.view.tasks[0]["label"], "9:4")
        self.assertEqual(self.view.tasks[0]["shape"], "square")
        self.assertEqual(self.view.tasks[0]["overlap_count"], 1)

    def test_semantic_grid_markers_batch_across_alternating_shapes(self):
        self.view.set_plan(plan(40, 30, 0))
        self.view.set_tasks([marker(index, row=2 + index // 20, col=index % 20,
                                    kind="task" if index % 2 else "errand") for index in range(200)])
        self.render_view()
        self.assertEqual(len(self.view.tasks), 200)
        self.assertEqual(len(self.view._layer._task_batches), 2)
        batches = self.view._layer._task_batches
        self.render_view()
        self.assertIs(self.view._layer._task_batches, batches)

    def test_marker_filters_restore_older_task_and_remove_overlap_indicator(self):
        self.view.set_plan(plan(10, 10, 0))
        older = marker(2, kind="errand", release_time=1)
        latest = marker(7, state="finished", release_time=5)
        self.view.set_tasks([latest, older])
        self.assertEqual(self.view.tasks[0]["label"], "7:0*")
        self.assertEqual(self.view.tasks[0]["brush"].color(), QColor(self.view.palette.color("task", "completed")))
        self.view.set_tasks([older])
        self.assertEqual(self.view.tasks[0]["label"], "2:0")
        self.assertEqual(self.view.tasks[0]["shape"], "diamond")
        self.assertEqual(self.view.tasks[0]["overlapping_task_ids"], (2,))
        self.view.set_tasks([])
        self.assertEqual(self.view.tasks, [])
        self.view.set_tasks([older, latest])
        self.assertEqual(self.view.tasks[0]["label"], "7:0*")
        self.assertEqual(older["label"], "2:0")
        self.assertEqual(latest["label"], "7:0")

    def test_task_index_and_overlap_suffix_are_readable_below_previous_zoom_cutoff(self):
        self.view.set_plan(plan(160, 100, 0))
        markers = [marker(1, row=30, col=30), marker(99999, 2, row=30, col=30)]
        self.view.set_tasks(markers)
        self.assertLess(self.view.current_scale, 22)
        without = self.render_view()
        self.view.set_options(task_ids=True)
        labelled = self.render_view()
        self.assertNotEqual(labelled, without)
        layout = self.view._layer._task_labels["99999:2*"]
        self.assertGreater(layout[1] * 2, self.view.current_scale)
        self.assertEqual(self.render_view(), labelled)
        self.assertIs(self.view._layer._task_labels["99999:2*"], layout)
        self.view.set_tasks(markers[:1])
        self.render_view()
        self.assertEqual(set(self.view._layer._task_labels), {"1:0"})

    def test_palette_recolors_shapes_and_invalidates_start_and_task_caches(self):
        custom = {"agent": {"idle": "#008800", "start_fill": "#ff0000", "start_outline": "#00ff00",
                            "selected_outline": "#3300ff", "collision_outline": "#ff00ff"},
                  "task": {"assigned": "#0088ff"}, "errand": {"assigned": "#aa4400"}}
        with tempfile.TemporaryDirectory() as folder:
            palette_path = Path(folder) / "custom.yaml"
            palette_path.write_text(json.dumps(custom))
            palette = load_palette(palette_path)
        source = plan(20, 15, 0)
        source.paths.starts = np.array([[2, 2, -1], [2, 5, -1]])
        self.view.set_plan(source)
        self.view.set_frame([[6, 2, -1], [6, 5, -1]], 1)
        self.view.set_options(starts=True, headings=False, collisions=True)
        self.view.set_selected_agents({0})
        self.view.set_conflict_agents({1})
        self.view.set_tasks([marker(1, row=9), marker(2, row=9, col=5, kind="errand"),
                             dict(row=9, col=8, color="#123456")])
        layer = self.view._layer
        with patch.object(layer, "_draw_starts", wraps=layer._draw_starts) as rasterize:
            before = self.render_view()
            self.assertEqual(rasterize.call_count, 1)
            self.assertEqual(self.render_view(), before)
            old_brush = self.view.tasks[0]["brush"]
            self.view.set_palette(palette)
            self.assertTrue(layer._start_cache.isNull())
            after = self.render_view()
            self.assertEqual(rasterize.call_count, 2)
            self.assertNotEqual(after, before)
            self.assertEqual(self.render_view(), after)
            self.assertEqual(rasterize.call_count, 2)
            self.assertIsNot(self.view.tasks[0]["brush"], old_brush)
        for row, col, color in ((6.5, 2.5, "#008800"), (9.5, 2.5, "#0088ff"),
                                (9.5, 5.5, "#aa4400"), (9.5, 8.5, "#123456")):
            self.assertEqual(after.pixelColor(self.view.mapFromScene(QPointF(col, row))), QColor(color))
        start = self.view.mapFromScene(QPointF(2.5, 2.5))
        self.assertGreater(after.pixelColor(start).red(), before.pixelColor(start).red())
        self.assertLess(after.pixelColor(start).green(), before.pixelColor(start).green())
        converted = after.convertToFormat(QImage.Format.Format_RGBA8888)
        pixels = np.frombuffer(converted.constBits(), np.uint8).reshape(-1, 4)
        for color in ("#3300ff", "#ff00ff", "#00ff00"):
            expected = QColor(color)
            self.assertTrue(np.any(np.all(pixels[:, :3] == [expected.red(), expected.green(), expected.blue()], axis=1)))
        # Explicit colors remain owned by the caller, while absent dict keys
        # follow the palette's default idle color on subsequent live changes.
        self.view.set_frame([[6, 2, -1], [6, 5, -1]], 2, colors={0: "#112233"})
        self.view.set_palette(load_palette())
        self.assertEqual(QColor(self.view.colors[0]), QColor("#112233"))
        self.assertEqual(QColor(self.view.colors[1]), QColor(self.view.palette.color("agent", "idle")))

    def test_frame_layers_overlay_and_plan_replacement(self):
        self.view.set_plan(plan())
        self.view.set_options(grid=True, starts=True, agent_ids=True, task_ids=True)
        self.view.set_selected_agents({2})
        self.view.set_collision_agents({3})
        self.view.set_paths({2: np.array([[2, 2, 0], [3, 2, 0], [4, 2, 0]])})
        self.view.set_tasks([dict(row=5, col=4, label="T1", color="orange")])
        self.view.set_task_sequences({2: np.array([[2, 2], [3, 2], [4, 2]])})
        self.view.set_overlay("heatmap", np.ones((50, 80)))
        self.assertEqual(len(self.view.scene().items()), 3)
        self.view.zoom_at(self.view.viewport().rect().center(), 6)
        self.render_view()
        self.view.set_plan(plan(100, 70))
        self.assertEqual(len(self.view.scene().items()), 2)
        self.assertEqual(self.view.overlays, {})
        self.assertEqual(self.view.path_geometry, {})
        self.assertEqual(self.view.selected_agents, set())

    def test_overlay_models_highway_and_layer_toggles(self):
        self.view.set_plan(plan())
        overlay = SimpleNamespace(kind="heuristic", values=np.ones((50, 80)), segments=(), colormap="Greys")
        self.view.set_overlay("heuristic", overlay, visible=False)
        self.assertFalse(self.view.overlays["heuristic"].isVisible())
        self.view.set_overlay_visible("heuristic", True)
        self.assertTrue(self.view.overlays["heuristic"].isVisible())
        highway = SimpleNamespace(kind="highway", values=None, segments=((2, 2, 3, 2), (3, 2, 3, 3)), colormap="Reds")
        self.view.set_overlay("highway", highway)
        self.assertEqual(len(self.view.scene().items()), 4)
        self.view.set_conflict_agents({3})
        self.view.set_options(collisions=False)
        self.render_view()
        self.view.set_overlay("highway", None)
        self.assertEqual(len(self.view.scene().items()), 3)

    def test_minimap_is_bounded_raster_and_maps_clicks(self):
        self.view.set_plan(plan(1000, 500))
        minimap = MiniMap(self.view)
        minimap.resize(240, 150)
        self.assertLessEqual(minimap._thumbnail.width(), 512)
        self.assertLessEqual(minimap._thumbnail.height(), 512)
        self.view.zoom_at(self.view.viewport().rect().center(), 5)
        rect = minimap.image_rect()
        minimap._center_at(QPointF(rect.left() + rect.width() * .7, rect.top() + rect.height() * .6))
        visible = self.view.visible_scene_rect()
        self.assertAlmostEqual(visible.center().x(), 700, delta=2)
        self.assertAlmostEqual(visible.center().y(), 300, delta=2)
        self.assertLess(minimap.viewport_rect().width(), rect.width())
        minimap.set_view(None)
        minimap.close()

    def test_task_ids_are_independent_from_agent_ids(self):
        self.view.set_plan(plan(12, 8, 1))
        self.view.set_tasks([dict(row=3, col=4, label="42:1", color="orange")])
        self.view.set_options(agent_ids=False, task_ids=False)
        without_labels = self.render_view()
        self.view.set_options(task_ids=True)
        with_task_labels = self.render_view()
        self.assertNotEqual(without_labels, with_task_labels)
        self.view.set_options(task_ids=False, agent_ids=True)
        with_agent_labels = self.render_view()
        self.assertNotEqual(without_labels, with_agent_labels)
        self.assertNotEqual(with_task_labels, with_agent_labels)

    def test_long_agent_index_is_not_clipped_to_a_small_cell(self):
        self.view.set_plan(plan(80, 50, 0))
        positions = np.full((10001, 3), np.nan)
        positions[10000] = (20, 30, -1)
        self.view.set_frame(positions, 0)
        self.assertLess(self.view.current_scale, 10)
        label_widths = []
        for _ in range(2):
            self.view.set_options(agent_ids=False)
            without = self.render_view()
            self.view.set_options(agent_ids=True)
            with_ids = self.render_view()
            before = np.frombuffer(without.constBits(), dtype=np.uint8).reshape(without.height(), without.width(), 4)
            after = np.frombuffer(with_ids.constBits(), dtype=np.uint8).reshape(with_ids.height(), with_ids.width(), 4)
            ys, xs = np.nonzero(np.any(before != after, axis=2))
            self.assertGreater(len(xs), 0)
            label_widths.append(int(xs.max() - xs.min() + 1))
            self.assertGreater(label_widths[-1], self.view.current_scale * 2)
            self.assertGreater(ys.max() - ys.min(), 3)
            self.view.zoom_at(self.view.mapFromScene(QPointF(30.5, 20.5)), .5)
        self.assertAlmostEqual(*label_widths, delta=1)
        self.assertEqual(len(self.view.scene().items()), 2)

    def test_task_cache_reuses_brushes_but_applies_changed_state_and_geometry(self):
        self.view.set_plan(plan(12, 8, 1))
        markers = [dict(row=3, col=4, label="42:1", color="orange"),
                   dict(row=4, col=5, label="42:2", color="orange")]
        self.view.set_tasks(markers)
        self.assertIs(self.view.tasks[0]["brush"], self.view.tasks[1]["brush"])
        unchanged_positions = self.view.task_positions
        self.view.set_tasks(markers)
        self.assertIs(self.view.task_positions, unchanged_positions)
        markers[0].update(row=2, color="grey")
        self.view.set_tasks(markers)
        self.assertEqual(self.view.tasks[0]["brush"].color(), QColor("grey"))
        np.testing.assert_allclose(self.view.task_positions, [[2, 4], [4, 5]])
        self.view.set_tasks([])
        self.assertEqual(len(self.view.task_positions), 0)
        self.assertEqual(len(self.view._task_visual_cache), 0)

    def test_heuristic_overlay_keeps_zero_and_normalizes_finite_range(self):
        self.view.set_plan(plan(3, 2, 0))
        values = np.array([[0., 5., 10.], [np.nan, 3., 8.]])
        overlay = SimpleNamespace(kind="heuristic", values=values, segments=(), colormap="Greys")
        self.view.set_overlay("heuristic", overlay)
        image = self.view.overlays["heuristic"].pixmap().toImage()
        self.assertGreater(image.pixelColor(0, 0).alpha(), 0)
        self.assertEqual(image.pixelColor(0, 1).alpha(), 0)
        self.assertGreater(image.pixelColor(0, 0).red(), image.pixelColor(2, 0).red())
        overlay.values = values + 100
        self.view.set_overlay("heuristic", overlay)
        shifted = self.view.overlays["heuristic"].pixmap().toImage()
        self.assertEqual(image, shifted)
        self.view.set_overlay("heatmap", values)
        self.assertEqual(self.view.overlays["heatmap"].pixmap().toImage().pixelColor(0, 0).alpha(), 0)

    def test_warehouse_fixture_visual_review_artifact(self):
        """A repeatable visual QA artifact, with explicit renderer status samples."""
        from planviz_qt.io.loader import load_plan
        from planviz_qt.domain.analytics import AnalyticsIndex
        fixture = load_plan(ROOT / "example/warehouse_small.map", ROOT / "example/warehouse_small_2024.json")
        index = AnalyticsIndex(fixture)
        self.view.resize(1600, 1000)
        self.app.processEvents()
        self.view.set_plan(fixture)
        at = min(20, fixture.max_time)
        positions = fixture.paths.positions(at)
        colors = np.full(fixture.team_size, "#00bfff", dtype="U7")
        # This screenshot checks colors supplied by the controller; these are
        # renderer samples, not claims about conflict/delay events in this file.
        if len(colors) >= 3:
            colors[1:3] = ("#ffff00", "#32cd32")
        self.view.set_frame(positions, at, colors)
        self.view.set_options(grid=True, agent_ids=True, task_ids=True, headings=True, collisions=True)
        self.view.set_selected_agents({0})
        self.view.set_conflict_agents({2})
        self.view.set_paths({0: fixture.paths.trajectory(0, at, min(at + 50, fixture.max_time))})
        self.view.set_tasks(index.task_markers(at, "assigned", {0}))
        context = index.active_task_context(at, 0)
        if context is not None and context["remaining_stops"]:
            points = np.vstack((positions[0, :2], context["remaining_stops"]))
            self.view.set_task_sequences({0: points})
        self.assertGreaterEqual(self.view.current_scale, 24)
        self.assertTrue(self.view.tasks)
        image = self.render_view()
        destination = Path("/private/tmp/planviz-qt-warehouse-scene.png")
        self.assertTrue(image.save(str(destination)))
        self.assertGreater(destination.stat().st_size, 1000)
        self.assertEqual(self.view._layer.last_painted_agents, fixture.team_size)

    def test_real_iron_fixture_retains_batched_scene(self):
        from planviz_qt.io.loader import load_plan
        fixture = load_plan(ROOT / "example/LoRR2026/maps/scene_mp_2p_01.map",
                            ROOT / "example/LoRR2026/outputs/iron-example_10000_output.json")
        self.view.set_plan(fixture)
        self.assertEqual(fixture.team_size, 10000)
        self.assertEqual(len(self.view.scene().items()), 2)
        colors = np.full(fixture.team_size, "#00bfff", dtype="U7")
        for at in (0, 5, 10):
            self.view.set_frame(fixture.paths.positions(at), at, colors)
            self.render_view()
            self.assertEqual(self.view._layer.last_painted_agents, fixture.team_size)
        self.view.zoom_at(self.view.viewport().rect().center(), 20)
        self.view.center_agent(0)
        self.render_view()
        self.assertGreater(self.view._layer.last_painted_agents, 0)
        self.assertLess(self.view._layer.last_painted_agents, fixture.team_size)


if __name__ == "__main__":
    unittest.main()
