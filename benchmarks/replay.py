"""Repeatable CPU-side replay measurements; run separately from tests.

From the repository root:
  QT_QPA_PLATFORM=offscreen PYTHONPATH=src python benchmarks/replay.py

These timings exclude native presentation/vsync. Rendering and logical-tick
updates are separate operations, not measured application FPS.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import numpy as np
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from planviz_qt.application.loading import LoadResult
from planviz_qt.domain.analytics import AnalyticsIndex
from planviz_qt.domain.selection import SelectedPathService
from planviz_qt.io.loader import load_plan
from planviz_qt.ui.main_window import MainWindow

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = (
    ('warehouse', 'example/warehouse_small.map', 'example/warehouse_small_2026.json'),
    ('iron', 'example/LoRR2026/maps/scene_mp_2p_01.map', 'example/LoRR2026/outputs/iron-example_10000_output.json'),
)


def paint(view, image):
    painter = QPainter(image)
    before = time.perf_counter()
    try:
        view.render(painter, QRectF(image.rect()), view.viewport().rect())
        return (time.perf_counter()-before)*1000
    finally:
        painter.end()


def measure(app, samples, warmup):
    for name, map_path, plan_path in FIXTURES:
        before = time.perf_counter()
        plan = load_plan(ROOT/map_path, ROOT/plan_path)
        analytics = AnalyticsIndex(plan)
        load_ms = (time.perf_counter()-before)*1000
        window = MainWindow()
        window.accept_result(LoadResult(plan, analytics))
        window.show()
        app.processEvents()
        yield dict(fixture=name, agents=plan.team_size, max_time=plan.max_time,
                   source_MiB=round((ROOT/plan_path).stat().st_size/2**20, 2),
                   compressed_path_MiB=round(plan.paths.storage_bytes/2**20, 2),
                   load_and_index_ms=round(load_ms, 2),
                   viewport=window.map_view.viewport().size().toTuple())
        image = QImage(window.map_view.viewport().size(), QImage.Format.Format_ARGB32_Premultiplied)
        base_tick = min(1000, max(0, plan.max_time-max(100, samples+warmup)))
        for ids, selected in ((False, 0), (True, 0), (False, 20)):
            window.layer_actions['agent_ids'].setChecked(ids)
            window.selected_agents = set(range(min(selected, plan.team_size)))
            window.selection_paths = SelectedPathService(plan, analytics)
            window.playback.seek(base_tick)
            window._refresh_selection()
            window.map_view._selection_pulse.stop()
            window.map_view._finish_selection_pulse()
            updates, paints = [], []
            for offset in range(1, samples+warmup+1):
                before = time.perf_counter()
                window.playback.seek(base_tick+offset)
                update_ms = (time.perf_counter()-before)*1000
                paint_ms = paint(window.map_view, image)
                if offset > warmup:
                    updates.append(update_ms)
                    paints.append(paint_ms)
            yield dict(fixture=name, agent_ids=ids, selected=selected, tick_start=base_tick,
                       logical_tick_update_median_ms=round(float(np.median(updates)), 2),
                       logical_tick_update_p95_ms=round(float(np.quantile(updates, .95)), 2),
                       paint_median_ms=round(float(np.median(paints)), 2),
                       paint_p95_ms=round(float(np.quantile(paints, .95)), 2),
                       path_cache_entries=window.selection_paths.cache_entries,
                       path_cache_MiB=round(window.selection_paths.cache_bytes/2**20, 2),
                       label_cache_MiB=round(window.map_view._layer._agent_rasters.bytes_used/2**20, 2))
        # Separate cold-cache costs from the warm measurements above.
        window.selected_agents.clear()
        window._refresh_selection()
        window.layer_actions['agent_ids'].setChecked(True)
        window.map_view._layer._agent_labels.clear()
        window.map_view._layer._agent_rasters.clear()
        yield dict(fixture=name, cold_label_paint_ms=round(paint(window.map_view, image), 2))
        window.close()
        window.deleteLater()
        app.processEvents()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=int, default=20)
    parser.add_argument('--warmup', type=int, default=4)
    args = parser.parse_args()
    if args.samples < 2 or args.warmup < 0:
        parser.error('Use at least two samples and a nonnegative warmup count.')
    app = QApplication([])
    for row in measure(app, args.samples, args.warmup):
        print(json.dumps(row), flush=True)


if __name__ == '__main__':
    main()
