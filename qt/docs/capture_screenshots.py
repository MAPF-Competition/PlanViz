"""Capture the real Qt widgets used by the illustrated README.

Run from the repository root:
    .venv/bin/python qt/docs/capture_screenshots.py

This uses the offscreen Qt platform and Fusion style for consistent, portable
captures. It does not open desktop windows, edit source fixtures, or simulate
results. Screenshots are widget grabs, without an operating-system title bar.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_SCALE_FACTOR"] = "2"
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "planviz-readme-mpl"))
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "qt/src"))

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QFont, QPalette, QColor, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from planviz_qt.application.loading import LoadRequest, LoadResult
from planviz_qt.domain.analytics import AnalyticsIndex
from planviz_qt.io.loader import load_plan
from planviz_qt.io.overlays import load_overlay
from planviz_qt.ui.main_window import MainWindow, OpenPlanDialog


def main():
    app = QApplication([])
    app.setStyle("Fusion")
    app.setFont(QFont("Arial", 11))
    palette = app.style().standardPalette()
    for role, color in ((QPalette.ColorRole.Window, "#f4f5f7"),
                        (QPalette.ColorRole.Base, "#ffffff"),
                        (QPalette.ColorRole.AlternateBase, "#eef1f5"),
                        (QPalette.ColorRole.WindowText, "#172334"),
                        (QPalette.ColorRole.Text, "#172334"),
                        (QPalette.ColorRole.ButtonText, "#172334"),
                        (QPalette.ColorRole.Highlight, "#245b96"),
                        (QPalette.ColorRole.HighlightedText, "#ffffff")):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    output = ROOT / "qt/docs/images"
    output.mkdir(parents=True, exist_ok=True)
    captures, fixtures = [], {}
    windows = []

    with tempfile.TemporaryDirectory(prefix="planviz-readme-",
                                     dir="/tmp" if Path("/tmp").is_dir() else None) as scratch:
        scratch = Path(scratch)

        def window(map_name, plan_name, *, time=0, heatmap=False):
            # Byte-identical temporary copies keep personal checkout paths out
            # of the publicly reusable Solution details screenshot.
            local = []
            for name in (map_name, plan_name):
                source = ROOT / "example" / name
                destination = scratch / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
                fixtures[str(source.relative_to(ROOT))] = hashlib.sha256(source.read_bytes()).hexdigest()
                local.append(destination)
            plan = load_plan(*local)
            index = AnalyticsIndex(plan)
            overlays = [load_overlay(local[1], "heatmap", plan.map)] if heatmap else []
            widget = MainWindow()
            widget.resize(1280, 820)
            widget.menuBar().setNativeMenuBar(False)
            widget.request = LoadRequest("example/" + map_name, "example/" + plan_name)
            widget.accept_result(LoadResult(plan, index, overlays))
            widget.show()
            app.processEvents()
            widget.playback.seek(time)
            widget.map_view.fit_map()
            windows.append(widget)
            return widget

        def capture(widget, name, description, source=None, before_grab=None):
            if source is not None:
                source.map_view._selection_pulse.stop()
                source.map_view._finish_selection_pulse()
            app.processEvents()
            QTest.qWait(80)
            if before_grab is not None:
                before_grab()
            image = widget.grab()
            path = output / (name + ".png")
            if image.isNull() or not image.save(str(path)):
                raise RuntimeError(f"Could not capture {name}")
            captures.append({"image": path.name, "description": description,
                             "pixels": [image.width(), image.height()],
                             "device_pixel_ratio": image.devicePixelRatio(),
                             **({"solution": source.request.plan_path,
                                 "time": source.playback.time} if source is not None else {})})
            print(path.relative_to(ROOT), flush=True)

        w = window("warehouse_small.map", "warehouse_small_2026.json", time=1000)
        capture(w, "overview", "Warehouse replay, Inspector and timeline at tick 1000", w)
        dialog = OpenPlanDialog(w, "example/warehouse_small.map", "example/warehouse_small_2026.json")
        dialog.resize(660, 260)
        dialog.show()
        capture(dialog, "open-plan", "Open dialog with converter selection and agent limit")
        dialog.close()

        w.show_visual_settings()
        w.visual_settings.resize(410, 610)
        capture(w.visual_settings, "visual-settings", "All visual controls and task-display modes", w)
        w.visual_settings.close()

        w.show_palette_legend()
        w.legend_dialog.resize(660, 690)
        capture(w.legend_dialog, "legend-agents", "Agent status colors, outlines and start markers", w)
        w.legend_dialog.tabs.setCurrentIndex(1)
        capture(w.legend_dialog, "legend-tasks", "Task/errand shapes, colors and shared-cell label rules", w)
        w.legend_dialog.close()

        w.playback.seek(3000)
        w.show_productivity()
        chart = w._dialogs[0]
        chart.set_time(3000)
        chart._flush_time()
        chart.canvas.draw()
        capture(chart, "productivity", "Recorded completed tasks with the chart cursor at tick 3000", w)
        chart.close()

        w.show_metadata()
        w.details_dialog.resize(830, 1000)
        capture(w.details_dialog, "solution-details", "Map metrics, timing, source results and input warnings", w)
        w.details_dialog.close()

        selection = window("warehouse_small.map", "warehouse_small_2024.json", time=20)
        selection.select_agent(8)
        selection.filter_agents.setChecked(True)
        selection.layer_actions["task_ids"].setChecked(True)
        capture(selection, "selected-path", "Agent 8's path to its next errand at timestep 20", selection)
        selection.clear_selection()
        selection.filter_agents.setChecked(False)
        selection.playback.seek(60)
        selection.task_mode.setCurrentIndex(selection.task_mode.findData("all"))
        selection.tabs.setCurrentIndex(2)
        selection.task_table.setColumnWidth(0, 65)
        selection.task_table.setColumnWidth(1, 65)
        selection.task_table.setColumnWidth(2, 120)
        capture(selection, "task-inspector", "All released task markers and the searchable Tasks table", selection)
        selection.layer_actions["starts"].setChecked(True)
        selection.layer_actions["hover_location"].setChecked(True)
        selection.task_mode.setCurrentIndex(selection.task_mode.findData("none"))
        point = selection.map_view.mapFromScene(QPointF(29.5, 17.5))

        def hover():
            viewport = selection.map_view.viewport()
            event = QMouseEvent(QEvent.Type.MouseMove, QPointF(point),
                               QPointF(viewport.mapToGlobal(point)), Qt.MouseButton.NoButton,
                               Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
            app.sendEvent(viewport, event)
            assert selection.map_view.hovered_cell == (17, 29)
            assert selection.map_view._hover_label.isVisible()

        capture(selection.map_view, "starts-hover", "Start markers and a row/column hover badge",
                selection, before_grab=hover)

        errors = window("warehouse_small.map", "warehouse_small_2023.json", time=82)
        errors.layer_actions["collisions"].setChecked(True)
        errors.tabs.setCurrentIndex(1)
        row = next(i for i, c in enumerate(errors.conflicts_model.records)
                   if c.time == 82 and c.agent_ids)
        errors.conflicts_table.selectRow(row)
        errors._conflict_activated(errors.conflicts_model.index(row, 0))
        errors.map_view.fit_map()
        capture(errors, "errors", "Recorded vertex conflict at timestep 82 in the 2023 fixture", errors)

        mapf = window("random-32-32-20.map", "mapf_plan_example.json", time=20)
        mapf.select_agent(0)
        capture(mapf, "mapf", "MAPF replay without heading-based motion, agent 0 selected", mapf)

        traffic = window("warehouse_small.map", "warehouse_small_2024.json", time=60, heatmap=True)
        traffic.task_mode.setCurrentIndex(traffic.task_mode.findData("none"))
        traffic.overlay_menu.actions()[0].setChecked(True)
        # setChecked alone does not emit QAction.triggered, as a menu click does.
        traffic.map_view.set_overlay_visible(traffic.overlay_menu.actions()[0].text(), True)
        capture(traffic, "traffic-heatmap", "Traffic heatmap derived from the loaded 2024 execution", traffic)

        large = window("LoRR2026/maps/orz900d.map", "LoRR2026/outputs/orz-example_1800_output.json", time=500)
        large.layer_actions["agent_ids"].setChecked(False)
        large.map_view.zoom_at(large.map_view.viewport().rect().center(), 4)
        large.select_agent(0, center=True)
        capture(large, "large-map", "Zoomed 1800-agent replay with minimap viewport navigation", large)

        for widget in windows:
            widget.close()
        app.processEvents()
    manifest = {"method": "Real PySide6 widget grabs, offscreen Fusion, 2x pixel density",
                "font": "Arial 11pt", "fixtures_sha256": fixtures, "captures": captures}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
