"""Application composition: menus, inspectable records, and a shared timeline."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import math

import numpy as np
from PySide6.QtCore import QSignalBlocker, QSortFilterProxyModel, QTimer, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDockWidget, QFileDialog, QFormLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QSlider, QSpinBox, QTabWidget, QTableView,
    QVBoxLayout, QWidget,
)

from planviz_qt.application.loading import LoadManager, LoadRequest
from planviz_qt.application.playback import PlaybackController
from planviz_qt.domain.selection import SelectedPathService
from planviz_qt.palette import Palette, load_palette, save_palette
from planviz_qt.ui.map_view import MapView
from planviz_qt.ui.minimap import MiniMap
from planviz_qt.ui.table_models import RecordTableModel, TaskTableModel
from planviz_qt.ui.visual_settings import VisualSettingsDialog


PLAYBACK_MULTIPLIERS = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 3.0, 4.0)
DEFAULT_TICKS_PER_SECOND = 10.0
DEFAULT_TIMESTEPS_PER_SECOND = 5.0


@dataclass
class ViewOptions:
    start: int = 0
    end: int | None = None
    fps: int = 60
    speed: float | None = None
    event_limit: int = 100
    grid: bool = True
    agent_ids: bool = True
    task_ids: bool = False
    starts: bool = False
    collisions: bool = False
    hover_location: bool = False


class OpenPlanDialog(QDialog):
    def __init__(self, parent=None, map_path="", plan_path=""):
        super().__init__(parent)
        self.setWindowTitle("Open plan")
        self.setMinimumWidth(580)
        layout = QVBoxLayout(self)
        intro = QLabel("Choose a grid map and a LoRR solution or normalized PlanViz plan.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        layout.addLayout(form)
        self.map_edit = QLineEdit(map_path)
        self.plan_edit = QLineEdit(plan_path)
        for title, edit, pattern in (("Map", self.map_edit, "Grid maps (*.map);;All files (*)"),
                                     ("Solution", self.plan_edit, "Solutions (*.json);;All files (*)")):
            row = QWidget()
            box = QHBoxLayout(row)
            box.setContentsMargins(0, 0, 0, 0)
            box.addWidget(edit, 1)
            browse = QPushButton("Browse…")
            browse.clicked.connect(lambda checked=False, e=edit, p=pattern: self.browse(e, p))
            box.addWidget(browse)
            form.addRow(title, row)
        from planviz_qt.converters.registry import available_formats
        self.input_format = QComboBox()
        self.input_format.addItem("Auto-detect", "auto")
        for identifier, label in available_formats():
            self.input_format.addItem(label, identifier)
        self.input_format.setAccessibleName("Input converter")
        form.addRow("Format", self.input_format)
        self.agents = QSpinBox()
        self.agents.setRange(0, 1_000_000)
        self.agents.setSpecialValueText("All agents")
        form.addRow("Agents to load", self.agents)
        self.error = QLabel("")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def browse(self, edit, pattern):
        name, _ = QFileDialog.getOpenFileName(self, "Select file", edit.text(), pattern)
        if name:
            edit.setText(name)

    def validate(self):
        for name, edit in (("map", self.map_edit), ("solution", self.plan_edit)):
            if not Path(edit.text()).is_file():
                self.error.setText(f"Select an existing {name} file.")
                edit.setFocus()
                return
        self.accept()

    def request(self):
        return LoadRequest(self.map_edit.text(), self.plan_edit.text(),
                           team_size=self.agents.value() or None,
                           input_format=self.input_format.currentData())


class MainWindow(QMainWindow):
    def __init__(self, options: ViewOptions | None = None, *, palette: Palette | None = None):
        super().__init__()
        self.options = options or ViewOptions()
        self.palette = palette if palette is not None else load_palette()
        self.legend_dialog = None
        self.details_dialog = None
        self.plan = self.analytics = None
        self.request = None
        self.selected_agents: set[int] = set()
        self.location_filter = None
        self.marked_conflicts: set[int] = set()
        self._closing = False
        self._busy = False
        self._colors = None
        self.selection_paths = None
        self._path_range = None
        self._dialogs = []
        self._last_time = -1
        self._last_task_markers = None
        self._conflicts_at = defaultdict(set)
        self._finished_at = defaultdict(set)
        self._assigned_at = defaultdict(set)
        self.setWindowTitle("PlanViz · Qt")
        self.resize(1320, 880)
        self.setMinimumSize(900, 620)
        self.map_view = MapView(self)
        self.map_view.set_palette(self.palette)
        self.playback = PlaybackController(self, self.options.fps)
        self.loader = LoadManager(self)
        self._build_canvas()
        self._build_actions()
        self._build_visual_settings()
        self._build_inspector()
        self._build_status()
        self._connect()
        self._set_enabled(False)

    def _build_canvas(self):
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 6, 10, 8)
        self.context = QLabel("Open a map and solution to inspect agents, tasks, and events.")
        self.context.setWordWrap(True)
        layout.addWidget(self.context)
        layout.addWidget(self.map_view, 1)
        self.timeline_widget = QWidget()
        timeline = QVBoxLayout(self.timeline_widget)
        timeline.setContentsMargins(0, 8, 0, 0)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setAccessibleName("Timeline")
        timeline.addWidget(self.slider)
        row = QHBoxLayout()
        self.restart_button = QPushButton("Restart")
        self.prev_button = QPushButton("Previous")
        self.play_button = QPushButton("Play")
        self.next_button = QPushButton("Next")
        for button in (self.restart_button, self.prev_button, self.play_button, self.next_button):
            row.addWidget(button)
        self.time_label = QLabel("Time: —")
        row.addWidget(self.time_label, 1)
        row.addWidget(QLabel("Go to"))
        self.time_edit = QLineEdit("0")
        self.time_edit.setMaximumWidth(100)
        self.time_edit.setAccessibleName("Go to time")
        row.addWidget(self.time_edit)
        self.speed = QComboBox()
        multiplier = self.options.speed if self.options.speed is not None else 1.0
        for value in sorted(set((*PLAYBACK_MULTIPLIERS, multiplier))):
            self.speed.addItem(f"{value}×", value)
        self.speed.setCurrentIndex(self.speed.findData(multiplier))
        self.speed.setAccessibleName("Playback speed multiplier")
        self.speed.setToolTip(f"1.0× = {DEFAULT_TICKS_PER_SECOND:g} ticks per second. "
                              "Choose a slower or faster playback rate.")
        row.addWidget(QLabel("Speed"))
        row.addWidget(self.speed)
        timeline.addLayout(row)
        layout.addWidget(self.timeline_widget)
        self.setCentralWidget(central)

    def _action(self, text, callback, shortcut=None, checkable=False, checked=False):
        action = QAction(text, self)
        action.setCheckable(checkable)
        action.setChecked(checked)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(callback)
        return action

    def _build_actions(self):
        file_menu = self.menuBar().addMenu("&File")
        self.open_action = self._action("Open…", self.open_dialog, "Ctrl+O")
        file_menu.addAction(self.open_action)
        self.export_plan_action = self._action("Export normalized plan…", self.export_plan)
        file_menu.addAction(self.export_plan_action)
        self.export_action = self._action("Export viewport image…", self.export_image, "Ctrl+Shift+S")
        file_menu.addAction(self.export_action)
        file_menu.addSeparator()
        file_menu.addAction(self._action("Close", self.close, "Ctrl+W"))
        view_menu = self.menuBar().addMenu("&View")
        self.fit_action = self._action("Fit map", lambda: self.map_view.fit_map(), "F")
        view_menu.addAction(self.fit_action)
        self.visual_settings_action = self._action("Visual settings…", self.show_visual_settings, "Ctrl+,")
        self.visual_settings_action.setToolTip("Choose map, agent, and task display options.")
        view_menu.addAction(self.visual_settings_action)
        self.palette_action = self._action("Colors && legend…", self.show_palette_legend)
        view_menu.addAction(self.palette_action)
        self.layer_actions = {}
        for name, label, checked in (
            ("grid", "Show grids", self.options.grid),
            ("agent_ids", "Show agent indices", self.options.agent_ids),
            ("headings", "Show agent headings", True),
            ("starts", "Show start locations", self.options.starts),
            ("task_ids", "Show task indices", self.options.task_ids),
            ("collisions", "Show colliding agents", self.options.collisions),
            ("hover_location", "Show location on hover", self.options.hover_location),
        ):
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(checked)
            action.toggled.connect(lambda value, n=name: self._toggle_layer(n, value))
            self.layer_actions[name] = action
        self.overlay_menu = view_menu.addMenu("Analysis overlays")
        self.overlay_menu.setEnabled(False)
        playback_menu = self.menuBar().addMenu("&Playback")
        self.play_action = self._action("Play / pause", self.playback.toggle, "Space")
        playback_menu.addAction(self.play_action)
        self.step_back_action = self._action("Previous", lambda: self.playback.step(-1), "Left")
        self.step_next_action = self._action("Next", lambda: self.playback.step(1), "Right")
        playback_menu.addAction(self.step_back_action)
        playback_menu.addAction(self.step_next_action)
        playback_menu.addAction(self._action("Restart", lambda: self.playback.seek(self.playback.start), "Home"))
        analysis = self.menuBar().addMenu("&Analysis")
        self.productivity_action = self._action("Productivity…", self.show_productivity)
        analysis.addAction(self.productivity_action)
        self.metadata_action = self._action("Solution details…", self.show_metadata)
        analysis.addAction(self.metadata_action)

    def _build_visual_settings(self):
        self.visual_settings = VisualSettingsDialog(self.layer_actions, self)
        self.show_paths = self.visual_settings.show_paths
        self.planned = self.visual_settings.planned
        self.task_mode = self.visual_settings.task_mode
        self.show_paths.toggled.connect(self._refresh_selection)
        self.planned.toggled.connect(self._planned_changed)
        self.task_mode.currentIndexChanged.connect(self._refresh_tasks)
        self.visual_settings.finished.connect(self._visual_settings_closed)
        self.visual_settings.palette_button.clicked.connect(self.show_palette_legend)

    def show_visual_settings(self):
        self.visual_settings.show()
        self.visual_settings.raise_()
        self.visual_settings.activateWindow()

    def _visual_settings_closed(self, *_):
        if self.isVisible() and not self._closing:
            self.activateWindow()
            self.map_view.setFocus()

    def show_palette_legend(self):
        if self.legend_dialog is None:
            from planviz_qt.ui.legend_dialog import LegendDialog
            self.legend_dialog = LegendDialog(self.palette, self)
            self.legend_dialog.loadRequested.connect(self.load_palette_dialog)
            self.legend_dialog.reloadRequested.connect(self.reload_palette)
            self.legend_dialog.saveRequested.connect(self.save_palette_copy)
            self.legend_dialog.defaultsRequested.connect(self.use_default_palette)
            self.legend_dialog.finished.connect(self._visual_settings_closed)
        self.legend_dialog.show()
        self.legend_dialog.raise_()
        self.legend_dialog.activateWindow()

    def apply_palette(self, palette: Palette):
        self.palette = palette
        self.map_view.set_palette(palette)
        self._last_task_markers = None
        self._refresh_colors()
        self._refresh_tasks()
        self._render_frame(self.playback.position)
        if self.legend_dialog is not None:
            self.legend_dialog.set_palette(palette)

    def _load_palette_path(self, path):
        try:
            palette = load_palette(path)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Cannot load palette", str(error))
            return False
        self.apply_palette(palette)
        self.statusBar().showMessage(f"Palette loaded: {palette.source or 'built-in defaults'}", 6000)
        return True

    def load_palette_dialog(self):
        name, _ = QFileDialog.getOpenFileName(
            self, "Load color palette", str(self.palette.source or ""), "YAML palettes (*.yaml *.yml)")
        if name:
            self._load_palette_path(name)

    def reload_palette(self):
        self._load_palette_path(self.palette.source)

    def use_default_palette(self):
        self._load_palette_path(None)

    def save_palette_copy(self):
        suggested = self.palette.source.with_stem(self.palette.source.stem + "_copy") \
            if self.palette.source else "Color_palette.yaml"
        name, _ = QFileDialog.getSaveFileName(
            self, "Save palette copy", str(suggested), "YAML palettes (*.yaml *.yml)")
        if not name:
            return
        path = Path(name)
        if not path.suffix:
            path = path.with_suffix(".yaml")
        try:
            save_palette(self.palette, path)
            saved = load_palette(path)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Cannot save palette", str(error))
            return
        # Make the copy active so edit-file -> Reload works immediately.
        self.apply_palette(saved)
        self.statusBar().showMessage(f"Palette saved: {path}", 6000)

    def _table(self, model):
        table = QTableView()
        table.setModel(model)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setWordWrap(False)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setDefaultSectionSize(26)
        for column in range(model.columnCount() - 1):
            table.setColumnWidth(column, 68)
        return table

    def _build_inspector(self):
        self.dock = QDockWidget("Inspector", self)
        self.dock.setObjectName("inspector")
        self.dock.setMinimumWidth(370)
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.minimap = MiniMap(self.map_view, panel)
        self.minimap.setMinimumHeight(145)
        self.minimap.setMaximumHeight(210)
        layout.addWidget(self.minimap)
        self.summary = QLabel("No solution loaded")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.counters = QLabel("Assigned —   Errands —   Tasks —")
        self.counters.setWordWrap(True)
        layout.addWidget(self.counters)
        agent_row = QHBoxLayout()
        agent_row.addWidget(QLabel("Agent"))
        self.agent_picker = QSpinBox()
        self.agent_picker.setRange(0, 0)
        self.agent_picker.setAccessibleName("Agent to inspect")
        agent_row.addWidget(self.agent_picker, 1)
        focus = QPushButton("Inspect")
        focus.clicked.connect(lambda: self.select_agent(self.agent_picker.value(), False, center=True))
        agent_row.addWidget(focus)
        clear = QPushButton("Clear")
        clear.clicked.connect(self.clear_selection)
        agent_row.addWidget(clear)
        layout.addLayout(agent_row)
        self.selection_label = QLabel("Select an agent on the map. Ctrl-click adds to the selection.")
        self.selection_label.setWordWrap(True)
        layout.addWidget(self.selection_label)
        self.filter_agents = QCheckBox("Filter events to selected agents")
        self.filter_agents.toggled.connect(self._refresh_events)
        layout.addWidget(self.filter_agents)
        self.tabs = QTabWidget()
        self.events_model = RecordTableModel(("Time", "Agent", "Task", "Event"), self)
        self.events_table = self._table(self.events_model)
        self.events_table.doubleClicked.connect(self._event_activated)
        self.tabs.addTab(self.events_table, "Recent events")
        self.conflicts_model = RecordTableModel(("Time", "Agents", "Description"), self)
        self.conflicts_table = self._table(self.conflicts_model)
        self.conflicts_table.doubleClicked.connect(self._conflict_activated)
        self.conflicts_table.selectionModel().selectionChanged.connect(self._conflicts_selected)
        self.tabs.addTab(self.conflicts_table, "Errors")
        self.task_model = TaskTableModel(self)
        self.task_proxy = QSortFilterProxyModel(self)
        self.task_proxy.setSourceModel(self.task_model)
        self.task_proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.task_proxy.setFilterKeyColumn(-1)
        tasks_panel = QWidget()
        tasks_layout = QVBoxLayout(tasks_panel)
        tasks_layout.setContentsMargins(0, 0, 0, 0)
        search = QLineEdit()
        search.setPlaceholderText("Filter task ID, agent, or state…")
        search.setAccessibleName("Filter tasks")
        search.textChanged.connect(self.task_proxy.setFilterFixedString)
        tasks_layout.addWidget(search)
        self.task_table = self._table(self.task_proxy)
        self.task_table.doubleClicked.connect(self._task_activated)
        tasks_layout.addWidget(self.task_table)
        self.tabs.addTab(tasks_panel, "Tasks")
        layout.addWidget(self.tabs, 1)
        hint = QLabel("Double-click an event or error to jump to its time and agent.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.dock.setWidget(panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.resizeDocks([self.dock], [410], Qt.Orientation.Horizontal)

    def _build_status(self):
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setMaximumWidth(160)
        self.progress_bar.hide()
        self.cancel_button = QPushButton("Cancel loading")
        self.cancel_button.clicked.connect(self.loader.cancel)
        self.cancel_button.hide()
        self.coordinates = QLabel("")
        self.statusBar().addPermanentWidget(self.progress_bar)
        self.statusBar().addPermanentWidget(self.cancel_button)
        self.statusBar().addPermanentWidget(self.coordinates)
        self.statusBar().showMessage("Ready")

    def _connect(self):
        self.restart_button.clicked.connect(lambda: self.playback.seek(self.playback.start))
        self.prev_button.clicked.connect(lambda: self.playback.step(-1))
        self.next_button.clicked.connect(lambda: self.playback.step(1))
        self.play_button.clicked.connect(self.playback.toggle)
        self.slider.valueChanged.connect(self._slider_changed)
        self.slider.sliderPressed.connect(self.playback.pause)
        self.time_edit.returnPressed.connect(self._time_entered)
        self.speed.currentIndexChanged.connect(self._speed_changed)
        self.playback.timeChanged.connect(self._time_changed)
        self.playback.frameRequested.connect(self._render_frame)
        self.playback.playingChanged.connect(lambda playing: self.play_button.setText("Pause" if playing else "Play"))
        self.map_view.agentSelected.connect(self.select_agent)
        self.map_view.locationSelected.connect(self.select_location)
        self.map_view.hovered.connect(lambda row, col: self.coordinates.setText(f"Row {row} · Col {col}" if row >= 0 else ""))
        self.loader.loaded.connect(self.accept_result)
        self.loader.failed.connect(self._load_failed)
        self.loader.progress.connect(self.statusBar().showMessage)
        self.loader.busyChanged.connect(self._loading_changed)
        self.loader.drained.connect(self._on_drained)

    def _set_enabled(self, enabled):
        self.timeline_widget.setEnabled(enabled)
        self.dock.setEnabled(enabled)
        for action in (self.fit_action, self.export_action, self.export_plan_action,
                       self.productivity_action, self.metadata_action,
                       self.play_action, self.step_back_action, self.step_next_action):
            action.setEnabled(enabled)

    def open_dialog(self):
        self.playback.pause()
        dialog = OpenPlanDialog(self, self.request.map_path if self.request else "",
                                self.request.plan_path if self.request else "")
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.options.start, self.options.end = 0, None
            self.load(dialog.request())

    def load(self, request: LoadRequest):
        self.request = request
        self.playback.pause()
        self.statusBar().showMessage("Loading map and solution…")
        self.loader.load(request)

    def accept_result(self, result):
        if self._closing:
            return
        for dialog in self._dialogs:
            dialog.close()
            dialog.deleteLater()
        self._dialogs.clear()
        if self.details_dialog is not None:
            self.details_dialog.close()
            self.details_dialog.deleteLater()
            self.details_dialog = None
        self.plan, self.analytics = result.plan, result.analytics
        self.selected_agents.clear()
        self.marked_conflicts.clear()
        self.location_filter = None
        self.selection_paths = SelectedPathService(self.plan, self.analytics)
        self._path_range = None
        self._last_time = -1
        self._last_task_markers = None
        self._conflicts_at.clear()
        self._finished_at.clear()
        self._assigned_at.clear()
        for conflict in self.plan.conflicts:
            self._conflicts_at[conflict.time].update(conflict.agent_ids)
        for event in self.plan.events:
            target = self._assigned_at if event.kind == "assigned" else self._finished_at
            target[event.time].add(event.agent_id)
        self._colors = np.full(self.plan.team_size, self.palette.color("agent", "idle"), dtype="<U7")
        self.map_view.set_plan(self.plan)
        self.map_view.set_options(**{name: action.isChecked() for name, action in self.layer_actions.items()})
        self.map_view.set_selected_agents(set())
        if hasattr(self.map_view, "set_conflict_agents"):
            self.map_view.set_conflict_agents(set().union(*self._conflicts_at.values()) if self._conflicts_at else set())
        self.overlay_menu.clear()
        for overlay in result.overlays:
            self.map_view.set_overlay(overlay.name, overlay, visible=False)
            action = self._action(overlay.name, lambda checked, name=overlay.name:
                                  self.map_view.set_overlay_visible(name, checked), checkable=True)
            self.overlay_menu.addAction(action)
        self.overlay_menu.setEnabled(bool(result.overlays))
        self.agent_picker.setRange(0, max(0, self.plan.team_size-1))
        self.task_model.set_tasks(self.plan.tasks)
        conflicts = sorted(self.plan.conflicts, key=lambda c: c.time)
        self.conflicts_model.set_rows(
            [(c.time, ", ".join(map(str, c.agent_ids)) or "—", c.description) for c in conflicts], conflicts)
        self.tabs.setTabText(1, f"Errors ({len(conflicts):,})")
        blocked = int(np.count_nonzero(self.plan.map.grid == 0))
        self.summary.setText(
            f"{self.plan.team_size:,} agents · {self.plan.map.width:,} × {self.plan.map.height:,}\n"
            f"{self.plan.map.grid.size-blocked:,} traversable · {blocked:,} obstacles\n"
            f"{self.plan.version} · {self.plan.action_model} · {self.plan.ticks_per_step} tick(s) per step")
        warning_count = len(self.plan.metadata.get("warnings", ()))
        if warning_count:
            self.summary.setText(self.summary.text() +
                                 f"\n{warning_count:,} input warnings — see Analysis → Solution details")
        self.setWindowTitle(f"{self.plan.map.name} · {self.plan.team_size:,} agents · PlanViz")
        self.context.setText(f"{self.plan.map.name}  ·  {Path(self.request.plan_path).name if self.request else 'Solution'}")
        self.selection_label.setText("Select an agent on the map. Ctrl-click adds to the selection.")
        end = self.plan.max_time if self.options.end is None else min(self.options.end, self.plan.max_time)
        start = min(self.options.start, end)
        self.slider.setRange(0, min(1_000_000, max(0, end-start)))
        speed = self._base_playback_speed() * float(self.speed.currentData())
        unit = "ticks" if self.plan.time_unit == "tick" else "timesteps"
        self.speed.setToolTip(f"1.0× = {self._base_playback_speed():g} {unit} per second. "
                              "Rendering runs independently of playback speed.")
        self.playback.configure(start, end, speed)
        self._set_enabled(True)
        self.map_view.fit_map()
        if result.warnings:
            self.statusBar().showMessage("Loaded with overlay warnings; see details.")
            QMessageBox.warning(self, "Overlay warnings", "\n".join(result.warnings))
        else:
            self.statusBar().showMessage("Loaded. Space to play, F to fit; select an agent to inspect its path.")

    def _loading_changed(self, busy):
        self._busy = busy
        self.progress_bar.setVisible(busy)
        self.cancel_button.setVisible(busy)
        self._set_enabled(self.plan is not None and not busy)
        if not busy and not self._closing:
            self.statusBar().showMessage("Ready" if self.plan else "Open a map and solution to begin.")

    def _load_failed(self, message):
        if not self._closing:
            QMessageBox.critical(self, "Cannot load solution", message)

    def _slider_changed(self, value):
        if self.plan is not None:
            span = self.playback.end - self.playback.start
            target = self.playback.start + round(value * span / max(1, self.slider.maximum()))
            self.playback.seek(target)

    def _time_entered(self):
        try:
            value = int(self.time_edit.text())
        except ValueError:
            self.statusBar().showMessage("Enter a whole tick or timestep.", 5000)
            self.time_edit.selectAll()
            return
        self.playback.seek(value)
        self.time_edit.setText(str(self.playback.time))

    def _base_playback_speed(self):
        if self.plan is not None and self.plan.time_unit != "tick":
            return DEFAULT_TIMESTEPS_PER_SECOND
        return DEFAULT_TICKS_PER_SECOND

    def _speed_changed(self, *_):
        self.playback.set_speed(self._base_playback_speed() * float(self.speed.currentData()))

    def _time_changed(self, time):
        if self.plan is None:
            return
        self._last_time = time
        label = "Tick" if self.plan.time_unit == "tick" else "Time"
        self.time_label.setText(f"{label}: {time:,} / {self.playback.end:,}")
        if not self.time_edit.hasFocus():
            self.time_edit.setText(str(time))
        with QSignalBlocker(self.slider):
            span = self.playback.end-self.playback.start
            self.slider.setValue(round((time-self.playback.start) * self.slider.maximum()/max(1, span)))
        counts = self.analytics.counts(time)
        self.counters.setText(f"Assigned {counts.get('assigned', 0):,}  ·  "
                             f"Errands {counts.get('errand_finished', 0):,}  ·  "
                             f"Tasks {counts.get('task_finished', 0):,}")
        self._refresh_colors()
        self._refresh_events()
        self._refresh_tasks()
        self.task_model.set_time(time)
        if self.selected_agents and self._path_range != self._selected_path_bounds():
            self._refresh_selected_paths()
        for dialog in self._dialogs:
            if dialog.isVisible():
                dialog.set_time(time)

    def _refresh_colors(self):
        if self.plan is None:
            return
        time = self.playback.time
        colors = {state: self.palette.color("agent", state) for state in
                  ("idle", "newly_assigned", "delayed", "errand_completed", "collision")}
        self._colors[:] = colors["idle"]
        for agent in self._assigned_at.get(time, ()):
            if 0 <= agent < self.plan.team_size:
                self._colors[agent] = colors["newly_assigned"]
        for agent in self.plan.delayed_agents(time):
            if 0 <= agent < self.plan.team_size:
                self._colors[agent] = colors["delayed"]
        for agent in self._finished_at.get(time, ()):
            if 0 <= agent < self.plan.team_size:
                self._colors[agent] = colors["errand_completed"]
        marked = self.marked_conflicts.copy()
        if self.layer_actions['collisions'].isChecked():
            marked.update(self._conflicts_at.get(time, ()))
        for agent in marked:
            if 0 <= agent < self.plan.team_size:
                self._colors[agent] = colors["collision"]
        self.map_view.set_agent_colors(self._colors)

    def _render_frame(self, position):
        if self.plan is None:
            return
        tick = min(self.plan.max_time, math.floor(position))
        positions = self.plan.paths.positions(tick, planned=self.planned.isChecked())
        fraction = position - tick
        if fraction > 0 and tick < self.plan.max_time:
            following = self.plan.paths.positions(tick+1, planned=self.planned.isChecked())
            blended = positions.copy()
            blended[:, :2] += (following[:, :2] - positions[:, :2]) * fraction
            delta = (following[:, 2] - positions[:, 2] + 2) % 4 - 2
            oriented = (positions[:, 2] >= 0) & (following[:, 2] >= 0)
            blended[oriented, 2] = (positions[oriented, 2] + delta[oriented] * fraction) % 4
            positions = blended
            positions.setflags(write=False)
        self.map_view.set_frame(positions, tick, preserve_colors=True)

    def select_agent(self, agent_id, additive=False, *, center=False):
        if self.plan is None:
            return
        if agent_id < 0:
            self.clear_selection()
            return
        if agent_id >= self.plan.team_size:
            return
        self.location_filter = None
        if additive:
            if agent_id in self.selected_agents:
                self.selected_agents.remove(agent_id)
            else:
                self.selected_agents.add(agent_id)
        else:
            self.selected_agents = {agent_id}
        self.agent_picker.setValue(agent_id)
        self._refresh_selection()
        if center:
            self.map_view.center_agent(agent_id)

    def clear_selection(self):
        self.selected_agents.clear()
        self.location_filter = None
        self.marked_conflicts.clear()
        self.conflicts_table.clearSelection()
        self._refresh_selection()
        self._refresh_colors()
        self._render_frame(self.playback.position)

    def select_location(self, row, col):
        if self.plan is None or row < 0 or col < 0:
            return
        self.location_filter = (row, col)
        self.selection_label.setText(f"Events at row {row}, column {col}")
        self._refresh_events()
        self.tabs.setCurrentIndex(0)

    def _refresh_selection(self, *_):
        if self.plan is None:
            return
        self.map_view.set_selected_agents(self.selected_agents)
        names = ", ".join(str(x) for x in sorted(self.selected_agents))
        self.selection_label.setText(f"Selected agents: {names}" if names else "No agent selected")
        self._refresh_selected_paths()
        self._refresh_events()
        self._refresh_tasks()

    def _refresh_selected_paths(self):
        self._path_range = self._selected_path_bounds()
        previews, intervals = {}, []
        if self.show_paths.isChecked():
            for agent in sorted(self.selected_agents):
                preview = self.selection_paths.preview(agent, self.playback.time, self.playback.end,
                                                       planned=self.planned.isChecked())
                if preview.has_movement:
                    previews[agent] = preview
                note = {"assignment": "", "completion": " (target from completion record)",
                        "recording": " (no upcoming errand record)"}[preview.source]
                intervals.append(f"{agent}: {preview.start:,}–{preview.end:,}{note}")
        names = ", ".join(str(agent) for agent in sorted(self.selected_agents))
        text = f"Selected agents: {names}" if names else "No agent selected"
        if intervals:
            text += "\nPath intervals: " + "; ".join(intervals)
            if not previews:
                text += "\nNo movement in the displayed interval."
        self.selection_label.setText(text)
        self.map_view.set_selected_paths(previews)

    def _selected_path_bounds(self):
        start = self.playback.time
        return start, min(self.playback.end, start+self.selection_paths.max_states-1)

    def _planned_changed(self, *_):
        self._refresh_selection()
        self._render_frame(self.playback.position)

    def _refresh_events(self, *_):
        if self.analytics is None:
            return
        events = self.analytics.recent_events(
            self.playback.time, limit=self.options.event_limit,
            agent_ids=self.selected_agents if self.filter_agents.isChecked() and self.selected_agents else None,
            location=self.location_filter)
        self.events_model.set_rows([(e.time, e.agent_id, e.task_id,
                                     e.kind.replace('_', ' ').capitalize()) for e in events], events)

    def _refresh_tasks(self, *_):
        if self.analytics is None:
            return
        mode = self.task_mode.currentData()
        mode = None if mode == "none" else mode
        markers = () if mode is None else self.analytics.task_markers(
            self.playback.time, mode=mode, selected_agents=self.selected_agents)
        # Analytics retains the same list until a task transition or filter
        # change. The moving first arrow follows the frame position at paint
        # time, so neither markers nor sequence geometry need rebuilding here.
        if markers is self._last_task_markers:
            return
        self._last_task_markers = markers
        self.map_view.set_tasks(markers)
        sequences = {}
        if hasattr(self.map_view, "set_task_sequences"):
            for agent in (self.selected_agents if mode is not None else ()):
                context = self.analytics.active_task_context(self.playback.time, agent)
                if not context or context.get("next_stop") is None:
                    context = self.analytics.next_recorded_errand(self.playback.time, agent)
                if context and context.get("next_stop") is not None:
                    current = self.plan.paths.positions(self.playback.time)[agent, :2]
                    sequences[agent] = np.asarray([current, context["next_stop"]], dtype=float)
            self.map_view.set_task_sequences(sequences)

    def _toggle_layer(self, name, value):
        self.map_view.set_options(**{name: value})
        if name == "collisions":
            self._refresh_colors()
            self._render_frame(self.playback.position)

    def _event_activated(self, index):
        event = self.events_model.records[index.row()]
        self.playback.seek(event.time)
        self.select_agent(event.agent_id, False, center=True)

    def _conflict_activated(self, index):
        conflict = self.conflicts_model.records[index.row()]
        self.location_filter = None
        self.playback.seek(conflict.time)
        if conflict.agent_ids:
            self.selected_agents = set(conflict.agent_ids)
            self._refresh_selection()
            self.map_view.center_agent(conflict.agent_ids[0])

    def _conflicts_selected(self, *_):
        self.marked_conflicts = set()
        for index in self.conflicts_table.selectionModel().selectedRows():
            if index.row() < len(self.conflicts_model.records):
                self.marked_conflicts.update(self.conflicts_model.records[index.row()].agent_ids)
        self._refresh_colors()
        self._render_frame(self.playback.position)

    def _task_activated(self, index):
        source_index = self.task_proxy.mapToSource(index)
        task = self.task_model.tasks[source_index.row()]
        agent = task.assigned_agent(self.playback.time)
        if agent is None and task.assignments:
            time, agent = task.assignments[0]
            self.playback.seek(time)
        if agent is not None:
            self.select_agent(agent, False, center=True)
        elif task.stops:
            row, col = task.stops[0]
            self.map_view.centerOn(col+.5, row+.5)
            self.select_location(row, col)

    def show_productivity(self):
        if self.plan is None:
            return
        from planviz_qt.ui.analytics_dialog import ProductivityDialog
        if self._dialogs:
            dialog = self._dialogs[0]
            dialog.set_time(self.playback.time)
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            return
        dialog = ProductivityDialog(self.plan, self.analytics, self)
        self._dialogs.append(dialog)
        dialog.set_range(self.playback.start, self.playback.end)
        dialog.set_time(self.playback.time)
        dialog.show()

    def show_metadata(self):
        if self.plan is None:
            return
        if self.details_dialog is None:
            from planviz_qt.ui.solution_details import SolutionDetailsDialog
            self.details_dialog = SolutionDetailsDialog(self.plan, self)
            self.details_dialog.finished.connect(self._visual_settings_closed)
        self.details_dialog.show()
        self.details_dialog.raise_()
        self.details_dialog.activateWindow()

    def export_plan(self):
        if self.plan is None:
            return
        self.playback.pause()
        stem = Path(self.request.plan_path).stem if self.request else "planviz"
        name, _ = QFileDialog.getSaveFileName(
            self, "Export normalized plan", f"{stem}.normalized.json", "PlanViz plan (*.json)")
        if not name:
            return
        if not Path(name).suffix:
            name += ".json"
        try:
            from planviz_qt.converters.exchange import dump_plan
            dump_plan(self.plan, name)
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.warning(self, "Export failed", f"The normalized plan could not be saved:\n{error}")
        else:
            self.statusBar().showMessage(f"Saved normalized plan: {name}", 6000)

    def export_image(self):
        self.playback.pause()
        name, _ = QFileDialog.getSaveFileName(self, "Export map viewport", "planviz.png", "PNG image (*.png)")
        if name and not self.map_view.viewport().grab().save(name, "PNG"):
            QMessageBox.warning(self, "Export failed", "The image could not be saved to that location.")

    def closeEvent(self, event):
        self._closing = True
        self.playback.pause()
        self.visual_settings.close()
        if self.legend_dialog is not None:
            self.legend_dialog.close()
        if self.details_dialog is not None:
            self.details_dialog.close()
        for dialog in self._dialogs:
            dialog.close()
        if self.loader.pending:
            self._closing = True
            self.loader.cancel()
            self.setEnabled(False)
            self.statusBar().showMessage("Finishing cancellation…")
            event.ignore()
        else:
            event.accept()

    def _on_drained(self):
        if self._closing:
            QTimer.singleShot(0, self.close)
