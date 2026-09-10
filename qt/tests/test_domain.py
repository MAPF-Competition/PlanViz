"""Behavioral checks for the GUI-independent loader and compressed path store."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from planviz_qt.domain.paths import MotionSequence, PathStore
from planviz_qt.io.loader import LoadCancelled, PlanLoadError, load_plan
from planviz_qt.converters.motions import parse_motion_sequence


ROOT = Path(__file__).resolve().parents[2]


def sequence(text, **kwargs):
    return parse_motion_sequence(text, **kwargs)


class PathStoreTests(unittest.TestCase):
    def test_integer_actions_and_short_agent_clamping(self):
        store = PathStore(np.array([[3, 4, 0], [2, 2, 1]]),
                          [sequence("F,F,R,F,C,W"), sequence("F")])
        np.testing.assert_allclose(store.positions(0), [[3, 4, 0], [2, 2, 1]])
        np.testing.assert_allclose(store.positions(4), [[4, 6, 3], [1, 2, 1]])
        np.testing.assert_allclose(store.positions(100), [[4, 6, 0], [1, 2, 1]])
        self.assertFalse(store.positions(1).flags.writeable)

    def test_fractional_rotation_and_forward_run_boundaries(self):
        motions = sequence("[(0,0,0,0,0):(R 3,F 6,C 3,F 3)]", tick=True)
        store = PathStore(np.array([[0, 0, 0]]), [motions], ticks_per_step=3)
        np.testing.assert_allclose(store.positions(1), [[0, 0, 11 / 3]], atol=1e-6)
        np.testing.assert_allclose(store.positions(3), [[0, 0, 3]])
        np.testing.assert_allclose(store.positions(9), [[2, 0, 3]], atol=1e-6)
        np.testing.assert_allclose(store.positions(12), [[2, 0, 0]], atol=1e-6)
        np.testing.assert_allclose(store.positions(15), [[2, 1, 0]], atol=1e-6)

    def test_plans_are_one_step_predictions_of_actual_previous_state(self):
        store = PathStore(np.array([[0, 0, 0]]), [sequence("F,F,F")], [sequence("R,R,R")])
        np.testing.assert_allclose(store.positions(2, planned=True), [[0, 1, 3]])
        np.testing.assert_allclose(store.positions(3, planned=True), [[0, 2, 3]])
        np.testing.assert_allclose(store.positions(99, planned=True), [[0, 2, 3]])

    def test_short_planner_path_clamps_its_last_prediction(self):
        store = PathStore(np.array([[0, 0, 0]]), [sequence("F,F,F")], [sequence("R")])
        np.testing.assert_allclose(store.positions(3, planned=True), [[0, 0, 3]])

    def test_mapf_coordinate_convention(self):
        store = PathStore(np.array([[1, 1, -1]]), [sequence("U,R,D,L", action_model="MAPF")],
                          action_model="MAPF")
        np.testing.assert_allclose(store.positions(1), [[2, 1, -1]])
        np.testing.assert_allclose(store.positions(4), [[1, 1, -1]])

    def test_empty_planned_and_actual_paths(self):
        store = PathStore(np.array([[1, 2, 0]]), [sequence("")], [sequence("")], max_time=20)
        np.testing.assert_allclose(store.positions(20), [[1, 2, 0]])
        np.testing.assert_allclose(store.positions(20, planned=True), [[1, 2, 0]])

    def test_long_runs_and_cache_do_not_allocate_tick_histories(self):
        store = PathStore(np.array([[0, 0, 0]]), [MotionSequence(("F",), (10**9,))])
        initial_bytes = store.storage_bytes
        for at in range(100):
            store.positions(at)
        self.assertLessEqual(store.storage_bytes - initial_bytes, 4 * 3 * 8)
        self.assertLess(store.storage_bytes, 1000)
        trajectory = store.trajectory(0, 0, 10**9, max_points=100)
        self.assertEqual(trajectory.shape, (100, 3))
        np.testing.assert_allclose(trajectory[-1], [0, 10**9, 0])

    def test_zero_agents(self):
        store = PathStore(np.empty((0, 3)), [])
        self.assertEqual(store.positions(0).shape, (0, 3))

    def test_rle_coalescing_and_chunk_validation(self):
        run = sequence("[(0,1,2,0,0):(F 3)][(3,1,2,0,0):(F 2,W 0,T 2)]", tick=True)
        self.assertEqual(run.actions, ("F", "W"))
        self.assertEqual(run.durations, (5, 2))
        with self.assertRaisesRegex(ValueError, "contiguous"):
            sequence("[(1,0,0,0,0):(F 1)]", tick=True)
        with self.assertRaisesRegex(ValueError, "unsupported"):
            sequence("F,X")
        with self.assertRaisesRegex(ValueError, "negative"):
            sequence("[(0,0,0,0,0):(W -1)]", tick=True)


class LoaderTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.folder = Path(self.directory.name)
        self.map = self.folder / "small.map"
        self.map.write_text("type octile\nheight 2\nwidth 3\nmap\n...\n.@E\n")

    def load(self, data, **kwargs):
        source = self.folder / "plan.json"
        source.write_text(json.dumps(data))
        return load_plan(self.map, source, **kwargs)

    @staticmethod
    def basic():
        return {"version": "2024 LoRR", "actionModel": "MAPF_T", "teamSize": 4,
                "start": [[0, 0, "E"]] * 4, "actualPaths": ["F,W"] * 4,
                "makespan": 2}

    def test_optional_fields_and_metadata(self):
        plan = self.load(self.basic())
        self.assertEqual((plan.map.width, plan.map.height), (3, 2))
        self.assertEqual(plan.map.grid.dtype, np.uint8)
        self.assertEqual(plan.tasks, ())
        self.assertEqual(plan.events, ())
        self.assertEqual(plan.map.grid[1, 1], 0)
        self.assertNotIn("actualPaths", plan.metadata)
        np.testing.assert_equal(plan.paths.positions(1), plan.paths.positions(1, planned=True))

    def test_all_same_tick_conflicts_and_merged_delays(self):
        data = self.basic()
        data["errors"] = [[0, 1, 1, "first"], [2, 3, 1, "second"]]
        data["delayIntervals"] = [[[0, 20], [5, 6], [21, 25]], [], [], []]
        plan = self.load(data)
        self.assertEqual(plan.conflict_agents(1), frozenset({0, 1, 2, 3}))
        self.assertEqual(plan.delays[0], ((0, 25),))
        self.assertEqual(plan.delayed_agents(10), frozenset({0}))

    def test_sequential_tasks_and_completion_semantics(self):
        data = self.basic()
        data.update(tasks=[[3, 0, [0, 1, 0, 2]]], actualSchedule=["0:3", "", "", ""],
                    events=[[1, 0, 3, 1], [2, 0, 3, 2]])
        plan = self.load(data)
        self.assertEqual([event.kind for event in plan.events],
                         ["assigned", "errand_finished", "task_finished"])
        self.assertEqual(plan.tasks[0].state(1), "assigned")
        self.assertEqual(plan.tasks[0].state(2), "finished")
        self.assertEqual(len({event.id for event in plan.events}), 3)

    def test_legacy_2023_format(self):
        data = {"actionModel": "MAPF", "teamSize": 1, "start": [[0, 0, "N/A"]],
                "actualPaths": ["R,R"], "tasks": [[0, 0, 2]],
                "events": [[[0, 0, "assigned"], [0, 2, "finished"]]], "makespan": 2}
        plan = self.load(data)
        self.assertEqual(plan.version, "2023 LoRR")
        self.assertEqual(plan.tasks[0].state(2), "finished")
        np.testing.assert_allclose(plan.paths.positions(2), [[0, 2, -1]])

    def test_event_ids_survive_agent_filtering(self):
        data = self.basic()
        data.update(tasks=[[0, 0, [0, 1]], [1, 0, [0, 2]]],
                    actualSchedule=["0:0", "0:1", "", ""],
                    events=[[1, 1, 1, 1], [2, 0, 0, 1]])
        full = self.load(data)
        filtered = self.load(data, team_size=1)
        self.assertEqual([event.id for event in full.events if event.agent_id == 0],
                         [event.id for event in filtered.events])

    def test_progress_cancellation_and_helpful_validation(self):
        updates = []
        self.load(self.basic(), progress=lambda percent, message: updates.append(percent))
        self.assertEqual((updates[0], updates[-1]), (0, 100))
        with self.assertRaises(LoadCancelled):
            self.load(self.basic(), cancelled=lambda: True)
        data = self.basic()
        data["actualPaths"][2] = "X"
        with self.assertRaisesRegex(PlanLoadError, r"actualPaths\[2\].*unsupported"):
            self.load(data)

    def test_all_twelve_existing_fixtures(self):
        pairs = {"warehouse_small_2023.json": "warehouse_small.map",
                 "warehouse_small_2024.json": "warehouse_small.map",
                 "warehouse_small_2026.json": "warehouse_small.map",
                 "random_200output.json": "random-32-32-20.map",
                 "mapf_plan_example.json": "random-32-32-20.map"}
        fixtures = [(ROOT / "example" / map_name, ROOT / "example" / plan_name)
                    for plan_name, map_name in pairs.items()]
        maps = {"maze": "maze-32-32-2.map", "room": "room-64-64-16.map",
                "fulfill": "warehouse_long_corridor_large.map", "orz": "orz900d.map",
                "bos": "Boston_0_256.map", "iron": "scene_mp_2p_01.map",
                "random": "random-64-64-10.map"}
        fixtures += [(ROOT / "example/LoRR2026/maps" / maps[path.name.split("-")[0]], path)
                     for path in sorted((ROOT / "example/LoRR2026/outputs").glob("*.json"))]
        self.assertEqual(len(fixtures), 12)
        for map_path, plan_path in fixtures:
            with self.subTest(plan=plan_path.name):
                plan = load_plan(map_path, plan_path)
                snapshot = plan.paths.positions(min(10, plan.max_time))
                self.assertEqual(snapshot.shape, (plan.team_size, 3))
                self.assertTrue(np.all(np.isfinite(snapshot)))
                self.assertNotIn("actualPaths", plan.metadata)


if __name__ == "__main__":
    unittest.main()
