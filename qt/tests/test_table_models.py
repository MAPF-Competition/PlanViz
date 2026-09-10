"""Task transitions update exact table rows and preserve proxy filter results."""
import unittest

from PySide6.QtCore import QSortFilterProxyModel

from planviz_qt.domain.models import Task
from planviz_qt.ui.table_models import TaskTableModel


class TaskTableTests(unittest.TestCase):
    def setUp(self):
        self.tasks = (
            Task(10, 2, ((1, 1), (2, 2)), ((4, 3), (8, 5)),
                 ((7, 3, 0), (11, 5, 1))),
            Task(20, 0, ((3, 3),), ((0, 7),), ((25, 7, 0),)),
            Task(30, 4, ((4, 4),), ((4, 9),), ((15, 9, 0),)),
        )
        self.model = TaskTableModel()
        self.model.set_tasks(self.tasks)
        self.changed = []
        self.model.dataChanged.connect(
            lambda start, end, roles: self.changed.append(
                (start.row(), end.row(), start.column(), end.column())))

    def row(self, row=0):
        return tuple(self.model.data(self.model.index(row, col)) for col in range(4))

    def assert_matches_domain(self, time):
        for row, task in enumerate(self.tasks):
            owner = task.assigned_agent(time)
            self.assertEqual(self.row(row), (task.id, "—" if owner is None else owner,
                                            task.state(time),
                                            f"{len(task.completed_stops(time))} / {len(task.stops)}"))

    def test_release_assignment_reassignment_and_multiple_stops(self):
        expected = {
            0: (10, "—", "unreleased", "0 / 2"),
            2: (10, "—", "unassigned", "0 / 2"),
            4: (10, 3, "assigned", "0 / 2"),
            5: (10, 3, "assigned", "0 / 2"),
            7: (10, 3, "assigned", "1 / 2"),
            8: (10, 5, "assigned", "1 / 2"),
            11: (10, 5, "finished", "2 / 2"),
        }
        for time, row in expected.items():
            self.model.set_time(time)
            self.assertEqual(self.row(), row)

    def test_unchanged_ticks_and_assignment_plus_one_do_not_invalidate(self):
        self.model.set_time(4)
        self.changed.clear()
        for time in (4, 5, 6, 5, 4):
            self.model.set_time(time)
            self.assertEqual(self.model.time, time)
        self.assertEqual(self.changed, [])

    def test_only_affected_rows_invalidate_and_task_id_stays_static(self):
        self.model.set_time(2)
        self.assertEqual(self.changed, [(0, 0, 1, 3)])
        self.changed.clear()
        self.model.set_time(4)
        self.assertEqual(self.changed, [(0, 0, 1, 3), (2, 2, 1, 3)])

    def test_adjacent_changed_rows_are_emitted_together(self):
        model = TaskTableModel()
        model.set_tasks((self.tasks[0], self.tasks[2]))
        model.set_time(2)
        changed = []
        model.dataChanged.connect(lambda first, last, roles: changed.append((first.row(), last.row())))
        model.set_time(4)
        self.assertEqual(changed, [(0, 1)])

    def test_backward_and_skipped_times_match_recorded_state(self):
        for time in (26, 4, 11, 1, 8, 0, 100, 3, 25, 24):
            self.model.set_time(time)
            self.assert_matches_domain(time)

    def test_proxy_filter_remains_correct_after_seeks(self):
        proxy = QSortFilterProxyModel()
        proxy.setSourceModel(self.model)
        proxy.setFilterKeyColumn(2)
        for pattern in ("^assigned$", "^finished$", "^unreleased$"):
            proxy.setFilterRegularExpression(pattern)
            state = pattern[1:-1]
            for time in (0, 4, 5, 11, 26, 2, 8, 7):
                self.model.set_time(time)
                actual = [proxy.data(proxy.index(row, 0)) for row in range(proxy.rowCount())]
                expected = [task.id for task in self.tasks if task.state(time) == state]
                self.assertEqual(actual, expected, (pattern, time))

    def test_duplicate_assignment_with_same_owner_has_no_visible_change(self):
        model = TaskTableModel()
        model.set_tasks((Task(0, 0, ((0, 0),), ((0, 1), (3, 1))),))
        changed = []
        model.dataChanged.connect(lambda *args: changed.append(args))
        model.set_time(3)
        self.assertEqual(changed, [])

    def test_replacing_tasks_replaces_transition_index(self):
        self.model.set_time(10)
        self.model.set_tasks((Task(99, 20, ((0, 0),), ((21, 2),)),))
        self.changed.clear()
        self.model.set_time(11)
        self.assertEqual(self.changed, [])
        self.model.set_time(21)
        self.assertEqual(self.row(), (99, 2, "assigned", "0 / 1"))
        self.assertEqual(self.changed, [(0, 0, 1, 3)])


if __name__ == "__main__":
    unittest.main()
