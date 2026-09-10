"""Bounded raster text cache for frequently repainted, screen-sized labels."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainter, QPixmap


class RasterTextCache:
    def __init__(self, max_bytes=96 * 1024 * 1024):
        self.max_bytes = max_bytes
        self.bytes_used = 0
        self._style = None
        self._pixmaps = {}

    def clear(self):
        self._pixmaps.clear()
        self.bytes_used = 0
        self._style = None

    def configure(self, font, color, dpr):
        key = font.toString(), color.rgba(), float(dpr)
        if key != self._style:
            self.clear()
            self._style = key

    def get(self, key, text, font, color, dpr):
        if key in self._pixmaps:
            return self._pixmaps[key]
        size = text.size()
        width = max(1, math.ceil((size.width()+2) * dpr))
        height = max(1, math.ceil((size.height()+2) * dpr))
        cost = width*height*4
        # Retain the useful working set instead of evicting it on every frame
        # when more labels than the budget permits are simultaneously visible.
        if self.bytes_used + cost > self.max_bytes:
            return None
        pixmap = QPixmap(width, height)
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setFont(font)
        painter.setPen(color)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.drawStaticText(QPointF(1, 1), text)
        painter.end()
        self._pixmaps[key] = pixmap
        self.bytes_used += cost
        return pixmap
