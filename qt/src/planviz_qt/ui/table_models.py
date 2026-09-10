"""Qt adapters; domain records never contain widget references."""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


class RecordTableModel(QAbstractTableModel):
    def __init__(self, headers, parent=None):
        super().__init__(parent)
        self.headers = tuple(headers)
        self.rows = ()
        self.records = ()

    def set_rows(self, rows, records=()):
        rows, records = tuple(tuple(row) for row in rows), tuple(records)
        if rows == self.rows and records == self.records:
            return
        self.beginResetModel()
        self.rows, self.records = rows, records
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.rows):
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return self.rows[index.row()][index.column()]
        if role == Qt.ItemDataRole.UserRole and index.row() < len(self.records):
            return self.records[index.row()]
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.headers[section]
        return None


class TaskTableModel(QAbstractTableModel):
    headers = ("Task", "Agent", "State", "Stops")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tasks = ()
        self.time = 0
        self._change_times = ()
        self._changed_rows = {}

    def set_tasks(self, tasks):
        tasks = tuple(tasks)
        changed_rows = defaultdict(set)
        for row, task in enumerate(tasks):
            for at in (task.release_time, *(at for at, _agent in task.assignments),
                       *(at for at, _agent, _stop in task.completions)):
                changed_rows[at].add(row)
        self.beginResetModel()
        self.tasks = tasks
        self._change_times = tuple(sorted(changed_rows))
        self._changed_rows = {at: tuple(rows) for at, rows in changed_rows.items()}
        self.endResetModel()

    def set_time(self, time):
        previous = self.time
        self.time = time
        if time == previous:
            return
        # A table state changes only when a recorded transition is crossed.
        # This also handles backwards and multi-tick seeks without replaying
        # every intermediate tick or refiltering every task on every frame.
        left = bisect_right(self._change_times, min(previous, time))
        right = bisect_right(self._change_times, max(previous, time))
        candidates = set()
        for at in self._change_times[left:right]:
            candidates.update(self._changed_rows[at])
        changed = [row for row in sorted(candidates)
                   if self._state_values(self.tasks[row], previous)
                   != self._state_values(self.tasks[row], time)]
        # The table has no one-tick newly-assigned color. Assignment + 1
        # therefore needs no invalidation unless another transition occurs.
        first = last = None
        for row in changed:
            if last is not None and row != last + 1:
                self._emit_rows(first, last)
                first = None
            if first is None:
                first = row
            last = row
        if first is not None:
            self._emit_rows(first, last)

    @staticmethod
    def _state_values(task, time):
        return task.assigned_agent(time), task.state(time), len(task.completed_stops(time))

    def _emit_rows(self, first, last):
        self.dataChanged.emit(self.index(first, 1), self.index(last, 3),
                              [Qt.ItemDataRole.DisplayRole])

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.tasks)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 4

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.tasks):
            return None
        task = self.tasks[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return task
        if role == Qt.ItemDataRole.DisplayRole:
            column = index.column()
            if column == 0:
                return task.id
            if column == 1:
                agent = task.assigned_agent(self.time)
                return "—" if agent is None else agent
            if column == 2:
                return task.state(self.time)
            if column == 3:
                return f"{len(task.completed_stops(self.time))} / {len(task.stops)}"
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.headers[section]
        return None
