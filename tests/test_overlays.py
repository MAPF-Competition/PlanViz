"""Legacy overlay fixtures, coordinate conventions, and invalid-input checks."""

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from planviz_qt.domain.models import MapData
from planviz_qt.io.overlays import load_overlay


class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.map = MapData(np.ones((3, 3), dtype=np.uint8))

    def write(self, text, name="overlay.txt"):
        path = Path(self.directory.name) / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_legacy_highway_decoding_matches_from_offset(self):
        # Encoded edge = (source location + 1) * cell_count + target location.
        path = self.write("2\n10\n31\n")  # 0 -> 1, 2 -> 4 is diagonal (invalid).
        with self.assertRaisesRegex(ValueError, "adjacent"):
            load_overlay(path, "hw", self.map)
        path = self.write("2\n10\n23\n")  # 0 -> 1, 1 -> 5 is also diagonal.
        with self.assertRaisesRegex(ValueError, "adjacent"):
            load_overlay(path, "hw", self.map)
        path = self.write("2\n10\n22\n")  # 0 -> 1, 1 -> 4.
        overlay = load_overlay(path, "hw", self.map)
        self.assertEqual(overlay.kind, "highway")
        self.assertEqual(overlay.segments, ((0, 0, 0, 1), (0, 1, 1, 1)))
        self.assertIsNone(overlay.values)

    def test_highway_json_and_count_validation(self):
        path = self.write(json.dumps({"edges": [{"from": [0, 0], "to": [0, 1]}]}))
        self.assertEqual(load_overlay(path, "highway", self.map).segments, ((0, 0, 0, 1),))
        with self.assertRaisesRegex(ValueError, "declares"):
            load_overlay(self.write("2\n10\n"), "highway", self.map)
        with self.assertRaisesRegex(ValueError, "outside"):
            load_overlay(self.write("1\n0\n"), "highway", self.map)

    def test_heuristic_agent_selection_and_unreachable_sentinels(self):
        rows = ["0," + ",".join(["1"] * 9),
                "104,0,1,2,2147483647,4,5,1.79769e308,7,8"]
        overlay = load_overlay(self.write("\n".join(rows)), "heu", self.map)
        self.assertTrue(np.isnan(overlay.values[1, 0]))
        self.assertTrue(np.isnan(overlay.values[2, 0]))
        self.assertEqual(overlay.values[2, 2], 8)
        self.assertEqual(overlay.colormap, "Greys")
        self.assertFalse(overlay.values.flags.writeable)
        other = load_overlay(self.write("\n".join(rows)), "heu", self.map, agent_id=0)
        self.assertTrue(np.all(other.values == 1))
        with self.assertRaisesRegex(ValueError, "agent 8"):
            load_overlay(self.write("\n".join(rows)), "heu", self.map, agent_id=8)

    def test_search_csv_accumulates_repeated_expansions(self):
        overlay = load_overlay(self.write("loc,g,h\n0,0,3\n4,1,2\n4,2,1\n"), "searchTree", self.map)
        self.assertEqual(overlay.values[0, 0], 1)
        self.assertEqual(overlay.values[1, 1], 2)
        self.assertEqual(overlay.values.sum(), 3)
        with self.assertRaisesRegex(ValueError, "loc"):
            load_overlay(self.write("loc\n-1\n"), "search_tree", self.map)
        with self.assertRaisesRegex(ValueError, "loc column"):
            load_overlay(self.write("bad\n0\n"), "search_tree", self.map)

    def test_heatmap_trims_waits_and_excludes_terminal_state(self):
        data = {"actionModel": "MAPF_T", "start": [[1, 1, "E"]],
                "actualPaths": ["F,C,F,W,W"]}
        overlay = load_overlay(self.write(json.dumps(data)), "hm", self.map)
        self.assertEqual(overlay.values.sum(), 3)
        self.assertEqual(overlay.values[1, 1], 1)
        self.assertEqual(overlay.values[1, 2], 2)
        self.assertEqual(overlay.values[0, 2], 0)
        data["actualPaths"] = ["W,W"]
        overlay = load_overlay(self.write(json.dumps(data)), "heatmap", self.map)
        self.assertEqual(overlay.values.sum(), 0)

    def test_heatmap_mapf_uses_existing_u_down_convention(self):
        data = {"actionModel": "MAPF", "start": [[0, 0, "N/A"]],
                "actualPaths": ["U,R"]}
        overlay = load_overlay(self.write(json.dumps(data)), "heatmap", self.map)
        self.assertEqual(overlay.values[0, 0], 1)
        self.assertEqual(overlay.values[1, 0], 1)
        self.assertEqual(overlay.values.sum(), 2)

    def test_service_actions_are_not_trimmed_as_trailing_waits(self):
        data = {"actionModel": "MAPF_T", "start": [[1, 0, "E"]],
                "actualPaths": ["F,T,W,W"]}
        overlay = load_overlay(self.write(json.dumps(data)), "heatmap", self.map)
        self.assertEqual(overlay.values.sum(), 2)
        self.assertEqual(overlay.values[1, 0], 1)
        self.assertEqual(overlay.values[1, 1], 1)
        data.update(version="2026 LoRR", agentMaxCounter=10,
                    actualPaths=["[(0,0,1,0,0):(F 10,T 10,W 20)]"])
        overlay = load_overlay(self.write(json.dumps(data)), "heatmap", self.map)
        self.assertEqual(overlay.values.sum(), 20)
        self.assertEqual(overlay.values[1, 1], 15)

    def test_tick_rle_heatmap_samples_every_tick_without_trailing_waits(self):
        data = {"version": "2026 LoRR", "agentMaxCounter": 10,
                "actionModel": "MAPF_T", "start": [[1, 0, "E"]],
                "actualPaths": ["[(0,0,1,0,0):(F 10,W 20)]"]}
        overlay = load_overlay(self.write(json.dumps(data)), "heatmap", self.map)
        self.assertEqual(overlay.values.sum(), 10)
        self.assertEqual(overlay.values[1, 0], 5)
        self.assertEqual(overlay.values[1, 1], 5)

    def test_transfer_paths_and_matrix_shape_validation(self):
        path = self.write("Agent 0: (0,0)->(0,1)->(1,1)->(1,1)->\n")
        overlay = load_overlay(path, "heatmap", self.map)
        self.assertEqual(overlay.values.sum(), 2)
        self.assertEqual(overlay.values[0, 1], 1)
        path = self.write(json.dumps({"values": list(range(9))}))
        self.assertEqual(load_overlay(path, "heatmap", self.map).values[2, 2], 8)
        with self.assertRaisesRegex(ValueError, "shape"):
            load_overlay(self.write("1,2\n3,4\n"), "heuristic", self.map)
        with self.assertRaisesRegex(ValueError, "leaves the map"):
            load_overlay(self.write("Agent 0: (-1,0)->(0,0)->\n"), "heatmap", self.map)

    def test_cancellation_interrupts_heatmap_chunks(self):
        data = {"version": "2026 LoRR", "actionModel": "MAPF_T",
                "start": [[1, 1, "E"]], "agentMaxCounter": 10,
                "actualPaths": ["[(0,1,1,0,0):(T 200000,W 10)]"]}
        path = self.write(json.dumps(data))
        calls = 0

        def cancel_during_sampling():
            nonlocal calls
            calls += 1
            return calls >= 8

        with self.assertRaises(InterruptedError):
            load_overlay(path, "heatmap", self.map, cancelled=cancel_during_sampling)
        self.assertEqual(calls, 8)
        with self.assertRaises(InterruptedError):
            load_overlay(path, "heatmap", self.map, cancelled=lambda: True)


if __name__ == "__main__":
    unittest.main()
