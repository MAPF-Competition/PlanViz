"""Cancellable workers with generation checks and safe asynchronous shutdown."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from threading import Event
import traceback
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


@dataclass(frozen=True)
class LoadRequest:
    map_path: str
    plan_path: str
    version: str | None = None
    team_size: int | None = None
    overlays: tuple[tuple[str, str], ...] = ()
    input_format: str = "auto"


@dataclass
class LoadResult:
    plan: object
    analytics: object
    overlays: list = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class WorkerSignals(QObject):
    progress = Signal(int, str)
    loaded = Signal(int, object)
    failed = Signal(int, str)
    finished = Signal(int)


class LoadWorker(QRunnable):
    def __init__(self, generation: int, request: LoadRequest):
        super().__init__()
        self.generation, self.request = generation, request
        self.cancel_event = Event()
        self.signals = WorkerSignals()

    def run(self):
        try:
            from planviz_qt.io.loader import load_plan
            from planviz_qt.domain.analytics import AnalyticsIndex
            request = self.request
            plan = load_plan(
                request.map_path, request.plan_path,
                version=request.version, team_size=request.team_size,
                input_format=request.input_format,
                progress=lambda percent, message: self.signals.progress.emit(self.generation, str(message)),
                cancelled=self.cancel_event.is_set,
            )
            if self.cancel_event.is_set():
                return
            self.signals.progress.emit(self.generation, "Indexing tasks and events…")
            result = LoadResult(plan, AnalyticsIndex(plan, cancelled=self.cancel_event.is_set))
            if request.overlays:
                from planviz_qt.io.overlays import load_overlay
                for kind, path in request.overlays:
                    if self.cancel_event.is_set():
                        return
                    self.signals.progress.emit(self.generation, f"Loading {kind}…")
                    try:
                        result.overlays.append(load_overlay(path, kind, plan.map, cancelled=self.cancel_event.is_set))
                    except (OSError, ValueError, KeyError) as error:
                        result.warnings.append(f"{path}: {error}")
            heatmaps = [overlay for overlay in result.overlays
                        if overlay.kind == "heatmap" and overlay.values is not None]
            if len(heatmaps) > 1 and not self.cancel_event.is_set():
                import numpy as np
                combined = np.zeros(heatmaps[0].values.shape, dtype=np.float64)
                for overlay in heatmaps:
                    if self.cancel_event.is_set():
                        return
                    combined += np.nan_to_num(overlay.values)
                combined[plan.map.grid == 0] = np.nan
                result.overlays.insert(0, replace(heatmaps[0], name="Combined heatmap", values=combined))
            names = set()
            for index, overlay in enumerate(result.overlays):
                name, suffix = overlay.name, 2
                while name in names:
                    name = f"{overlay.name} ({suffix})"
                    suffix += 1
                names.add(name)
                result.overlays[index] = replace(overlay, name=name)
            if not self.cancel_event.is_set():
                self.signals.loaded.emit(self.generation, result)
        except Exception as error:
            if not self.cancel_event.is_set():
                traceback.print_exc()
                self.signals.failed.emit(self.generation, str(error) or type(error).__name__)
        finally:
            self.signals.finished.emit(self.generation)


class LoadManager(QObject):
    loaded = Signal(object)
    failed = Signal(str)
    progress = Signal(str)
    busyChanged = Signal(bool)
    drained = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self._generation = 0
        self._workers: dict[int, LoadWorker] = {}

    @property
    def pending(self):
        return bool(self._workers)

    def load(self, request: LoadRequest):
        self.cancel()
        self._generation += 1
        worker = LoadWorker(self._generation, request)
        self._workers[self._generation] = worker
        worker.signals.progress.connect(self._progress)
        worker.signals.loaded.connect(self._loaded)
        worker.signals.failed.connect(self._failed)
        worker.signals.finished.connect(self._finished)
        self.busyChanged.emit(True)
        self.pool.start(worker)

    def cancel(self):
        self._generation += 1
        for worker in self._workers.values():
            worker.cancel_event.set()
        self.busyChanged.emit(False)

    @Slot(int, str)
    def _progress(self, generation, message):
        if generation == self._generation:
            self.progress.emit(message)

    @Slot(int, object)
    def _loaded(self, generation, result):
        if generation == self._generation:
            self.loaded.emit(result)

    @Slot(int, str)
    def _failed(self, generation, message):
        if generation == self._generation:
            self.failed.emit(message)

    @Slot(int)
    def _finished(self, generation):
        self._workers.pop(generation, None)
        if generation == self._generation:
            self.busyChanged.emit(False)
        if not self._workers:
            self.drained.emit()
