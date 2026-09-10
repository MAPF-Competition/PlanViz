"""Readable solution summaries with separately inspectable source metadata."""
from __future__ import annotations

from numbers import Real

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QGridLayout, QGroupBox, QHeaderView,
    QLabel, QLineEdit, QScrollArea, QSizePolicy, QTabWidget, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)


def display_value(value):
    if value is None:
        return "Not provided"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, Real):
        return f"{value:,}"
    if isinstance(value, (dict, list, tuple)):
        return f"{len(value):,} {'fields' if isinstance(value, dict) else 'items'}"
    return str(value)


def _label(text, *, size=None, bold=False):
    label = QLabel(str(text))
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse |
                                  Qt.TextInteractionFlag.TextSelectableByKeyboard)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    font = label.font()
    if size:
        font.setPointSizeF(size)
    font.setBold(bold)
    label.setFont(font)
    return label


class SolutionDetailsDialog(QDialog):
    def __init__(self, plan, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Solution details")
        self.setMinimumSize(620, 480)
        self.resize(760, 760)
        self.setStyleSheet("""
            QFrame[metric="true"] {
                background: palette(base); border: 1px solid palette(mid);
                border-radius: 9px;
            }
            QGroupBox { font-weight: bold; margin-top: 12px; padding-top: 12px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 14)
        layout.setSpacing(14)
        layout.addWidget(_label(plan.map.name or "Unnamed map", size=23, bold=True))
        layout.addWidget(_label(f"{plan.version}  ·  {plan.action_model}  ·  {plan.time_unit.capitalize()} timeline"))

        self.tabs = QTabWidget()
        self.tabs.setAccessibleName("Solution information categories")
        layout.addWidget(self.tabs, 1)
        page = QWidget()
        overview = QVBoxLayout(page)
        overview.setContentsMargins(12, 16, 12, 16)
        overview.setSpacing(16)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, "&Overview")

        blocked = int(np.count_nonzero(plan.map.grid == 0))
        self.metrics = {}
        cards = QGridLayout()
        cards.setSpacing(10)
        for column, (name, value, caption) in enumerate((
            ("Agents loaded", f"{plan.team_size:,}", "Current view"),
            ("Map dimensions", f"{plan.map.width:,} × {plan.map.height:,}", "Width × height"),
            ("Traversable cells", f"{plan.map.grid.size - blocked:,}", "Available terrain"),
            ("Obstacle cells", f"{blocked:,}", "Blocked terrain"),
        )):
            card = QFrame()
            card.setProperty("metric", True)
            inner = QVBoxLayout(card)
            inner.setContentsMargins(12, 12, 12, 12)
            inner.addWidget(_label(name))
            number = _label(value, size=21, bold=True)
            number.setAccessibleName(name)
            self.metrics[name] = number
            inner.addWidget(number)
            inner.addWidget(_label(caption, size=10))
            cards.addWidget(card, 0, column)
            cards.setColumnStretch(column, 1)
        overview.addLayout(cards)

        self.fields = {}
        timing, timing_rows = self._section("Timeline")
        self._row(timing_rows, "Time unit", plan.time_unit)
        self._row(timing_rows, "Maximum time", f"{plan.max_time:,} {plan.time_unit}s")
        self._row(timing_rows, "Ticks per step", plan.ticks_per_step)
        self.fields["Ticks per step"].setToolTip(
            "Ticks required for one cell move or a 90-degree turn; independent of playback speed.")
        if "agentMaxCounter" in plan.metadata:
            self._row(timing_rows, "Agent max counter", plan.metadata["agentMaxCounter"], "agentMaxCounter")
        overview.addWidget(timing)

        results, result_rows = self._section("Reported results")
        self._row(result_rows, "Tasks finished", plan.metadata.get("numTaskFinished"), "numTaskFinished")
        makespan_key = "makespanTicks" if "makespanTicks" in plan.metadata else "makespan"
        self._row(result_rows, "Makespan (ticks)" if makespan_key == "makespanTicks" else "Makespan",
                  plan.metadata.get(makespan_key), makespan_key)
        for label, key in (("Planner errors", "numPlannerErrors"),
                           ("Schedule errors", "numScheduleErrors"),
                           ("Entry timeouts", "numEntryTimeouts")):
            self._row(result_rows, label, plan.metadata.get(key), key)
        overview.addWidget(results)
        overview.addWidget(_label("Reported results describe the input solution, including agents omitted from the current view.", size=10))

        files, file_rows = self._section("Input files")
        self._path_row(file_rows, "Solution", plan.metadata.get("source"))
        self._path_row(file_rows, "Map", plan.map.source)
        if "outputSegmentSize" in plan.metadata:
            self._row(file_rows, "Output segment size", plan.metadata["outputSegmentSize"], "outputSegmentSize")
        overview.addWidget(files)

        warnings = plan.metadata.get("warnings", ())
        if warnings:
            warning_box, warning_rows = self._section("Input warnings")
            for index, warning in enumerate(warnings if isinstance(warnings, (list, tuple)) else [warnings], 1):
                self._row(warning_rows, str(index), warning)
            overview.addWidget(warning_box)
        else:
            overview.addWidget(_label("No input warnings."))
        overview.addStretch()

        source_page = QWidget()
        source_layout = QVBoxLayout(source_page)
        source_layout.setContentsMargins(12, 12, 12, 12)
        source_layout.addWidget(_label("Original metadata fields. Expand a collection to inspect its contents."))
        self.metadata_tree = QTreeWidget()
        self.metadata_tree.setHeaderLabels(["Field", "Value"])
        self.metadata_tree.setAccessibleName("Source metadata")
        self.metadata_tree.setAlternatingRowColors(True)
        self.metadata_tree.setUniformRowHeights(True)
        self.metadata_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.metadata_tree.setColumnWidth(0, 230)
        self.metadata_tree.itemExpanded.connect(self._expand)
        for key, value in plan.metadata.items():
            self._metadata_item(self.metadata_tree, str(key), value)
        source_layout.addWidget(self.metadata_tree, 1)
        self.tabs.addTab(source_page, "&Source metadata")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _section(title):
        group = QGroupBox(title)
        grid = QGridLayout(group)
        grid.setContentsMargins(14, 12, 14, 12)
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(8)
        grid.setColumnMinimumWidth(0, 145)
        grid.setColumnStretch(1, 1)
        return group, grid

    def _row(self, grid, name, value, key=None):
        row = grid.rowCount()
        caption = _label(name)
        field = _label(display_value(value))
        field.setAccessibleName(name)
        if key:
            caption.setToolTip(key)
            field.setToolTip(key)
        grid.addWidget(caption, row, 0)
        grid.addWidget(field, row, 1)
        self.fields[name] = field

    def _path_row(self, grid, name, value):
        row = grid.rowCount()
        caption = QLabel(name)
        field = QLineEdit(str(value) if value else "Not provided")
        field.setReadOnly(True)
        field.setAccessibleName(f"{name} file path")
        field.setToolTip(field.text())
        field.setCursorPosition(0)
        caption.setBuddy(field)
        grid.addWidget(caption, row, 0)
        grid.addWidget(field, row, 1)

    @staticmethod
    def _metadata_item(parent, key, value):
        item = QTreeWidgetItem(parent, [key, display_value(value)])
        item.setToolTip(1, display_value(value))
        if isinstance(value, (dict, list, tuple)) and value:
            item.setData(0, Qt.ItemDataRole.UserRole, value)
            item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
        return item

    def _expand(self, item):
        value = item.data(0, Qt.ItemDataRole.UserRole)
        if value is None or item.childCount():
            return
        entries = value.items() if isinstance(value, dict) else enumerate(value)
        for key, child in entries:
            self._metadata_item(item, str(key), child)
        item.setData(0, Qt.ItemDataRole.UserRole, None)
