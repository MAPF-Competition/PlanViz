"""Modeless productivity chart with cached series and coalesced time updates."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
    QVBoxLayout,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from ..domain.analytics import AnalyticsIndex
from ..domain.models import PlanData


class ProductivityDialog(QDialog):
    """Plot recorded completion/assignment counts, in the plan's own time units.

    Full-range curves are computed once per metric/mode. Playback only moves a
    dashed current-time line and updates the text summary; requests within a
    60 ms interval coalesce. Closing the dialog stops pending redraws.
    """

    def __init__(self, plan: PlanData, index: AnalyticsIndex, parent=None) -> None:
        super().__init__(parent)
        self.plan = plan
        self.index = index
        self._time = 0
        self._range_start = 0
        self._range_end = plan.max_time
        self._metric = "task_finished"
        self._mode = "cumulative"
        self._x = np.empty(0)
        self._y = np.empty(0)
        self._prefix_max = np.empty(0)
        self.setWindowTitle("Productivity · PlanViz")
        self.setModal(False)
        self.resize(940, 650)

        layout = QVBoxLayout(self)
        title = QLabel("Productivity over time")
        title_font = title.font()
        title_font.setPointSize(title_font.pointSize() + 4)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        explanation = QLabel(
            "Completed errands include the final stop of each task. "
            "The dashed line follows the playback time."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        controls = QHBoxLayout()
        self.metric_combo = QComboBox()
        for label, value in (("Completed tasks", "task_finished"),
                             ("Completed errands", "errand_finished"),
                             ("Task assignments", "assigned")):
            self.metric_combo.addItem(label, value)
        metric_label = QLabel("&Metric")
        metric_label.setBuddy(self.metric_combo)
        self.metric_combo.setAccessibleName("Productivity metric")
        controls.addWidget(metric_label)
        controls.addWidget(self.metric_combo)
        self.mode_combo = QComboBox()
        for label, value in (("Cumulative count", "cumulative"),
                             ("Completions / assignments at each time", "instant"),
                             ("Average throughput", "throughput")):
            self.mode_combo.addItem(label, value)
        mode_label = QLabel("&Display")
        mode_label.setBuddy(self.mode_combo)
        self.mode_combo.setAccessibleName("Productivity display mode")
        self.mode_combo.setToolTip("Average throughput is cumulative count divided by elapsed plan time.")
        controls.addWidget(mode_label)
        controls.addWidget(self.mode_combo, 1)
        self.full_range = QCheckBox("&Full timeline")
        self.full_range.setChecked(True)
        self.full_range.setToolTip("Show the complete recorded plan, including times after the playback cursor.")
        controls.addWidget(self.full_range)
        layout.addLayout(controls)

        self.figure = Figure(figsize=(8, 4), layout="constrained", facecolor="white")
        self.axes = self.figure.add_subplot(111)
        self.axes.set_facecolor("white")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setAccessibleName("Productivity chart; current and total values are also shown below")
        self.canvas.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, 1)
        self._line, = self.axes.plot([], [], color="#176B9B", linewidth=1.8,
                                     label="Recorded plan")
        self._marker = self.axes.axvline(0, color="#374151", linestyle="--",
                                         linewidth=1.3, label="Playback time")
        self.axes.grid(axis="y", alpha=0.2)
        self.axes.legend(loc="upper left", frameon=False)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.summary)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._flush_time)
        self.metric_combo.currentIndexChanged.connect(self._refresh_series)
        self.mode_combo.currentIndexChanged.connect(self._refresh_series)
        self.full_range.toggled.connect(self._refresh_series)
        self._refresh_series()

    def set_time(self, time: int) -> None:
        self._time = min(max(int(time), 0), self.plan.max_time)
        if self.isVisible() and not self._timer.isActive():
            self._timer.start()

    def set_range(self, start: int, end: int | None = None) -> None:
        """Set the playback interval used when Full timeline is unchecked.

        Full timeline always shows the entire recorded plan. The other view
        starts at this interval's first time and ends at the playback cursor.
        """
        end = self.plan.max_time if end is None else int(end)
        start = int(start)
        if not 0 <= start <= end <= self.plan.max_time:
            raise ValueError("Chart range must satisfy 0 <= start <= end <= plan.max_time")
        self._range_start, self._range_end = start, end
        self._refresh_series()

    def _refresh_series(self, *_args) -> None:
        self._metric = self.metric_combo.currentData()
        self._mode = self.mode_combo.currentData()
        start = 0 if self.full_range.isChecked() else self._range_start
        end = self.plan.max_time if self.full_range.isChecked() else self._range_end
        self._x, self._y = self.index.series(self._metric, self._mode, start, end)
        self._prefix_max = np.maximum.accumulate(self._y) if len(self._y) else np.empty(0)
        self._line.set_drawstyle("steps-post" if self._mode == "cumulative" else "default")
        time_label = "Tick" if self.plan.time_unit == "tick" else "Timestep"
        self.axes.set_xlabel(time_label)
        ylabel = (f"Count / {time_label.lower()}" if self._mode == "throughput"
                  else "Count at this time" if self._mode == "instant" else "Cumulative count")
        self.axes.set_ylabel(ylabel)
        self.axes.set_title(self.metric_combo.currentText(), loc="left", fontweight="bold")
        self.note.setText(
            f"Average throughput = cumulative count / elapsed {time_label.lower()}s since {start:,}; zero at that time."
            if self._mode == "throughput" else
            "Counts are derived from recorded events; assignments may include task reassignments."
        )
        self._flush_time(reset_curve=True)

    def _flush_time(self, reset_curve: bool = False) -> None:
        self._timer.stop()
        full = self.full_range.isChecked()
        if full:
            if reset_curve:
                self._line.set_data(self._x, self._y)
                self.axes.set_xlim(0, max(1, self.plan.max_time))
                self.axes.set_ylim(0, max(1.0, float(self._prefix_max[-1]) * 1.08)
                                   if len(self._prefix_max) else 1.0)
        else:
            visible_time = min(max(self._time, self._range_start), self._range_end)
            stop = int(np.searchsorted(self._x, visible_time, side="right"))
            current = self._value_at_time()
            # Appending the current value terminates a sparse series precisely
            # at the cursor, even when no event occurred at the selected time.
            self._line.set_data(np.r_[self._x[:stop], visible_time],
                                np.r_[self._y[:stop], current])
            self.axes.set_xlim(self._range_start, max(self._range_start + 1, visible_time))
            peak = float(self._prefix_max[stop - 1]) if stop else 0.0
            self.axes.set_ylim(0, max(1.0, peak * 1.08, current * 1.08))
        self._marker.set_xdata([self._time, self._time])
        current = self._value_at_time()
        label = "tick" if self.plan.time_unit == "tick" else "timestep"
        value_text = f"{current:.4g}" if self._mode == "throughput" else f"{int(current):,}"
        text = f"At {label} {self._time:,}: {value_text}"
        if full:
            total = self.index.counts(self.plan.max_time)[self._metric]
            text += f"  ·  Total recorded {self.metric_combo.currentText().lower()}: {total:,}"
        self.summary.setText(text)
        self.canvas.draw_idle()

    def _value_at_time(self) -> float:
        count = self.index.counts(self._time)[self._metric]
        if self._mode == "throughput":
            start = 0 if self.full_range.isChecked() else self._range_start
            return count / (self._time - start) if self._time > start else 0.0
        if self._mode == "instant":
            return count - self.index.counts(self._time - 1)[self._metric]
        return float(count)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._flush_time(reset_curve=True)

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)
