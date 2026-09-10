"""Converter dispatch and all LoRR version / movement-model combinations."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from planviz_qt.io.loader import PlanLoadError, load_plan
from planviz_qt.converters.lorr import LoRR2024Converter
from planviz_qt.converters.registry import ConverterRegistry, default_registry


class InputFormatTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.map = self.folder / "test.map"
        self.map.write_text("type octile\nheight 6\nwidth 6\nmap\n" + "......\n" * 6)
        self.source = self.folder / "input.json"

    def load(self, data, **options):
        self.source.write_text(json.dumps(data))
        return load_plan(self.map, self.source, **options)

    def data(self, year, model):
        ticks = 3 if year == 2026 else 1
        actions = "URDLW" if model == "MAPF" else "FRFCF"
        motion = ("[(0,2,2,0,0):(" + ",".join(f"{action} {ticks}" for action in actions) + ")]"
                  if year == 2026 else ",".join(actions))
        data = {"version": f"{year} LoRR", "actionModel": model, "teamSize": 1,
                "start": [[2, 2, "N/A" if model == "MAPF" else "E"]],
                "actualPaths": [motion], "makespan": 5}
        goal = [2, 2] if model == "MAPF" else [3, 4]
        if year == 2023:
            data.update(tasks=[[7, *goal]], events=[[[7, 0, "assigned"], [7, 5, "finished"]]])
        else:
            data.update(tasks=[[7, 0, goal]], actualSchedule=["0:7"], events=[[5*ticks, 0, 7, 1]])
        if year == 2026:
            data.update(agentMaxCounter=3, makespanTicks=15)
        return data

    def test_three_versions_times_both_movement_models(self):
        for year in (2023, 2024, 2026):
            for model in ("MAPF", "MAPF_T"):
                with self.subTest(year=year, model=model):
                    data = self.data(year, model)
                    auto = self.load(data)
                    explicit = self.load(data, input_format=f"lorr-{year}")
                    tick = 3 if year == 2026 else 1
                    expected = ([[2, 2, -1], [3, 2, -1], [3, 3, -1], [2, 3, -1], [2, 2, -1], [2, 2, -1]]
                                if model == "MAPF" else
                                [[2, 2, 0], [2, 3, 0], [2, 3, 3], [3, 3, 3], [3, 3, 0], [3, 4, 0]])
                    for step, state in enumerate(expected):
                        np.testing.assert_allclose(auto.paths.positions(step*tick), [state])
                        np.testing.assert_array_equal(auto.paths.positions(step*tick),
                                                      explicit.paths.positions(step*tick))
                    self.assertEqual(auto.tasks[0].state(5*tick-1), "assigned")
                    self.assertEqual(auto.tasks[0].state(5*tick), "finished")
                    self.assertEqual(auto.time_unit, "tick" if year == 2026 else "timestep")
                    self.assertEqual(auto.max_time, 5*tick)

    def test_versionless_empty_tick_paths_detect_from_tick_metadata(self):
        data = self.data(2026, "MAPF_T")
        del data["version"]
        data["actualPaths"] = [""]
        plan = self.load(data)
        self.assertEqual(plan.version, "2026 LoRR")
        np.testing.assert_array_equal(plan.paths.positions(15), [[2, 2, 0]])

    def test_versionless_sequential_tasks_without_schedule(self):
        data = self.data(2024, "MAPF")
        del data["version"], data["actualSchedule"]
        self.assertEqual(self.load(data).version, "2024 LoRR")

    def test_minimal_legacy_start_only_result_stays_stationary(self):
        plan = self.load({"actionModel": "MAPF", "AllValid": "Yes", "teamSize": 1,
                          "start": [[2, 2, "N/A"]]})
        self.assertEqual(plan.max_time, 0)
        np.testing.assert_array_equal(plan.paths.positions(0), [[2, 2, -1]])
        self.assertEqual(plan.events, ())

    def test_legacy_rle_override_cannot_silently_change_time_scale(self):
        data = self.data(2026, "MAPF")
        with self.assertRaisesRegex(PlanLoadError, "RLE.*2026"):
            self.load(data, input_format="lorr-2023")

    def test_conflicting_format_version_and_unknown_input_fail_helpfully(self):
        with self.assertRaisesRegex(PlanLoadError, "different converters"):
            self.load(self.data(2024, "MAPF"), input_format="lorr-2024", version="2026 LoRR")
        with self.assertRaisesRegex(PlanLoadError, "Unrecognized input"):
            self.load({"unrelated": [1, 2]})
        with self.assertRaisesRegex(PlanLoadError, "Unknown input format"):
            self.load(self.data(2024, "MAPF"), input_format="missing")

    def test_custom_converter_routes_without_changing_loader_or_domain(self):
        class WrappedConverter:
            id, label = "wrapped", "Wrapped test input"

            def can_read(self, data):
                return data.get("format") == self.id

            def convert(self, data, context):
                return LoRR2024Converter().convert(data["payload"], context)

        registry = default_registry()
        registry.register(WrappedConverter())
        plan = self.load({"format": "wrapped", "payload": self.data(2024, "MAPF")}, registry=registry)
        np.testing.assert_array_equal(plan.paths.positions(1), [[3, 2, -1]])
        with self.assertRaisesRegex(ValueError, "already registered"):
            registry.register(WrappedConverter())

    def test_ambiguous_detection_requires_explicit_choice(self):
        class AlsoLegacy(LoRR2024Converter):
            id = "another-lorr-2024"
        registry = ConverterRegistry((LoRR2024Converter(), AlsoLegacy()))
        with self.assertRaisesRegex(PlanLoadError, "Ambiguous"):
            self.load(self.data(2024, "MAPF"), registry=registry)
        self.assertEqual(self.load(self.data(2024, "MAPF"), registry=registry,
                                   input_format="lorr-2024").version, "2024 LoRR")


if __name__ == "__main__":
    unittest.main()
