"""Raster maps and batched, viewport-culled agents in fixed cell coordinates.

Left/right click selects an agent (Ctrl-left requests additive selection).
Left click on empty space or Ctrl-right click reports a cell; empty right click
clears agent selection. Drag with the left/middle button to pan. F fits the map,
+/- zoom, arrow keys pan, and Escape requests selection clearing.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

import numpy as np
from PySide6.QtCore import QEvent, QLineF, QPoint, QPointF, QRectF, Qt, Signal, QVariantAnimation
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QStaticText, QTransform
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QLabel

from planviz_qt.palette import Palette, load_palette
from .text_cache import RasterTextCache


AGENT_COLOR = load_palette().color("agent", "idle")
MAP_PALETTE = np.array([[27, 31, 39, 255], [247, 248, 250, 255], [207, 229, 215, 255]], dtype=np.uint8)


def _rgba_image(pixels: np.ndarray) -> QImage:
    rgba = np.ascontiguousarray(pixels, dtype=np.uint8)
    return QImage(rgba.data, rgba.shape[1], rgba.shape[0], rgba.strides[0],
                  QImage.Format.Format_RGBA8888).copy()


def _positions(values: Any) -> np.ndarray:
    result = np.asarray(values, dtype=np.float64)
    if result.size == 0:
        return np.empty((0, 3), dtype=np.float64)
    if result.ndim != 2 or result.shape[1] < 2:
        raise ValueError("Positions must have shape (agents, 2 or 3): row, col, [direction].")
    if result.shape[1] == 2:
        result = np.column_stack((result, np.full(len(result), -1.0)))
    if result.shape[1] == 3 and not result.flags.writeable:
        return result
    return np.array(result[:, :3], copy=True)


def _visible_indices(positions: np.ndarray, rect: QRectF, margin: float = 0.5) -> np.ndarray:
    if not len(positions):
        return np.empty(0, dtype=np.int64)
    x, y = positions[:, 1] + 0.5, positions[:, 0] + 0.5
    return np.flatnonzero(np.isfinite(x) & np.isfinite(y) &
                          (x >= rect.left() - margin) & (x <= rect.right() + margin) &
                          (y >= rect.top() - margin) & (y <= rect.bottom() + margin))


def _filled_path() -> QPainterPath:
    path = QPainterPath()
    # Agent circles can overlap or exactly coincide at a recorded collision.
    # Odd-even fill would erase their overlap, hiding the bodies we must show.
    path.setFillRule(Qt.FillRule.WindingFill)
    return path


class _DynamicLayer(QGraphicsItem):
    """One scene item regardless of agent, task, or path vertex count."""

    def __init__(self, view: "MapView") -> None:
        super().__init__()
        self.view = view
        self.rect = QRectF()
        self.last_painted_agents = 0
        self._task_batch_key = None
        self._task_batches: list[tuple[QBrush, str, list]] = []
        self._task_label_size = None
        self._task_label_font = QFont("Arial")
        self._task_labels: dict[str, tuple[QStaticText, float, float]] = {}
        self._agent_label_size = None
        self._agent_label_font = QFont("Arial")
        self._agent_labels: dict[int, tuple[QStaticText, float, float]] = {}
        self._agent_rasters = RasterTextCache()
        self._start_cache_key = None
        self._start_cache = QImage()
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(10)

    def set_rect(self, rect: QRectF) -> None:
        self.prepareGeometryChange()
        self.rect = QRectF(rect)
        self._agent_labels.clear()
        self._agent_rasters.clear()
        self._task_labels.clear()
        self._start_cache_key = None
        self._start_cache = QImage()

    def boundingRect(self) -> QRectF:
        return self.rect

    def paint(self, painter: QPainter, option, widget=None) -> None:
        view = self.view
        scale = max(math.hypot(painter.worldTransform().m11(), painter.worldTransform().m12()), 1e-9)
        # QGraphicsView.render() may expose the whole large item, even with
        # ItemUsesExtendedStyleOption. Always restrict Python work to this view.
        exposed = option.exposedRect.intersected(self.rect).intersected(view.visible_scene_rect())
        radius = max(0.42, min(2.0 / scale, 4.0))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, scale >= 4)
        if view.options["grid"] and scale >= 9:
            pen = QPen(QColor(125, 134, 147, 70), 0)
            painter.setPen(pen)
            lines = []
            for col in range(max(0, math.ceil(exposed.left())), min(view.map_width, math.floor(exposed.right())) + 1):
                lines.append(QLineF(col, exposed.top(), col, exposed.bottom()))
            for row in range(max(0, math.ceil(exposed.top())), min(view.map_height, math.floor(exposed.bottom())) + 1):
                lines.append(QLineF(exposed.left(), row, exposed.right(), row))
            if lines:
                painter.drawLines(lines)

        if view.options["starts"]:
            self._paint_starts(painter, exposed, radius)

        painter.setPen(Qt.PenStyle.NoPen)
        visible_tasks = _visible_indices(view.task_positions, exposed, 1)
        task_key = (view._task_revision, visible_tasks.tobytes(), view._task_global_batching)
        if task_key != self._task_batch_key:
            self._task_batches = []
            batch_indices = {}
            for task_index in visible_tasks:
                task = view.tasks[task_index]
                brush = task["brush"]
                shape = task["shape"]
                if view._task_global_batching:
                    # Coalesced integer-grid markers cannot overlap. Group all
                    # of each shape/color to avoid a brush switch at every stop.
                    key = (id(brush), shape)
                    if key not in batch_indices:
                        batch_indices[key] = len(self._task_batches)
                        self._task_batches.append((brush, shape, []))
                    batch = self._task_batches[batch_indices[key]]
                else:
                    # Generic/fractional markers may overlap, so their original
                    # paint order must survive even across repeated colors.
                    if (not self._task_batches or self._task_batches[-1][0] is not brush
                            or self._task_batches[-1][1] != shape):
                        self._task_batches.append((brush, shape, []))
                    batch = self._task_batches[-1]
                batch[2].append(task["geometry"])
            self._task_batch_key = task_key
        for brush, shape, geometries in self._task_batches:
            painter.setBrush(brush)
            if shape == "square":
                painter.drawRects(geometries)
            else:
                for polygon in geometries:
                    painter.drawPolygon(polygon)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        sequence_pen = QPen(QColor(view.palette.color("path", "remaining_errands")), 2)
        sequence_pen.setCosmetic(True)
        painter.setPen(sequence_pen)
        for path in view.task_sequence_geometry.values():
            if path.boundingRect().adjusted(-.01, -.01, .01, .01).intersects(exposed):
                painter.drawPath(path)
        moving_connections = QPainterPath()
        for agent, target in view.task_sequence_targets.items():
            if 0 <= agent < len(view.positions):
                row, col = view.positions[agent, :2]
                if math.isfinite(row) and math.isfinite(col):
                    _arrow_segment(moving_connections, QPointF(col + .5, row + .5), target, .22)
        painter.drawPath(moving_connections)

        # Keep the recorded route visible when it coincides with the straight
        # target arrow. Draw it last and slightly wider than the arrow shaft.
        path_color = QColor(view.palette.color("path", "executed"))
        path_color.setAlpha(170)
        path_pen = QPen(path_color, 3)
        path_pen.setCosmetic(True)
        painter.setPen(path_pen)
        for path in view.path_geometry.values():
            if path.boundingRect().adjusted(-.01, -.01, .01, .01).intersects(exposed):
                painter.drawPath(path)

        # Connection arrows terminate at task centers. Paint text afterwards so
        # their strokes cannot obscure the task IDs at those endpoints.
        if view.options["task_ids"]:
            self._paint_task_ids(painter, visible_tasks, scale)

        visible = _visible_indices(view.positions, exposed, radius)
        self.last_painted_agents = len(visible)
        groups: dict[str, list[int]] = defaultdict(list)
        for index in visible:
            groups[view.colors[index]].append(index)
        painter.setPen(Qt.PenStyle.NoPen)
        for name, indices in groups.items():
            color = QColor(name)
            painter.setBrush(color)
            # Scalar lists avoid allocating thousands of GC-tracked point or
            # row objects together, which causes periodic collection pauses.
            rows = view.positions[indices, 0].tolist()
            columns = view.positions[indices, 1].tolist()
            if color.alpha() == 255:
                # Qt's ellipse primitive avoids rasterizing one antialiased
                # compound path spanning the whole map on every frame.
                for row, col in zip(rows, columns):
                    painter.drawEllipse(QPointF(col + .5, row + .5), radius, radius)
            else:
                # A translucent group historically blends once at overlaps.
                path = _filled_path()
                for row, col in zip(rows, columns):
                    path.addEllipse(QPointF(col + .5, row + .5), radius, radius)
                painter.drawPath(path)

        if view.options["headings"] and scale >= 10:
            painter.setBrush(QColor(view.palette.color("agent", "heading")))
            for row, col, direction in zip(*(view.positions[visible, axis].tolist() for axis in range(3))):
                if not math.isfinite(direction) or direction < 0:
                    continue
                angle = direction * math.pi / 2
                painter.drawEllipse(QPointF(col + 0.5 + 0.30 * math.cos(angle),
                                           row + 0.5 - 0.30 * math.sin(angle)), 0.085, 0.085)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        selected_pen = QPen(QColor(view.palette.color("agent", "selected_outline")), 2.4)
        selected_pen.setCosmetic(True)
        collision_pen = QPen(QColor(view.palette.color("agent", "collision_outline")), 2.8)
        collision_pen.setCosmetic(True)
        marked = view.selected_agents | (view.collision_agents if view.options["collisions"] else set())
        decorated = np.intersect1d(visible, np.fromiter(marked, dtype=np.int64)) if marked else ()
        for index in decorated:
            row, col = view.positions[index, :2]
            if view.options["collisions"] and int(index) in view.collision_agents:
                painter.setPen(collision_pen)
                painter.drawEllipse(QPointF(col + 0.5, row + 0.5), radius + 1.5 / scale, radius + 1.5 / scale)
            if int(index) in view.selected_agents:
                painter.setPen(selected_pen)
                painter.drawEllipse(QPointF(col + 0.5, row + 0.5), radius + 3 / scale, radius + 3 / scale)
        if view.options["agent_ids"]:
            self._paint_agent_ids(painter, visible, scale)
        # A short selection cue follows the rendered (interpolated) position.
        # It never changes agent state, size, or the persistent selection ring.
        if view._pulse_agents:
            progress = view._pulse_progress
            color = QColor(view.palette.color("agent", "selected_outline"))
            color.setAlphaF(.85 * (1 - progress))
            pulse_pen = QPen(color, 2.6)
            pulse_pen.setCosmetic(True)
            painter.setPen(pulse_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            pulse_radius = radius + (5 + 15 * progress) / scale
            for agent in view._pulse_agents:
                if agent >= len(view.positions):
                    continue
                row, col = view.positions[agent, :2]
                if math.isfinite(row) and math.isfinite(col):
                    painter.drawEllipse(QPointF(col + .5, row + .5), pulse_radius, pulse_radius)

    def _paint_starts(self, painter: QPainter, exposed: QRectF, radius: float) -> None:
        if exposed.isEmpty():
            return
        transform = painter.worldTransform()
        # Retain only the visible raster, including the cosmetic outline at its
        # edges. A full-map cache would grow without bound while zooming in.
        rect = transform.mapRect(exposed).toAlignedRect().adjusted(-2, -2, 2, 2)
        dpr = painter.device().devicePixelRatioF()
        key = (transform.m11(), transform.m12(), transform.m13(),
               transform.m21(), transform.m22(), transform.m23(),
               transform.m31(), transform.m32(), transform.m33(),
               rect.x(), rect.y(), rect.width(), rect.height(),
               exposed.x(), exposed.y(), exposed.width(), exposed.height(),
               dpr, radius, painter.renderHints())
        if key != self._start_cache_key:
            image = QImage(math.ceil(rect.width() * dpr), math.ceil(rect.height() * dpr),
                           QImage.Format.Format_ARGB32_Premultiplied)
            if image.isNull():
                self._draw_starts(painter, exposed, radius)
                return
            image.setDevicePixelRatio(dpr)
            image.fill(Qt.GlobalColor.transparent)
            cached = QPainter(image)
            cached.setRenderHints(painter.renderHints())
            cached.setWorldTransform(transform * QTransform.fromTranslate(-rect.x(), -rect.y()))
            self._draw_starts(cached, exposed, radius)
            cached.end()
            self._start_cache = image
            self._start_cache_key = key
        painter.save()
        painter.setWorldTransform(QTransform())
        painter.drawImage(QPointF(rect.x(), rect.y()), self._start_cache)
        painter.restore()

    def _draw_starts(self, painter: QPainter, exposed: QRectF, radius: float) -> None:
        painter.setPen(QPen(QColor(self.view.palette.color("agent", "start_outline")), 0))
        fill = QColor(self.view.palette.color("agent", "start_fill"))
        fill.setAlpha(70)
        painter.setBrush(fill)
        starts = _filled_path()
        for index in _visible_indices(self.view.starts, exposed, radius):
            row, col = self.view.starts[index, :2]
            starts.addEllipse(QPointF(col + .5, row + .5), radius, radius)
        # Keep a single winding fill so coincident translucent markers do not
        # darken. Only camera changes or plan replacement rasterize it again.
        painter.drawPath(starts)

    def _paint_agent_ids(self, painter: QPainter, visible, scale: float) -> None:
        # A checked display option must work at Fit map as well as close zoom.
        # Draw in screen coordinates so the full ID stays readable instead of
        # being clipped to a subpixel/single-digit cell-sized rectangle.
        pixels = max(10, min(17, int(scale * .38)))
        if pixels != self._agent_label_size:
            self._agent_label_size = pixels
            self._agent_label_font.setPixelSize(pixels)
            self._agent_labels.clear()
        transform = painter.worldTransform()
        painter.save()
        painter.setWorldTransform(QTransform())
        painter.setFont(self._agent_label_font)
        color = QColor(self.view.palette.color("agent", "index"))
        painter.setPen(color)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        dpr = painter.device().devicePixelRatioF()
        self._agent_rasters.configure(self._agent_label_font, color, dpr)
        indices = visible.tolist()
        rows = self.view.positions[visible, 0] + .5
        columns = self.view.positions[visible, 1] + .5
        xs = (transform.m11()*columns + transform.m21()*rows + transform.dx()).tolist()
        ys = (transform.m12()*columns + transform.m22()*rows + transform.dy()).tolist()
        for index, x, y in zip(indices, xs, ys):
            label = self._agent_labels.get(index)
            if label is None:
                text = QStaticText(str(index))
                text.setTextFormat(Qt.TextFormat.PlainText)
                text.prepare(QTransform(), self._agent_label_font)
                size = text.size()
                label = self._agent_labels[index] = (text, size.width() / 2, size.height() / 2)
            text, half_width, half_height = label
            raster = self._agent_rasters.get(index, text, self._agent_label_font, color, dpr)
            if raster is None:
                painter.drawStaticText(QPointF(x-half_width, y-half_height), text)
            else:
                painter.drawPixmap(QPointF(x-half_width-1, y-half_height-1), raster)
        painter.restore()

    def _paint_task_ids(self, painter: QPainter, visible, scale: float) -> None:
        pixels = max(10, min(17, int(scale * .38)))
        if pixels != self._task_label_size:
            self._task_label_size = pixels
            self._task_label_font.setPixelSize(pixels)
            self._task_labels.clear()
        transform = painter.worldTransform()
        painter.save()
        painter.setWorldTransform(QTransform())
        painter.setFont(self._task_label_font)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        previous_kind = None
        for index in visible:
            marker = self.view.tasks[index]
            label = marker["label"]
            if not label:
                continue
            layout = self._task_labels.get(label)
            if layout is None:
                text = QStaticText(label)
                text.setTextFormat(Qt.TextFormat.PlainText)
                text.prepare(QTransform(), self._task_label_font)
                size = text.size()
                layout = self._task_labels[label] = (text, size.width() / 2, size.height() / 2)
            kind = marker["kind"]
            if kind != previous_kind:
                painter.setPen(QColor(self.view.palette.color(kind, "index")))
                previous_kind = kind
            text, half_width, half_height = layout
            point = transform.map(QPointF(marker["col"] + .5, marker["row"] + .5))
            painter.drawStaticText(QPointF(point.x() - half_width, point.y() - half_height), text)
        painter.restore()


class _SegmentOverlay(QGraphicsItem):
    """Highway arrows in one item, with vectorized viewport filtering."""

    def __init__(self, view: "MapView", segments) -> None:
        super().__init__()
        self.view = view
        self.segments = np.asarray(segments, dtype=np.float64).reshape((-1, 4))
        self.segments = self.segments[np.all(np.isfinite(self.segments), axis=1)]
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(3)

    def boundingRect(self) -> QRectF:
        return self.view.world_rect

    def paint(self, painter, option, widget=None) -> None:
        scale = self.view.current_scale
        if scale < 3 or not len(self.segments):
            return
        rect = self.view.visible_scene_rect().adjusted(-1, -1, 1, 1)
        rows0, cols0, rows1, cols1 = self.segments.T
        mask = ((np.maximum(cols0, cols1) + .5 >= rect.left()) &
                (np.minimum(cols0, cols1) + .5 <= rect.right()) &
                (np.maximum(rows0, rows1) + .5 >= rect.top()) &
                (np.minimum(rows0, rows1) + .5 <= rect.bottom()))
        path = QPainterPath()
        for row0, col0, row1, col1 in self.segments[mask]:
            _arrow_segment(path, QPointF(col0 + .5, row0 + .5), QPointF(col1 + .5, row1 + .5), .18)
        pen = QPen(QColor("#cc3d3d"), 1.3)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)


def _arrow_segment(path: QPainterPath, start: QPointF, end: QPointF, head: float) -> None:
    path.moveTo(start)
    path.lineTo(end)
    dx, dy = end.x() - start.x(), end.y() - start.y()
    distance = math.hypot(dx, dy)
    if distance < 1e-9:
        return
    ux, uy = dx / distance, dy / distance
    head = min(head, distance * .35)
    path.moveTo(end.x() - head * ux + head * .55 * uy, end.y() - head * uy - head * .55 * ux)
    path.lineTo(end)
    path.lineTo(end.x() - head * ux - head * .55 * uy, end.y() - head * uy + head * .55 * ux)


class MapView(QGraphicsView):
    agentSelected = Signal(int, bool)
    locationSelected = Signal(int, int)
    hovered = Signal(int, int)
    viewportChanged = Signal()
    planChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        scene = QGraphicsScene(self)
        scene.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
        self.setScene(scene)
        self.plan = None
        self.palette = load_palette()
        self.map_width = self.map_height = 0
        self.map_image = QImage()
        self.positions = np.empty((0, 3), dtype=np.float64)
        self.starts = self.positions.copy()
        self.colors: list[str] = []
        self._default_agent_indices: range | tuple[int, ...] = ()
        self._color_cache: dict[str, str] = {}
        self.time = 0.0
        self.options = dict(grid=False, agent_ids=False, starts=False, headings=True, collisions=True,
                            task_ids=False, hover_location=False)
        self.selected_agents: set[int] = set()
        self._pulse_agents: set[int] = set()
        self._pulse_progress = 1.0
        self._selection_pulse = QVariantAnimation(self)
        self._selection_pulse.setDuration(420)
        self._selection_pulse.setStartValue(0.0)
        self._selection_pulse.setEndValue(1.0)
        self._selection_pulse.valueChanged.connect(self._advance_selection_pulse)
        self._selection_pulse.finished.connect(self._finish_selection_pulse)
        self.collision_agents: set[int] = set()
        self.tasks: list[dict] = []
        self._task_markers: tuple[dict, ...] = ()
        self._task_global_batching = False
        self.task_positions = np.empty((0, 3), dtype=np.float64)
        self._task_brush_cache: dict[str, QBrush] = {}
        self._task_visual_cache: dict[tuple, dict] = {}
        self._task_visual_key: tuple = ()
        self._task_revision = 0
        self._task_position_key: tuple = ()
        self.path_geometry: dict[int, QPainterPath] = {}
        self._selected_path_keys = {}
        self.task_sequence_geometry: dict[int, QPainterPath] = {}
        self.task_sequence_targets: dict[int, QPointF] = {}
        self.overlays: dict[str, QGraphicsItem] = {}
        self._background = QGraphicsPixmapItem()
        self._background.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._background.setTransformationMode(Qt.TransformationMode.FastTransformation)
        scene.addItem(self._background)
        self._layer = _DynamicLayer(self)
        scene.addItem(self._layer)
        self._fitted = True
        self._fit_scale = 1.0
        self._press_pos: QPoint | None = None
        self._drag_last = QPoint()
        self._dragging = False
        self._hover_pos: QPoint | None = None
        self._hovered_cell = (-1, -1)
        # One viewport child stays readable at every zoom without adding scene
        # items or rebuilding map/agent geometry as the pointer moves.
        self._hover_label = QLabel(self.viewport())
        self._hover_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._hover_label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._hover_label.setMargin(5)
        self._hover_label.setStyleSheet(
            "QLabel { color: #243247; background: #fffef8; border: 1px solid #9ca9b9; border-radius: 4px; }"
        )
        self._hover_label.hide()
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setBackgroundBrush(QColor("#dfe4ec"))
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Plan map")
        self.setAccessibleDescription("Drag to pan. Mouse wheel zooms. F fits map. Arrow keys pan. Escape clears selection.")
        self.horizontalScrollBar().valueChanged.connect(lambda _: self.viewportChanged.emit())
        self.verticalScrollBar().valueChanged.connect(lambda _: self.viewportChanged.emit())
        self.viewportChanged.connect(self._refresh_hover)

    @property
    def world_rect(self) -> QRectF:
        return QRectF(0, 0, self.map_width, self.map_height)

    @property
    def current_scale(self) -> float:
        return max(abs(self.transform().m11()), 1e-9)

    @property
    def hovered_cell(self) -> tuple[int, int]:
        """Current valid (row, col), or (-1, -1) outside the map/viewport."""
        return self._hovered_cell

    def visible_scene_rect(self) -> QRectF:
        return self.mapToScene(self.viewport().rect()).boundingRect().intersected(self.world_rect)

    def set_plan(self, plan) -> None:
        grid = np.asarray(plan.map.grid, dtype=np.uint8)
        if grid.ndim != 2 or grid.size == 0:
            raise ValueError("Map grid must be a nonempty two-dimensional array.")
        self._clear_hover()
        self.plan = plan
        self.map_height, self.map_width = grid.shape
        self.map_image = _rgba_image(MAP_PALETTE[np.minimum(grid, 2)])
        self._background.setPixmap(QPixmap.fromImage(self.map_image))
        self.scene().setSceneRect(self.world_rect)
        self._layer.set_rect(self.world_rect)
        self.starts = _positions(plan.paths.starts)
        self._selection_pulse.stop()
        self._pulse_agents.clear()
        self.selected_agents.clear()
        self.collision_agents.clear()
        self.tasks.clear()
        self._task_markers = ()
        self._task_global_batching = False
        self.task_positions = np.empty((0, 3), dtype=np.float64)
        self._task_brush_cache.clear()
        self._task_visual_cache.clear()
        self._task_visual_key = ()
        self._task_revision += 1
        self._task_position_key = ()
        self.path_geometry.clear()
        self._selected_path_keys.clear()
        self.task_sequence_geometry.clear()
        self.task_sequence_targets.clear()
        for overlay in self.overlays.values():
            self.scene().removeItem(overlay)
        self.overlays.clear()
        self.set_frame(self.starts, 0)
        self.fit_map()
        self.planChanged.emit()

    def set_frame(self, positions, time, colors=None, *, preserve_colors=False) -> None:
        self.positions = _positions(positions)
        self.time = float(time)
        if not preserve_colors or len(self.colors) != len(self.positions):
            self.set_agent_colors(colors)
        self._layer.update()

    def set_agent_colors(self, colors) -> None:
        default_color = self.palette.color("agent", "idle")
        if colors is None:
            self.colors = [default_color] * len(self.positions)
            self._default_agent_indices = range(len(self.positions))
        elif isinstance(colors, dict):
            self.colors = [self._color_name(colors.get(index, default_color))
                           for index in range(len(self.positions))]
            self._default_agent_indices = tuple(index for index in range(len(self.positions)) if index not in colors)
        else:
            if len(colors) != len(self.positions):
                raise ValueError("One color is required for each agent.")
            self.colors = [self._color_name(color) for color in colors]
            self._default_agent_indices = ()
        self._layer.update()

    def set_palette(self, palette: Palette) -> None:
        """Recolor current markers without retaining old images or brushes.

        Explicit per-agent state colors still belong to the caller; only colors
        originally filled from the idle default are replaced here.
        """
        self.palette = palette
        default_color = palette.color("agent", "idle")
        for index in self._default_agent_indices:
            self.colors[index] = default_color
        self._color_cache.clear()
        self._layer._agent_rasters.clear()
        self._task_brush_cache.clear()
        self._task_visual_cache.clear()
        self._layer._start_cache_key = None
        self._layer._start_cache = QImage()
        self._layer._task_batch_key = None
        self._layer._task_batches.clear()
        self.set_tasks(self._task_markers)
        self._layer.update()

    def _color_name(self, color) -> str:
        if isinstance(color, QColor):
            return color.name(QColor.NameFormat.HexArgb)
        key = str(color)
        if key not in self._color_cache:
            self._color_cache[key] = QColor(key).name(QColor.NameFormat.HexArgb)
        return self._color_cache[key]

    def set_options(self, **options: bool) -> None:
        for name, value in options.items():
            if name in self.options:
                self.options[name] = bool(value)
            elif name in self.overlays:
                self.overlays[name].setVisible(bool(value))
        self._layer.update()
        self._refresh_hover()

    def set_selected_agents(self, agents: set[int]) -> None:
        selected = {int(agent) for agent in agents if 0 <= int(agent) < len(self.positions)}
        added = selected - self.selected_agents
        self.selected_agents = selected
        self._pulse_agents.intersection_update(selected)
        if added:
            self._selection_pulse.stop()
            self._pulse_agents = added
            self._pulse_progress = 0.0
            self._selection_pulse.start()
        elif not self._pulse_agents:
            self._selection_pulse.stop()
        self._layer.update()

    def _advance_selection_pulse(self, progress):
        self._pulse_progress = float(progress)
        self._layer.update()

    def _finish_selection_pulse(self):
        self._pulse_agents.clear()
        self._layer.update()

    def set_collision_agents(self, agents: set[int]) -> None:
        self.collision_agents = {int(agent) for agent in agents}
        self._layer.update()

    def set_conflict_agents(self, agents: set[int]) -> None:
        """Set historical conflict outlines; frame fill colors remain independent."""
        self.set_collision_agents(agents)

    def set_paths(self, paths: dict[int, np.ndarray]) -> None:
        self._selected_path_keys.clear()
        self.path_geometry = {}
        for agent, points in paths.items():
            values = _positions(points)
            path = QPainterPath()
            connected = False
            for row, col, _ in values:
                if not (math.isfinite(row) and math.isfinite(col)):
                    connected = False
                    continue
                if connected:
                    path.lineTo(col + 0.5, row + 0.5)
                else:
                    path.moveTo(col + 0.5, row + 0.5)
                connected = True
            self.path_geometry[int(agent)] = path
        self._layer.update()

    def set_selected_paths(self, previews) -> None:
        """Reuse fixed interior geometry, moving only its clipped endpoints."""
        paths, keys = {}, {}
        for agent, preview in previews.items():
            points, key = preview.points, preview.geometry_key
            path = self.path_geometry.get(agent)
            if path is not None and self._selected_path_keys.get(agent) == key:
                path.setElementPositionAt(0, points[0, 1]+.5, points[0, 0]+.5)
                path.setElementPositionAt(path.elementCount()-1, points[-1, 1]+.5, points[-1, 0]+.5)
            else:
                path = QPainterPath(QPointF(points[0, 1]+.5, points[0, 0]+.5))
                for row, col in points[1:, :2].tolist():
                    path.lineTo(col+.5, row+.5)
            paths[agent], keys[agent] = path, key
        self.path_geometry, self._selected_path_keys = paths, keys
        self._layer.update()

    def set_task_sequences(self, sequences: dict[int, np.ndarray]) -> None:
        self.task_sequence_geometry = {}
        self.task_sequence_targets = {}
        for agent, values in sequences.items():
            points = _positions(values)
            path = QPainterPath()
            if len(points) > 1 and np.all(np.isfinite(points[1, :2])):
                self.task_sequence_targets[int(agent)] = QPointF(points[1, 1] + .5, points[1, 0] + .5)
            # The first connection starts at the current painted agent position,
            # not the integer snapshot supplied when the task list refreshed.
            for start, end in zip(points[1:-1], points[2:]):
                if np.all(np.isfinite(start[:2])) and np.all(np.isfinite(end[:2])):
                    _arrow_segment(path, QPointF(start[1] + .5, start[0] + .5),
                                   QPointF(end[1] + .5, end[0] + .5), .22)
            self.task_sequence_geometry[int(agent)] = path
        self._layer.update()

    @staticmethod
    def _coalesce_task_markers(markers: tuple[dict, ...]):
        """Choose one semantic marker per exact location, preserving generic layers.

        This acts only on the supplied display list. Filtering or seeking back
        therefore restores older tasks without changing domain task history.
        """
        entries = []
        winners = {}
        task_ids_at = defaultdict(set)
        for index, marker in enumerate(markers):
            row, col = float(marker["row"]), float(marker["col"])
            if not (math.isfinite(row) and math.isfinite(col)):
                continue
            location = (row, col)
            semantic = marker.get("task_id") is not None or "state" in marker or "kind" in marker
            entries.append((index, marker, location, semantic))
            if semantic:
                task_id = marker.get("task_id")
                if task_id is not None:
                    task_ids_at[location].add(int(task_id))
                order = (int(marker.get("release_time", 0)),
                         -1 if task_id is None else int(task_id), int(marker.get("stop_index", 0)))
                previous = winners.get(location)
                if previous is None or order >= previous[0]:
                    winners[location] = (order, index)
        for index, marker, location, semantic in entries:
            if semantic and winners[location][1] != index:
                continue
            overlapping = tuple(sorted(task_ids_at[location])) if semantic else ()
            yield marker, location, overlapping

    def set_tasks(self, tasks: list[dict] | tuple[dict, ...]) -> None:
        self._task_markers = tuple(tasks)
        visuals = []
        next_cache = {}
        positions = []
        keys = []
        global_batching = True
        for task, (row, col), overlapping in self._coalesce_task_markers(self._task_markers):
            semantic = task.get("task_id") is not None or "state" in task or "kind" in task
            global_batching = global_batching and semantic and row.is_integer() and col.is_integer()
            kind = "errand" if task.get("kind") == "errand" else "task"
            state = task.get("state")
            palette_state = {"newlyassigned": "newly_assigned", "finished": "completed"}.get(state, state)
            raw_color = (self.palette.color(kind, palette_state) if state is not None
                         else task.get("color", self.palette.color(kind, "assigned")))
            color = raw_color.name(QColor.NameFormat.HexArgb) if isinstance(raw_color, QColor) else str(raw_color)
            label = str(task.get("label", ""))
            if len(overlapping) > 1 and not label.endswith("*"):
                label += "*"
            task_id, stop_index = task.get("task_id"), task.get("stop_index")
            release_time = int(task.get("release_time", 0))
            key = (row, col, label, color, kind, task_id, stop_index, state, release_time, overlapping)
            keys.append(key)
            visual = self._task_visual_cache.get(key)
            if visual is None:
                brush = self._task_brush_cache.get(color)
                if brush is None:
                    brush = QBrush(QColor(color))
                    self._task_brush_cache[color] = brush
                rect = QRectF(col + .08, row + .08, .84, .84)
                geometry = (QPolygonF([QPointF(col + .5, row + .08), QPointF(col + .92, row + .5),
                                       QPointF(col + .5, row + .92), QPointF(col + .08, row + .5)])
                            if kind == "errand" else rect)
                visual = dict(row=row, col=col, label=label, brush=brush, position=(row, col), rect=rect,
                              geometry=geometry, shape="diamond" if kind == "errand" else "square",
                              kind=kind, state=state, task_id=task_id, stop_index=stop_index,
                              release_time=release_time, overlapping_task_ids=overlapping,
                              overlap_count=len(overlapping))
            visuals.append(visual)
            positions.append(visual["position"])
            next_cache[key] = visual
        # Keep only the currently shown records. History/time scrubbing must not
        # accumulate a second task history inside the renderer.
        self.tasks = visuals
        self._task_global_batching = global_batching
        self._task_visual_cache = next_cache
        current_labels = {visual["label"] for visual in visuals}
        self._layer._task_labels = {label: value for label, value in self._layer._task_labels.items()
                                   if label in current_labels}
        visual_key = tuple(keys)
        if visual_key != self._task_visual_key:
            self._task_visual_key = visual_key
            self._task_revision += 1
        position_key = tuple(positions)
        if position_key != self._task_position_key:
            self.task_positions = np.asarray(positions, dtype=np.float64).reshape((-1, 2))
            self._task_position_key = position_key
        self._layer.update()

    def set_overlay(self, name: str, data=None, *, visible: bool = True, opacity: float = 0.55) -> None:
        """Accept an Overlay model, map-sized numeric/RGBA grid or QImage; None removes it."""
        old = self.overlays.pop(name, None)
        if old is not None:
            self.scene().removeItem(old)
        if data is None:
            return
        colormap = "Reds"
        overlay_kind = name
        if hasattr(data, "kind"):
            overlay_kind = data.kind
            if data.kind == "highway" or (getattr(data, "values", None) is None and getattr(data, "segments", ())):
                item = _SegmentOverlay(self, data.segments)
                item.setVisible(visible)
                item.setOpacity(min(max(float(opacity), 0.0), 1.0))
                self.scene().addItem(item)
                self.overlays[name] = item
                return
            colormap = str(getattr(data, "colormap", "Reds") or "Reds")
            data = data.values
            if data is None:
                return
        if isinstance(data, QImage):
            image = data.copy()
        else:
            values = np.asarray(data)
            if values.ndim == 2:
                finite = np.isfinite(values)
                maximum = float(np.max(values[finite])) if finite.any() else 0.0
                minimum = float(np.min(values[finite])) if overlay_kind == "heuristic" and finite.any() else 0.0
                normalized = np.clip((np.where(finite, values, minimum) - minimum) /
                                     max(maximum - minimum, 1e-9), 0, 1)
                rgba = np.zeros((*values.shape, 4), dtype=np.uint8)
                if "grey" in colormap.lower() or "gray" in colormap.lower():
                    rgba[:, :, :3] = np.asarray(235 * (1 - normalized[:, :, None]), dtype=np.uint8)
                elif "blue" in colormap.lower():
                    rgba[:, :, 0] = np.asarray(225 * (1 - normalized), dtype=np.uint8)
                    rgba[:, :, 1] = np.asarray(240 * (1 - normalized), dtype=np.uint8)
                    rgba[:, :, 2] = 220
                else:
                    rgba[:, :, 0] = 220
                    rgba[:, :, 1] = np.asarray(225 * (1 - normalized), dtype=np.uint8)
                    rgba[:, :, 2] = np.asarray(225 * (1 - normalized), dtype=np.uint8)
                visible_values = finite if overlay_kind == "heuristic" else finite & (values > 0)
                rgba[:, :, 3] = np.where(visible_values, 220, 0)
            elif values.ndim == 3 and values.shape[2] in (3, 4):
                rgba = values if values.shape[2] == 4 else np.dstack((values, np.full(values.shape[:2], 255)))
            else:
                raise ValueError("Overlay must be a scalar grid, RGB/RGBA array, or QImage.")
            image = _rgba_image(rgba)
        if image.isNull() or image.width() != self.map_width or image.height() != self.map_height:
            raise ValueError("Overlay dimensions must match the map.")
        item = QGraphicsPixmapItem(QPixmap.fromImage(image))
        item.setZValue(2)
        item.setOpacity(min(max(float(opacity), 0.0), 1.0))
        item.setVisible(visible)
        item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        item.setTransformationMode(Qt.TransformationMode.FastTransformation)
        self.scene().addItem(item)
        self.overlays[name] = item

    def set_overlay_visible(self, name: str, visible: bool) -> None:
        if name in self.overlays:
            self.overlays[name].setVisible(bool(visible))

    def center_agent(self, agent_id: int) -> None:
        if 0 <= agent_id < len(self.positions):
            row, col = self.positions[agent_id, :2]
            if math.isfinite(row) and math.isfinite(col):
                self._fitted = False
                self.centerOn(col + 0.5, row + 0.5)
                self.viewportChanged.emit()

    def center_world(self, x: float, y: float) -> None:
        self._fitted = False
        self.centerOn(min(max(x, 0), self.map_width), min(max(y, 0), self.map_height))
        self.viewportChanged.emit()

    def fit_map(self) -> None:
        if self.world_rect.isEmpty():
            return
        self.resetTransform()
        self.fitInView(self.world_rect, Qt.AspectRatioMode.KeepAspectRatio)
        self._fit_scale = self.current_scale
        self._fitted = True
        self.viewportChanged.emit()

    def zoom_at(self, position: QPoint, factor: float) -> None:
        if self.world_rect.isEmpty() or not math.isfinite(factor) or factor <= 0:
            return
        target = max(self._fit_scale * 0.5, min(self.current_scale * factor, 256.0))
        point = self.mapToScene(position)
        self.scale(target / self.current_scale, target / self.current_scale)
        after = self.mapFromScene(point)
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + after.x() - position.x())
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() + after.y() - position.y())
        self._fitted = False
        self.viewportChanged.emit()

    def agent_at(self, scene_position: QPointF) -> int:
        if not len(self.positions):
            return -1
        delta = self.positions[:, :2] - np.array([scene_position.y() - 0.5, scene_position.x() - 0.5])
        distances = np.sum(delta * delta, axis=1)
        distances[~np.isfinite(distances)] = np.inf
        index = int(np.argmin(distances))
        hit_radius = max(0.45, min(5 / self.current_scale, 4.0))
        return index if distances[index] <= hit_radius * hit_radius else -1

    def wheelEvent(self, event) -> None:
        pixels, angle = event.pixelDelta(), event.angleDelta()
        delta = pixels.y() / 240 if pixels.y() else angle.y() / 120 * 0.16
        if delta:
            self.zoom_at(event.position().toPoint(), math.exp(max(-2, min(2, delta))))
        elif pixels.x() or angle.x():
            self._fitted = False
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - (pixels.x() or angle.x()))
        event.accept()

    def viewportEvent(self, event) -> bool:
        if event.type() == QEvent.Type.Leave:
            self._clear_hover()
        if event.type() == QEvent.Type.NativeGesture and event.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
            self.zoom_at(event.position().toPoint(), math.exp(event.value()))
            event.accept()
            return True
        return super().viewportEvent(event)

    def mousePressEvent(self, event) -> None:
        self.setFocus()
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._press_pos = event.position().toPoint()
            self._drag_last = self._press_pos
            self._dragging = False
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        point = event.position().toPoint()
        if self._press_pos is not None:
            if (point - self._press_pos).manhattanLength() >= 5:
                self._dragging = True
            if self._dragging:
                delta = point - self._drag_last
                self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
                self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
                self._fitted = False
                self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            self._drag_last = point
        self._hover_pos = point
        self._refresh_hover()
        event.accept()

    def _clear_hover(self) -> None:
        self._hover_pos = None
        self._refresh_hover()

    def _refresh_hover(self) -> None:
        cell = (-1, -1)
        point = self._hover_pos
        if self.plan is not None and point is not None and self.viewport().rect().contains(point):
            scene = self.mapToScene(point)
            row, col = math.floor(scene.y()), math.floor(scene.x())
            if 0 <= row < self.map_height and 0 <= col < self.map_width:
                cell = (row, col)
        self._hovered_cell = cell
        self.hovered.emit(*cell)
        if not self.options["hover_location"] or cell == (-1, -1):
            self._hover_label.hide()
            return
        text = f"Row {cell[0]} · Col {cell[1]}"
        if self._hover_label.text() != text:
            self._hover_label.setText(text)
            self._hover_label.adjustSize()
        width, height = self._hover_label.width(), self._hover_label.height()
        viewport = self.viewport().rect()
        x, y = point.x() + 14, point.y() + 18
        if x + width > viewport.width() - 6:
            x = point.x() - width - 14
        if y + height > viewport.height() - 6:
            y = point.y() - height - 12
        self._hover_label.move(max(0, min(x, viewport.width() - width)),
                               max(0, min(y, viewport.height() - height)))
        self._hover_label.show()
        self._hover_label.raise_()

    def mouseReleaseEvent(self, event) -> None:
        dragged = self._dragging
        self._press_pos = None
        self._dragging = False
        self.viewport().unsetCursor()
        if not dragged and event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            scene = self.mapToScene(event.position().toPoint())
            ctrl = bool(event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier))
            agent = self.agent_at(scene)
            right_click = event.button() == Qt.MouseButton.RightButton
            location_click = (right_click and ctrl) or (not right_click and agent < 0)
            if location_click:
                row, col = math.floor(scene.y()), math.floor(scene.x())
                if 0 <= row < self.map_height and 0 <= col < self.map_width:
                    self.locationSelected.emit(row, col)
            elif agent >= 0:
                self.agentSelected.emit(agent, ctrl and not right_click)
            elif right_click:
                self.agentSelected.emit(-1, False)
        event.accept()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key.Key_F:
            self.fit_map()
        elif key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal, Qt.Key.Key_Minus):
            self.zoom_at(self.viewport().rect().center(), 1 / 1.25 if key == Qt.Key.Key_Minus else 1.25)
        elif key == Qt.Key.Key_Escape:
            self.agentSelected.emit(-1, False)
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            self._fitted = False
            bar = self.horizontalScrollBar() if key in (Qt.Key.Key_Left, Qt.Key.Key_Right) else self.verticalScrollBar()
            bar.setValue(bar.value() + (-60 if key in (Qt.Key.Key_Left, Qt.Key.Key_Up) else 60))
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fitted:
            self.fit_map()
        self.viewportChanged.emit()
