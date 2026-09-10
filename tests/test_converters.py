from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from planviz_qt.converters import ConversionError, convert_paths, convert_tracker, main
from planviz_qt.io.loader import load_plan


class ConverterTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.map = self.folder / "small.map"
        self.map.write_text("type octile\nheight 3\nwidth 3\nmap\n...\n...\n...\n")
        self.scenario = self.folder / "small-random-1.scen"
        self.scenario.write_text("version 1\n0 small.map 3 3 0 0 1 1 2\n0 small.map 3 3 2 2 2 2 0\n")

    def write_csv(self, rows):
        source = self.folder / "tracker.csv"
        with source.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        return source

    def test_coordinate_paths_round_trip_down_and_up(self):
        source = self.folder / "paths.txt"
        source.write_text("Agent 0: (0,0)->(1,0)->(1,1)->\nAgent1: (2,2)->(1,2)->\n")
        output = self.folder / "converted.json"
        result = convert_paths(source, output)
        self.assertEqual(result["actualPaths"], ["U,R", "D,W"])
        plan = load_plan(self.map, output)
        np.testing.assert_allclose(plan.paths.positions(2)[:, :2], [[1, 1], [1, 2]])
        self.assertEqual(result["events"][1][-1], [1, 1, "finished"])

    def test_paths_reject_teleport_and_missing_agent(self):
        source = self.folder / "paths.txt"
        source.write_text("Agent0: (0,0)->(2,0)\n")
        with self.assertRaisesRegex(ConversionError, "noncardinal"):
            convert_paths(source)
        source.write_text("Agent1: (0,0)\n")
        with self.assertRaisesRegex(ConversionError, "expected agent 0"):
            convert_paths(source)

    def test_conflict_conversion_and_stationary_path(self):
        source = self.folder / "paths.txt"
        source.write_text("Agent0: (0,0)\nAgent1: (0,1)\n")
        conflicts = self.folder / "conflicts.csv"
        conflicts.write_text("agent1,agent2,time,type\n0,1,0,V\n")
        result = convert_paths(source, conflict_file=conflicts)
        self.assertEqual(result["makespan"], 0)
        self.assertEqual(result["actualPaths"], ["", ""])
        self.assertEqual(result["errors"], [[0, 1, 0, "vertex conflict"]])
        self.assertEqual(result["AllValid"], "No")

    def test_tracker_roundtrip_and_stationary_last_agent(self):
        source = self.write_csv([{"agents": 2, "solution_cost": 2, "path": "dr\n"}])
        output = self.folder / "single.json"
        result = convert_tracker(source, self.scenario, output)[0]
        self.assertEqual(result["actualPaths"], ["U,R", "W,W"])
        self.assertEqual(len(result["start"]), 2)
        plan = load_plan(self.map, output)
        np.testing.assert_allclose(plan.paths.positions(2)[:, :2], [[1, 1], [2, 2]])

    def test_tracker_rejects_agent_count_mismatch(self):
        source = self.write_csv([{"agents": 2, "path": "dr"}])
        with self.assertRaisesRegex(ConversionError, "2 agents but 1 paths"):
            convert_tracker(source, self.scenario)
        source = self.write_csv([{"agents": 3, "path": "dr\nw\nw"}])
        with self.assertRaisesRegex(ConversionError, "requires 3"):
            convert_tracker(source, self.scenario)

    def test_bulk_numeric_suffixes_and_no_partial_invalid_output(self):
        rows = [{"agents": 1, "solution_plan": "dr", "map_name": "small", "scen_type": "random", "type_id": 1}]
        source = self.write_csv(rows * 2)
        output = self.folder / "bulk.json"
        convert_tracker(source, self.folder, output, multi=True)
        self.assertTrue((self.folder / "bulk_0.json").exists())
        self.assertTrue((self.folder / "bulk_1.json").exists())
        rows.append(dict(rows[0], map_name="../escape"))
        source = self.write_csv(rows)
        with self.assertRaisesRegex(ConversionError, "unsafe"):
            convert_tracker(source, self.folder, self.folder / "invalid.json", multi=True)
        self.assertFalse((self.folder / "invalid_0.json").exists())

    def test_scenario_coordinate_validation(self):
        self.scenario.write_text("version 1\n0 small.map 3 3 9 0 1 1 2\n")
        source = self.write_csv([{"agents": 1, "path": "dr"}])
        with self.assertRaisesRegex(ConversionError, "outside"):
            convert_tracker(source, self.scenario)

    def test_cli_paths(self):
        source = self.folder / "paths.txt"
        source.write_text("Agent0: (0,0)->(0,1)\n")
        target = self.folder / "cli.json"
        self.assertEqual(main(["paths", "--path", str(source), "--output", str(target)]), 0)
        self.assertEqual(json.loads(target.read_text())["version"], "2023 LoRR")


if __name__ == "__main__":
    unittest.main()
