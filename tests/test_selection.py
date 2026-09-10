"""Path preview equivalence, reuse, and bounded memory across seeks."""
from dataclasses import replace
from unittest.mock import patch
import unittest

import numpy as np

from planviz_qt.domain.models import MapData, PlanData, Task
from planviz_qt.domain.paths import PathStore, MotionSequence
from planviz_qt.domain.analytics import AnalyticsIndex
from planviz_qt.domain.selection import SelectedPathService


def fixture(actual, planned=None, ticks=1, model='MAPF_T'):
    paths = PathStore(np.array([[5., 5., -1. if model == 'MAPF' else 0.]]),
                      [actual], [planned] if planned else None, ticks_per_step=ticks, action_model=model)
    return PlanData(MapData(np.ones((20, 20), np.uint8)), paths, (), (), (), {}, {},
                    'test', model, 'tick', ticks, paths.max_time)


def assert_same_route(test, dense, sparse):
    # Match the directed route in order, including loops and reversals.
    segments = np.diff(sparse[:, :2], axis=0)
    test.assertAlmostEqual(float(np.linalg.norm(np.diff(dense[:, :2], axis=0), axis=1).sum()),
                           float(np.linalg.norm(segments, axis=1).sum()), places=5)
    at = 0
    for point in dense[:, :2]:
        if not len(segments):
            np.testing.assert_allclose(point, sparse[0, :2], atol=1e-6)
            continue
        while at < len(segments):
            origin, vector = sparse[at, :2], segments[at]
            fraction = np.dot(point-origin, vector) / np.dot(vector, vector)
            if -1e-6 <= fraction <= 1+1e-6 and np.allclose(origin+fraction*vector, point, atol=1e-6):
                break
            at += 1
        test.assertLess(at, len(segments), 'Path skipped a turn or changed traversal order')


class SelectionTests(unittest.TestCase):
    def test_turns_waits_reversals_and_one_step_plans_survive_block_clipping(self):
        rng = np.random.default_rng(7)
        for model in ('MAPF', 'MAPF_T'):
            alphabet = list('UDRLW' if model == 'MAPF' else 'FRCW')
            actual = MotionSequence(tuple(rng.choice(alphabet, 160)), tuple(map(int, rng.integers(1, 14, 160))))
            planned = MotionSequence(tuple(rng.choice(alphabet, 160)), tuple(map(int, rng.integers(1, 14, 160))))
            for ticks in (1, 3, 10):
                plan = fixture(actual, planned, ticks, model)
                service = SelectedPathService(plan, AnalyticsIndex(plan), max_states=90, block_size=32)
                for prediction in (False, True):
                    for time in (0, 1, 31, 32, 33, 200, 100, plan.max_time):
                        with self.subTest(model=model, ticks=ticks, planned=prediction, time=time):
                            preview = service.preview(0, time, plan.max_time, planned=prediction)
                            dense = plan.paths.trajectory(0, time, preview.end, planned=prediction)
                            assert_same_route(self, dense, preview.points)
                            self.assertFalse(preview.points.flags.writeable)

    def test_long_runs_reuse_samples_and_keep_memory_bounded(self):
        plan = fixture(MotionSequence(('F',), (10**9,)))
        service = SelectedPathService(plan, AnalyticsIndex(plan), cache_size=3)
        with patch.object(plan.paths, 'trajectory', wraps=plan.paths.trajectory) as decode:
            for time in range(100):
                preview = service.preview(0, time, plan.max_time)
                self.assertEqual(len(preview.points), 2)
                self.assertEqual(preview.end-time+1, 2000)
            self.assertEqual(decode.call_count, 1)
            for time in (10000, 20000, 30000, 0):
                service.preview(0, time, plan.max_time, planned=True)
        self.assertLessEqual(service.cache_entries, 3)
        self.assertLess(service.cache_bytes, 500_000)

    def test_first_arrival_task_change_and_backwards_seek(self):
        plan = fixture(MotionSequence(('F', 'R', 'F'), (8, 1, 8)))
        task = Task(2, 0, ((5, 8), (10, 13)), ((0, 0),), ((4, 0, 0), (14, 0, 1)))
        plan = replace(plan, tasks=(task,))
        service = SelectedPathService(plan, AnalyticsIndex(plan))
        self.assertEqual(service.preview(0, 0, 17).end, 3)
        self.assertEqual(service.preview(0, 4, 17).end, 14)
        self.assertEqual(service.preview(0, 1, 17).end, 3)

    def test_zero_length_and_limited_playback_range(self):
        plan = fixture(MotionSequence((), ()))
        service = SelectedPathService(plan, AnalyticsIndex(plan))
        for planned in (False, True):
            self.assertFalse(service.preview(0, 0, 0, planned=planned).has_movement)
        plan = fixture(MotionSequence(('F',), (100,)))
        service = SelectedPathService(plan, AnalyticsIndex(plan))
        preview = service.preview(0, 20, 25)
        self.assertEqual(preview.end, 25)
        np.testing.assert_allclose(preview.points[-1], plan.paths.positions(25)[0])
