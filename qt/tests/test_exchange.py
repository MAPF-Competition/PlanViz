"""Interchange round trips and validation independent of Qt or a source adapter."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from planviz_qt.domain.models import Conflict, Event, MapData, PlanData, Task
from planviz_qt.domain.paths import MotionSequence, PathStore
from planviz_qt.converters.exchange import decode_document, dump_plan, plan_to_document
from planviz_qt.io.loader import load_plan


ROOT = Path(__file__).resolve().parents[2]


class ExchangeTests(unittest.TestCase):
    def setUp(self):
        self.map = MapData(np.ones((8, 10), dtype=np.uint8))

    def plan(self):
        paths = PathStore(np.array([[3, 3, 0], [4, 4, 1]]),
                          [MotionSequence(("F", "R", "W"), (6, 3, 2)),
                           MotionSequence(("W",), (4,))],
                          [MotionSequence(("R",), (9,)), MotionSequence(("F",), (2,))],
                          ticks_per_step=3, max_time=20)
        task = Task(7, 1, ((3., 4.), (3., 5.)), ((1, 0), (3, 1)), ((4, 1, 0), (8, 0, 1)))
        return PlanData(self.map, paths, (task,),
                        (Event(1, 0, 7, "assigned", id="first"),
                         Event(4, 1, 7, "errand_finished", 0, "second"),
                         Event(8, 0, 7, "task_finished", 1, "third")),
                        (Conflict(5, (0, 1), "vertex", 7), Conflict(7, (), "timeout")),
                        {0: ((1, 3), (10, 12))}, {"warnings": (), "solver": "example"},
                        "2026 LoRR", "MAPF_T", "tick", 3, 20)

    def assert_equivalent(self, before, after):
        self.assertEqual((before.version, before.action_model, before.time_unit,
                          before.ticks_per_step, before.max_time, before.team_size),
                         (after.version, after.action_model, after.time_unit,
                          after.ticks_per_step, after.max_time, after.team_size))
        self.assertEqual(before.tasks, after.tasks)
        self.assertEqual(before.events, after.events)
        self.assertEqual(before.conflicts, after.conflicts)
        self.assertEqual(before.delays, after.delays)
        self.assertEqual(json.loads(json.dumps(before.metadata)), after.metadata)
        for planned in (False, True):
            self.assertEqual(list(before.paths.iter_motion_sequences(planned)),
                             list(after.paths.iter_motion_sequences(planned)))
            for at in (0, 1, 2, 3, 4, 5, 8, 11, before.max_time, before.max_time + 10):
                np.testing.assert_array_equal(before.paths.positions(at, planned), after.paths.positions(at, planned))

    def test_roundtrip_retains_tasks_errors_delays_and_one_step_predictions(self):
        original = self.plan()
        restored = decode_document(plan_to_document(original), self.map)
        self.assert_equivalent(original, restored)
        np.testing.assert_allclose(restored.paths.positions(2, True), [[3, 3 + 1 / 3, 11 / 3],
                                                                     [4 - 1 / 3, 4, 1]], atol=1e-6)

    def test_dump_file_is_json_and_retains_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "normalized.json"
            self.assertEqual(dump_plan(self.plan(), target), target)
            document = json.loads(target.read_text())
            self.assertEqual(document["format"], "planviz")
            self.assertEqual(document["schema_version"], 1)
            self.assert_equivalent(self.plan(), decode_document(document, self.map))

    def test_billion_tick_export_does_not_expand_or_duplicate_histories(self):
        original = self.plan()
        paths = PathStore(np.array([[0, 0, 0]]), [MotionSequence(("W",), (10**9,))])
        original = PlanData(self.map, paths, (), (), (), {}, {}, "2026 LoRR", "MAPF_T", "tick", 1, 10**9)
        document = plan_to_document(original)
        self.assertEqual(document["agents"], [{"start": [0, 0, 0], "actual": [["W", 10**9]]}])
        self.assertLess(len(json.dumps(document)), 500)
        restored = decode_document(document, self.map)
        self.assertLess(restored.paths.storage_bytes, 1000)
        np.testing.assert_array_equal(restored.paths.positions(10**9), [[0, 0, 0]])

    def test_empty_agents_and_empty_paths_roundtrip(self):
        original = self.plan()
        document = plan_to_document(original)
        document.update(agents=[], tasks=[], events=[], conflicts=[], delays={})
        restored = decode_document(document, self.map)
        self.assertEqual(restored.paths.positions(20).shape, (0, 3))
        self.assertEqual(list(restored.paths.iter_motion_sequences()), [])
        document["agents"] = [{"start": [0, 0, 0], "actual": []}]
        restored = decode_document(document, self.map)
        self.assertEqual(list(restored.paths.iter_motion_sequences()), [MotionSequence((), ())])

    def test_team_filter_retains_global_tasks_and_stable_event_ids(self):
        document = plan_to_document(self.plan())
        restored = decode_document(document, self.map, team_size=1)
        self.assertEqual(restored.team_size, 1)
        self.assertEqual([event.id for event in restored.events], ["first", "third"])
        self.assertEqual(restored.tasks[0].assignments, ((1, 0),))
        self.assertEqual(restored.tasks[0].completions, ((8, 0, 1),))
        self.assertEqual(restored.conflicts[0].agent_ids, (0,))
        self.assertEqual(restored.tasks[0].stops, self.plan().tasks[0].stops)

    def test_invalid_schema_types_models_times_and_dimensions(self):
        original = plan_to_document(self.plan())
        invalid = (("format", "unrelated"), ("schema_version", 2), ("schema_version", True),
                   ("schema_version", 1.0), ("schema_version", "1"), ("action_model", "other"),
                   ("time_unit", "second"), ("ticks_per_step", 0), ("ticks_per_step", 1.2),
                   ("max_time", -1), ("max_time", 1), ("map", {"width": 9, "height": 8}),
                   ("map", {"width": True, "height": 8}), ("metadata", {"bad": float("nan")}))
        for field, value in invalid:
            with self.subTest(field=field, value=value):
                document = copy.deepcopy(original)
                document[field] = value
                with self.assertRaises(ValueError):
                    decode_document(document, self.map)
        document = copy.deepcopy(original)
        document["time_unit"] = "timestep"
        with self.assertRaisesRegex(ValueError, "ticks_per_step = 1"):
            decode_document(document, self.map)

    def test_invalid_motions_and_coordinates_are_rejected_even_when_filtered(self):
        for duration in (0, -1, True, 1.5, "1", 2**64):
            document = plan_to_document(self.plan())
            document["agents"][1]["actual"] = [["W", duration]]
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                decode_document(document, self.map, team_size=1)
        for field, value in (("actual", [["L", 1]]), ("actual", [["W"]]),
                             ("actual", "W"), ("start", [0, float("inf"), 0]),
                             ("start", [0, 0, -1]), ("start", [True, 0, 0])):
            document = plan_to_document(self.plan())
            document["agents"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                decode_document(document, self.map)

    def test_invalid_references_are_rejected(self):
        mutations = (
            lambda doc: doc["tasks"].append(copy.deepcopy(doc["tasks"][0])),
            lambda doc: doc["tasks"][0].update(assignments=[[1, 2]]),
            lambda doc: doc["tasks"][0].update(completions=[[1, 0, 2]]),
            lambda doc: doc["events"][0].update(agent_id=5),
            lambda doc: doc["events"][0].update(task_id=-1),
            lambda doc: doc["events"][0].update(stop_index=2),
            lambda doc: doc["conflicts"][0].update(agent_ids=[0, 0]),
            lambda doc: doc.update(delays={"2": [[0, 2]]}),
            lambda doc: doc.update(delays={"00": [[0, 2]]}),
            lambda doc: doc.update(delays={"0": [[3, 2]]}),
        )
        for index, mutation in enumerate(mutations):
            document = plan_to_document(self.plan())
            mutation(document)
            with self.subTest(case=index), self.assertRaises(ValueError):
                decode_document(document, self.map)

    def test_unavailable_tasks_in_diagnostics_are_preserved(self):
        document = plan_to_document(self.plan())
        document["events"][0].update(task_id=999, stop_index=4)
        document["conflicts"][0]["task_id"] = 998
        document["metadata"]["warnings"] = ["Event references unavailable task 999."]
        restored = decode_document(document, self.map)
        self.assertEqual(restored.events[0].task_id, 999)
        self.assertEqual(restored.events[0].stop_index, 4)
        self.assertEqual(restored.conflicts[0].task_id, 998)
        self.assertEqual(restored.metadata["warnings"], document["metadata"]["warnings"])

    def test_mapf_sentinel_and_direction_convention_roundtrip(self):
        document = plan_to_document(self.plan())
        document.update(action_model="MAPF", time_unit="timestep", ticks_per_step=1,
                        agents=[{"start": [1, 1, -1], "actual": [["U", 1], ["R", 1]]}],
                        tasks=[], events=[], conflicts=[], delays={})
        restored = decode_document(document, self.map)
        np.testing.assert_array_equal(restored.paths.positions(2), [[2, 2, -1]])
        self.assertEqual(plan_to_document(restored)["agents"], document["agents"])

    def test_cancellation_and_progress(self):
        document = plan_to_document(self.plan())
        with self.assertRaises(InterruptedError):
            decode_document(document, self.map, cancelled=lambda: True)
        seen = []
        decode_document(document, self.map, progress=lambda percent, message: seen.append(percent))
        self.assertEqual(seen[-1], 100)
        self.assertEqual(seen, sorted(seen))

    def test_all_twelve_existing_lorr_fixtures_roundtrip(self):
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
                original = load_plan(map_path, plan_path)
                restored = decode_document(plan_to_document(original), original.map)
                self.assert_equivalent(original, restored)


if __name__ == "__main__":
    unittest.main()
