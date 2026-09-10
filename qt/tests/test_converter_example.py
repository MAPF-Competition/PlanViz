"""The documented example is executable without registering a production format."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from planviz_qt.converters import ConversionContext, available_formats, default_registry
from planviz_qt.converters.example import ExampleConverter
from planviz_qt.domain.models import MapData
from planviz_qt.io.loader import load_plan


class ExampleConverterTests(unittest.TestCase):
    def setUp(self):
        self.map = MapData(np.ones((6, 6), dtype=np.uint8))
        self.context = ConversionContext(self.map, Path("example.json"))
        self.converter = ExampleConverter()

    def document(self, model="MAPF_T"):
        return {"format": "example-actions", "action_model": model,
                "starts": [[2, 2, -1 if model == "MAPF" else 0]],
                "actions": ["U,R,D,L,W" if model == "MAPF" else "F,R,F,C,W"],
                "metadata": {"solver": "test"}}

    def test_example_is_opt_in_and_private_registry_loads_actual_json(self):
        self.assertNotIn("example-actions", dict(available_formats()))
        registry = default_registry()
        registry.register(self.converter)
        with tempfile.TemporaryDirectory() as directory:
            map_path, plan_path = Path(directory) / "test.map", Path(directory) / "test.json"
            map_path.write_text("type octile\nheight 6\nwidth 6\nmap\n" + "......\n" * 6)
            plan_path.write_text(json.dumps(self.document()))
            for selection in ("auto", "example-actions"):
                with self.subTest(selection=selection):
                    plan = load_plan(map_path, plan_path, input_format=selection, registry=registry)
                    np.testing.assert_array_equal(plan.paths.positions(3), [[3, 3, 3]])
                    self.assertEqual(plan.metadata["source"], str(plan_path))

    def test_both_models_have_correct_axes_and_no_invented_tasks(self):
        for model, expected in (("MAPF", [[3, 2, -1], [3, 3, -1], [2, 3, -1], [2, 2, -1]]),
                                ("MAPF_T", [[2, 3, 0], [2, 3, 3], [3, 3, 3], [3, 3, 0]])):
            with self.subTest(model=model):
                source = self.document(model)
                before = copy.deepcopy(source)
                plan = self.converter.convert(source, self.context)
                self.assertEqual(source, before)
                self.assertEqual((plan.time_unit, plan.ticks_per_step, plan.max_time), ("timestep", 1, 5))
                self.assertEqual((plan.tasks, plan.events, plan.conflicts), ((), (), ()))
                self.assertEqual(plan.metadata["solver"], "test")
                for at, state in enumerate(expected, 1):
                    np.testing.assert_array_equal(plan.paths.positions(at), [state])

    def test_filtering_preserves_timeline_and_checks_excluded_agents(self):
        source = self.document()
        source["starts"].append([2, 2, 0])
        source["actions"].append("W," * 20)
        context = ConversionContext(self.map, Path("example.json"), team_size=1)
        plan = self.converter.convert(source, context)
        self.assertEqual((plan.team_size, plan.max_time), (1, 20))
        source["starts"][1] = [2, 2, float("nan")]
        with self.assertRaisesRegex(ValueError, "finite"):
            self.converter.convert(source, context)

    def test_empty_agents_and_stationary_agents_are_valid(self):
        source = self.document()
        source.update(starts=[], actions=[])
        plan = self.converter.convert(source, self.context)
        self.assertEqual((plan.team_size, plan.max_time), (0, 0))
        source.update(starts=[[2, 2, 0]], actions=[""])
        plan = self.converter.convert(source, self.context)
        np.testing.assert_array_equal(plan.paths.positions(0), [[2, 2, 0]])

    def test_invalid_sources_cannot_silently_lose_semantics(self):
        cases = (
            ("format", "other"), ("action_model", "other"), ("metadata", []),
            ("actions", []), ("starts", "2,2,0"), ("actions", ["U"]),
            ("actions", ["[(0,2,2,0,0):(F 10)]"]),
            ("starts", [[2, 2, "E"]]), ("starts", [[2, 2, -1]]),
            ("time_unit", "tick"), ("plannerPaths", ["F"]), ("goals", [[2, 3]]),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                source = self.document()
                source[field] = value
                with self.assertRaises(ValueError):
                    self.converter.convert(source, self.context)

    def test_progress_is_monotonic_and_cancellation_works(self):
        progress = []
        context = ConversionContext(self.map, Path("example.json"),
                                    progress=lambda value, text: progress.append(value))
        self.converter.convert(self.document(), context)
        self.assertEqual(progress, sorted(progress))
        self.assertEqual(progress[-1], 100)
        cancelled = ConversionContext(self.map, Path("example.json"), cancelled=lambda: True)
        with self.assertRaises(InterruptedError):
            self.converter.convert(self.document(), cancelled)


if __name__ == "__main__":
    unittest.main()
