"""Small raster overview; it never instantiates a duplicate graphics scene."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget


class MiniMap(QWidget):
    def __init__(self, view=None, parent=None) -> None:
        super().__init__(parent)
        self.view = None
        self._thumbnail = QPixmap()
        self.setMinimumSize(100, 70)
        self.setMaximumHeight(240)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Map overview")
        self.setAccessibleDescription("Click or drag to center the main map. Arrow keys pan; F fits map.")
        if view is not None:
            self.set_view(view)

    def sizeHint(self) -> QSize:
        return QSize(240, 150)

    def set_view(self, view) -> None:
        if self.view is not None:
            self.view.viewportChanged.disconnect(self.update)
            self.view.planChanged.disconnect(self._refresh_thumbnail)
        self.view = view
        if view is not None:
            view.viewportChanged.connect(self.update)
            view.planChanged.connect(self._refresh_thumbnail)
        self._refresh_thumbnail()

    def _refresh_thumbnail(self) -> None:
        if self.view is None or self.view.map_image.isNull():
            self._thumbnail = QPixmap()
        else:
            # Bound the retained overview texture even for enormous maps.
            self._thumbnail = QPixmap.fromImage(self.view.map_image.scaled(
                QSize(512, 512), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation))
        self.update()

    def image_rect(self) -> QRectF:
        area = QRectF(self.rect()).adjusted(6, 6, -6, -6)
        if self.view is None or self.view.world_rect.isEmpty():
            return QRectF()
        scale = min(area.width() / self.view.map_width, area.height() / self.view.map_height)
        width, height = self.view.map_width * scale, self.view.map_height * scale
        return QRectF(area.center().x() - width / 2, area.center().y() - height / 2, width, height)

    def viewport_rect(self) -> QRectF:
        image_rect = self.image_rect()
        if image_rect.isEmpty():
            return QRectF()
        visible = self.view.visible_scene_rect()
        sx, sy = image_rect.width() / self.view.map_width, image_rect.height() / self.view.map_height
        return QRectF(image_rect.left() + visible.left() * sx, image_rect.top() + visible.top() * sy,
                      visible.width() * sx, visible.height() * sy)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#e8ecf2"))
        rect = self.image_rect()
        if not self._thumbnail.isNull() and not rect.isEmpty():
            painter.drawPixmap(rect, self._thumbnail, QRectF(self._thumbnail.rect()))
            painter.setPen(QPen(QColor("#c93636"), 1.5))
            painter.setBrush(QColor(220, 38, 38, 25))
            painter.drawRect(self.viewport_rect())
        else:
            painter.setPen(QColor("#667085"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Map overview")

    def _center_at(self, position: QPointF) -> None:
        rect = self.image_rect()
        if self.view is None or rect.isEmpty():
            return
        x = (position.x() - rect.left()) / rect.width() * self.view.map_width
        y = (position.y() - rect.top()) / rect.height() * self.view.map_height
        self.view.center_world(x, y)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._center_at(event.position())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._center_at(event.position())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def keyPressEvent(self, event) -> None:
        if self.view is not None:
            self.view.keyPressEvent(event)
        else:
            super().keyPressEvent(event)
