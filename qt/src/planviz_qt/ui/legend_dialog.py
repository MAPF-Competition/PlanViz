"""A modeless legend for the current palette; file actions belong to the host."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFontDatabase, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QTabWidget, QVBoxLayout, QWidget,
)

from .map_view import MAP_PALETTE


class _LegendSwatch(QWidget):
    """Render the same fixed object shapes and alpha as the map renderer."""

    def __init__(self, section, key, shape, parent=None):
        super().__init__(parent)
        self.section, self.key, self.shape = section, key, shape
        self._legend_palette = None
        self.setFixedSize(48, 30)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_palette(self, palette):
        self._legend_palette = palette
        self.update()

    def color(self, section=None, key=None):
        return QColor(self._legend_palette.color(section or self.section, key or self.key))

    def paintEvent(self, event):
        if self._legend_palette is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Samples use the map's traversable-cell background, even in dark UI
        # themes, so dark headings/indices match their actual map appearance.
        painter.fillRect(self.rect(), QColor(*MAP_PALETTE[1].tolist()))
        center, radius = QPointF(24, 15), 9
        primary = self.color()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(primary)
        if self.shape == "circle":
            painter.drawEllipse(center, radius, radius)
        elif self.shape == "square":
            painter.drawRect(QRectF(15, 6, 18, 18))
        elif self.shape == "diamond":
            painter.drawPolygon(QPolygonF([QPointF(24, 4), QPointF(35, 15),
                                           QPointF(24, 26), QPointF(13, 15)]))
        elif self.shape in ("heading", "outline", "start"):
            fill = self.color("agent", "start_fill" if self.shape == "start" else "idle")
            if self.shape == "start":
                fill.setAlpha(70)
            painter.setBrush(fill)
            painter.drawEllipse(center, radius, radius)
            if self.shape == "heading":
                painter.setBrush(primary)
                painter.drawEllipse(QPointF(30, 15), 2.5, 2.5)
            else:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                outline = self.color("agent", "start_outline") if self.shape == "start" else primary
                painter.setPen(QPen(outline, 1 if self.shape == "start" else 2.4))
                painter.drawEllipse(center, radius, radius)
        elif self.shape in ("line", "arrow"):
            if self.shape == "line":
                primary.setAlpha(170)
            painter.setPen(QPen(primary, 2))
            painter.drawLine(QPointF(5, 15), QPointF(42, 15))
            if self.shape == "arrow":
                painter.drawLine(QPointF(34, 9), QPointF(42, 15))
                painter.drawLine(QPointF(34, 21), QPointF(42, 15))
        elif self.shape == "text":
            painter.setPen(primary)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "7" if self.section == "agent" else "12:2")
        painter.end()


class LegendDialog(QDialog):
    """Display palette changes immediately and emit file-action requests only."""

    loadRequested = Signal()
    reloadRequested = Signal()
    saveRequested = Signal()
    defaultsRequested = Signal()

    def __init__(self, palette, parent=None):
        # A normal QDialog keeps the main map's Space/arrow shortcuts from
        # stealing keyboard input. The map remains usable because it is modeless.
        super().__init__(parent)
        self.setWindowTitle("Colors & legend")
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setMinimumWidth(540)
        self.resize(580, 560)
        self._hex_labels = {}
        self._swatches = {}
        self._alpha = {("agent", "start_fill"): 70, ("path", "executed"): 170}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        intro = QLabel("Shapes identify objects; colors show recorded status.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        source_row = QHBoxLayout()
        source_label = QLabel("Palette:")
        self.source_field = QLineEdit()
        self.source_field.setReadOnly(True)
        self.source_field.setAccessibleName("Current palette source")
        source_label.setBuddy(self.source_field)
        source_row.addWidget(source_label)
        source_row.addWidget(self.source_field, 1)
        layout.addLayout(source_row)
        self.tabs = QTabWidget()
        self.tabs.setAccessibleName("Legend categories")
        layout.addWidget(self.tabs, 1)
        self._build_agents()
        self._build_tasks()
        self._build_paths()
        actions = QHBoxLayout()
        for attribute, label, requested in (
            ("load_button", "Load &YAML…", self.loadRequested),
            ("reload_button", "&Reload", self.reloadRequested),
            ("save_button", "&Save copy…", self.saveRequested),
            ("defaults_button", "Use &defaults", self.defaultsRequested),
        ):
            button = QPushButton(label)
            button.setAutoDefault(False)
            button.clicked.connect(lambda checked=False, signal=requested: signal.emit())
            actions.addWidget(button)
            setattr(self, attribute, button)
        self.load_button.setToolTip("Choose a YAML palette file.")
        self.reload_button.setToolTip("Read changes from the active YAML file, including bundled defaults.")
        self.save_button.setToolTip("Save the current colors to a YAML palette file.")
        self.defaults_button.setToolTip("Restore the built-in colors.")
        layout.addLayout(actions)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.set_palette(palette)

    def _page(self, title):
        contents = QWidget()
        layout = QVBoxLayout(contents)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(contents)
        self.tabs.addTab(scroll, title)
        return layout

    @staticmethod
    def _note(layout, text):
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        layout.addWidget(label)
        return label

    def _cell(self, section, key, shape):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        swatch = _LegendSwatch(section, key, shape)
        swatch.setAccessibleName(f"{section} {key.replace('_', ' ')} color sample")
        color_label = QLabel()
        color_label.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        color_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse |
                                          Qt.TextInteractionFlag.TextSelectableByKeyboard)
        color_label.setAccessibleName(f"{section} {key.replace('_', ' ')} color value")
        layout.addWidget(swatch)
        layout.addWidget(color_label)
        layout.addStretch()
        self._swatches[section, key] = swatch
        self._hex_labels[section, key] = color_label
        return widget

    def _entry(self, layout, label, section, key, shape):
        row = QHBoxLayout()
        text = QLabel(label)
        text.setWordWrap(True)
        row.addWidget(text, 1)
        row.addWidget(self._cell(section, key, shape))
        layout.addLayout(row)

    def _build_agents(self):
        layout = self._page("&Agents")
        self._note(layout, "Normal / idle means no special recorded status; it does not classify moving or waiting.")
        self._note(layout, "Status priority: collision → errand completed → delayed → newly assigned → normal.")
        self._note(layout, "Collision color requires collision highlighting or selected errors. "
                           "New assignment and completion colors mark their recorded time.")
        for label, key, shape in (
            ("Normal / idle", "idle", "circle"),
            ("Newly assigned", "newly_assigned", "circle"),
            ("Delayed", "delayed", "circle"),
            ("Errand completed", "errand_completed", "circle"),
            ("Collision", "collision", "circle"),
            ("Heading dot", "heading", "heading"),
            ("Selected agent outline", "selected_outline", "outline"),
            ("Recorded collision outline", "collision_outline", "outline"),
            ("Start location fill", "start_fill", "start"),
            ("Start location outline", "start_outline", "start"),
        ):
            self._entry(layout, label, "agent", key, shape)
        layout.addStretch()

    def _build_tasks(self):
        layout = self._page("&Tasks && errands")
        self._note(layout, "Squares are final task destinations. Diamonds are intermediate errands. Shapes are fixed.")
        table = QGridLayout()
        table.setHorizontalSpacing(10)
        for column, title in enumerate(("Status", "Task · final stop", "Errand · intermediate")):
            label = QLabel(title)
            label.setWordWrap(True)
            table.addWidget(label, 0, column)
        for row, (label, key) in enumerate((("Unassigned", "unassigned"),
                                           ("Newly assigned", "newly_assigned"),
                                           ("Assigned", "assigned"),
                                           ("Completed", "completed")), 1):
            status = QLabel(label)
            status.setWordWrap(True)
            table.addWidget(status, row, 0)
            table.addWidget(self._cell("task", key, "square"), row, 1)
            table.addWidget(self._cell("errand", key, "diamond"), row, 2)
        layout.addLayout(table)
        overlap = QGroupBox("Shared cells")
        notes = QVBoxLayout(overlap)
        self._note(notes, "One marker and label at an exact shared cell: latest release time wins, "
                          "then highest task ID, then highest stop index.")
        self._note(notes, "Labels use task:errand. A trailing * means more than one distinct task "
                          "shares the cell in the current filters; repeated errands of one task do not add *.")
        self._note(notes, "All task records remain in Inspector.")
        layout.addWidget(overlap)
        layout.addStretch()

    def _build_paths(self):
        layout = self._page("&Paths && labels")
        self._entry(layout, "Selected path", "path", "executed", "line")
        self._entry(layout, "Next errand arrow", "path", "remaining_errands", "arrow")
        self._entry(layout, "Agent index", "agent", "index", "text")
        self._entry(layout, "Task label", "task", "index", "text")
        self._entry(layout, "Errand label", "errand", "index", "text")
        self._note(layout, "Agent indices identify agents. Task and errand labels use task:errand, "
                           "with * for overlapping distinct tasks in the current filters.")
        self._note(layout, "Paths use logged execution, or one-step predictions when Show planned states is enabled.")
        self._note(layout, "Selected paths start at the current time and stop at the next unfinished errand. "
                           "The arrow points only to that errand. A brief ring marks newly selected agents.")
        self._note(layout, "Start fills use 70/255 opacity; executed paths use 170/255 opacity. "
                           "Their hex values describe the configured color before blending.")
        layout.addStretch()

    def set_palette(self, palette):
        """Refresh every sample/value without replacing the window or tab state."""
        self._legend_palette = palette
        source = str(palette.source) if palette.source is not None else "Built-in defaults"
        self.source_field.setText(source)
        self.source_field.setToolTip(source)
        self.source_field.setCursorPosition(0)
        for identity, label in self._hex_labels.items():
            color = QColor(palette.color(*identity)).name()
            alpha = self._alpha.get(identity)
            label.setText(f"{color} · {alpha}/255" if alpha is not None else color)
            self._swatches[identity].set_palette(palette)
