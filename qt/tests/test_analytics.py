"""Regression checks for completion accounting and seek-independent task state."""

import unittest
from types import SimpleNamespace

import numpy as np

from planviz_qt.domain.analytics import AnalyticsIndex
from planviz_qt.domain.models import Event, Task


def make_plan():
    tasks = (
        Task(10, 0, ((0, 1), (1, 1)), ((1, 0),), ((3, 0, 0), (5, 0, 1))),
        Task(20, 4, ((2, 2),), ((4, 1), (6, 2)), ((8, 2, 0),)),
        Task(30, 20, ((0, 0),)),
    )
    events = (
        Event(8, 2, 20, "task_finished", 0),
        Event(1, 0, 10, "assigned"),
        Event(6, 2, 20, "assigned"),
        Event(3, 0, 10, "errand_finished", 0),
        Event(4, 1, 20, "assigned"),
        Event(5, 0, 10, "task_finished", 1),
    )
    return SimpleNamespace(tasks=tasks, events=events, max_time=30, time_unit="tick")


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.index = AnalyticsIndex(make_plan())

    def test_final_stop_counts_as_both_errand_and_task(self):
        self.assertEqual(self.index.counts(-1), {
            "assigned": 0, "errand_finished": 0, "task_finished": 0})
        self.assertEqual(self.index.counts(5), {
            "assigned": 2, "errand_finished": 2, "task_finished": 1})
        self.assertEqual(self.index.counts(8), {
            "assigned": 3, "errand_finished": 3, "task_finished": 2})
        # The final stop remains one visible event, not two history rows.
        self.assertEqual(len(self.index.recent_events(8, 100)), 6)

    def test_seek_backwards_restores_counts_and_task_state(self):
        self.index.task_markers(8, "all")
        markers = self.index.task_markers(2, "assigned", {0})
        self.assertEqual([(m["task_id"], m["stop_index"], m["state"]) for m in markers],
                         [(10, 0, "assigned"), (10, 1, "assigned")])
        self.assertEqual(self.index.counts(2)["task_finished"], 0)
        markers = self.index.task_markers(3, "next", {0})
        self.assertEqual([(m["task_id"], m["stop_index"]) for m in markers], [(10, 1)])
        self.assertEqual(self.index.task_markers(5, "next", {0}), [])

    def test_reassignment_removes_previous_agent_ownership(self):
        self.assertEqual(self.index.active_task_context(5, 1)["task_id"], 20)
        self.assertIsNone(self.index.active_task_context(6, 1))
        context = self.index.active_task_context(6, 2)
        self.assertEqual(context["next_stop"], (2, 2))
        self.assertEqual(context["remaining_stops"], ((2, 2),))
        self.assertEqual(self.index.task_markers(6, "assigned", {1}), [])
        self.assertEqual(self.index.task_markers(6, "assigned", {2})[0]["state"], "newlyassigned")

    def test_release_and_completed_stop_visibility(self):
        at_zero = self.index.task_markers(0, "all")
        self.assertEqual({m["task_id"] for m in at_zero}, {10})
        self.assertTrue(all(m["state"] == "unassigned" for m in at_zero))
        at_three = self.index.task_markers(3, "all")
        self.assertEqual([m["state"] for m in at_three], ["finished", "assigned"])
        self.assertNotIn(30, {m["task_id"] for m in self.index.task_markers(19, "all")})
        self.assertIn(30, {m["task_id"] for m in self.index.task_markers(20, "all")})

    def test_markers_distinguish_intermediate_errands_and_final_destinations(self):
        markers = self.index.task_markers(4, "all")
        self.assertEqual([(m["task_id"], m["kind"], m["release_time"]) for m in markers],
                         [(10, "errand", 0), (10, "task", 0), (20, "task", 4)])
        self.assertEqual(markers[0]["state"], "finished")
        self.assertEqual(markers[1]["state"], "assigned")

    def test_new_assignment_color_is_exact_even_between_integer_ticks(self):
        for time, state in ((1, "newlyassigned"), (1.5, "assigned"),
                            (2, "assigned"), (1, "newlyassigned")):
            marker = self.index.task_markers(time, "next", {0})[0]
            self.assertEqual(marker["state"], state)
            self.assertEqual(marker["stop_index"], 0)

    def test_finishing_latest_task_does_not_revive_an_older_assignment(self):
        plan = make_plan()
        plan.tasks = (*plan.tasks, Task(40, 0, ((0, 2),), ((2, 0),), ((4, 0, 0),)))
        index = AnalyticsIndex(plan)
        self.assertEqual(index.task_markers(3, "next", {0})[0]["task_id"], 40)
        # Task 10 still has an unfinished stop, but legacy current-task semantics
        # choose the latest assigned task, rather than reviving earlier work.
        self.assertEqual(index.task_markers(4, "next", {0}), [])
        self.assertEqual(index.task_markers(1, "next", {0})[0]["task_id"], 10)

    def test_history_filters_time_agent_and_physical_stop(self):
        self.assertEqual([e.time for e in self.index.recent_events(5, 2)], [5, 4])
        self.assertEqual([e.time for e in self.index.recent_events(8, 100, {2})], [8, 6])
        self.assertEqual([e.time for e in self.index.recent_events(30, 100, location=(1, 1))], [5, 1])
        self.assertEqual([e.time for e in self.index.recent_events(7, 100, {2}, (2, 2))], [6])
        self.assertEqual(self.index.recent_events(30, 100, set()), [])
        self.assertEqual(self.index.recent_events(30, 0), [])

    def test_series_keeps_boundary_counts_and_zero_gaps(self):
        x, y = self.index.series("errand", "cumulative", start=4, end=9)
        np.testing.assert_array_equal(x, [4, 5, 8, 9])
        np.testing.assert_array_equal(y, [1, 2, 3, 3])
        x, y = self.index.series("task", "instant", end=9)
        samples = dict(zip(x, y))
        self.assertEqual(samples[5], 1)
        self.assertEqual(samples[6], 0)
        self.assertEqual(samples[7], 0)
        self.assertEqual(samples[8], 1)
        x, y = self.index.series("task", "throughput", end=10)
        self.assertEqual(dict(zip(x, y))[0], 0)
        self.assertAlmostEqual(dict(zip(x, y))[10], 0.2)

    def test_large_horizon_does_not_expand_every_tick(self):
        plan = make_plan()
        plan.max_time = 10**9
        index = AnalyticsIndex(plan)
        x, y = index.series("task", "cumulative")
        self.assertLess(len(x), 10)
        self.assertEqual(x[-1], 10**9)
        self.assertEqual(y[-1], 2)
        self.assertFalse(x.flags.writeable)
        self.assertFalse(y.flags.writeable)
        x, _y = index.series("task", "throughput")
        self.assertLess(len(x), 2010)

    def test_empty_plan_and_invalid_queries(self):
        index = AnalyticsIndex(SimpleNamespace(tasks=(), events=(), max_time=0))
        x, y = index.series("task")
        np.testing.assert_array_equal(x, [0])
        np.testing.assert_array_equal(y, [0])
        self.assertEqual(index.task_markers(0), [])
        self.assertEqual(index.recent_events(0, 10), [])
        with self.assertRaises(ValueError):
            index.series("unknown")
        with self.assertRaises(ValueError):
            index.series("task", start=3, end=2)

    def test_indexing_checks_cancellation_during_work(self):
        with self.assertRaises(InterruptedError):
            AnalyticsIndex(make_plan(), cancelled=lambda: True)
        calls = 0

        def cancel_after_starting():
            nonlocal calls
            calls += 1
            return calls >= 3

        with self.assertRaises(InterruptedError):
            AnalyticsIndex(make_plan(), cancelled=cancel_after_starting)
        self.assertEqual(calls, 3)


if __name__ == "__main__":
    unittest.main()
