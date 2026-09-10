"""A reusable, modeless window for map display controls."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QGroupBox, QLabel, QPushButton, QVBoxLayout,
)


class VisualSettingsDialog(QDialog):
    """Apply display changes immediately while leaving the map interactive."""

    def __init__(self, layer_actions, parent=None):
        # A normal dialog has its own shortcut scope. Qt.Tool would let the
        # parent's Space/arrow playback actions steal input from these controls.
        super().__init__(parent)
        self.setWindowTitle("Visual settings")
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        description = QLabel("Choose what appears on the map. Changes apply immediately.")
        description.setWordWrap(True)
        layout.addWidget(description)
        self.layer_checks = {}

        def group(title):
            box = QGroupBox(title)
            contents = QVBoxLayout(box)
            contents.setSpacing(8)
            layout.addWidget(box)
            return contents

        def layer(contents, name, tooltip=None):
            action = layer_actions[name]
            check = QCheckBox(action.text())
            check.setChecked(action.isChecked())
            check.setEnabled(action.isEnabled())
            if tooltip:
                check.setToolTip(tooltip)
            # The action is shared state, including changes made through APIs.
            check.toggled.connect(action.setChecked)
            action.toggled.connect(check.setChecked)
            action.enabledChanged.connect(check.setEnabled)
            contents.addWidget(check)
            self.layer_checks[name] = check

        map_group = group("Map")
        layer(map_group, "grid")
        layer(map_group, "hover_location", "Show row and column beside the pointer while it is over the map.")

        agents = group("Agents")
        layer(agents, "agent_ids", "Show indices at every zoom level. Zoom in to separate crowded labels.")
        layer(agents, "headings")
        layer(agents, "starts")
        layer(agents, "collisions", "Highlight agents involved in recorded conflicts.")
        self.show_paths = QCheckBox("Show selected agent path")
        self.show_paths.setToolTip("Show the recorded path from now to the next unfinished errand.")
        self.show_paths.setChecked(True)
        agents.addWidget(self.show_paths)
        self.planned = QCheckBox("Show planned states")
        self.planned.setToolTip("One-step planned predictions based on the previous actual state.")
        agents.addWidget(self.planned)

        tasks = group("Tasks")
        form = QFormLayout()
        self.task_mode = QComboBox()
        for label, mode in (("Next errand", "next"), ("Assigned tasks", "assigned"),
                            ("All tasks", "all"), ("Hidden", "none")):
            self.task_mode.addItem(label, mode)
        self.task_mode.setCurrentIndex(self.task_mode.findData("assigned"))
        self.task_mode.setAccessibleName("Shown tasks")
        self.task_mode.setToolTip(
            "All tasks includes tasks released by the current time, including completed tasks. "
            "Selecting agents limits task markers to those agents.")
        form.addRow("Shown", self.task_mode)
        tasks.addLayout(form)
        layer(tasks, "task_ids")

        layout.addStretch()
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.palette_button = QPushButton("Colors && legend…")
        self.buttons.addButton(self.palette_button, QDialogButtonBox.ButtonRole.ActionRole)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
