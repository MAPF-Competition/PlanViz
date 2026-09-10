"""Malformed structure fails; inconsistent replay records remain inspectable."""
from pathlib import Path
import json
import tempfile
import unittest

from planviz_qt.io.loader import load_map, load_plan, PlanLoadError


class ValidationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.map = Path(directory.name) / 'input.map'
        self.source = Path(directory.name) / 'plan.json'
        self.map.write_text('type octile\nheight 2\nwidth 3\nmap\n...\n...\n')
        self.data = {'version': '2026 LoRR', 'actionModel': 'MAPF_T', 'teamSize': 1,
                     'start': [[0, 0, 'E']], 'actualPaths': ['[(0,0,0,0,0):(F 2)]'], 'agentMaxCounter': 1,
                     'makespan': 2, 'tasks': [[7, 0, [0, 1]]],
                     'actualSchedule': ['0:7'], 'events': [[1, 0, 7, 1]]}

    def load(self, **kwargs):
        self.source.write_text(json.dumps(self.data))
        return load_plan(self.map, self.source, **kwargs)

    def test_map_headers_dimensions_and_terrain_are_validated(self):
        original = self.map.read_text()
        for replacement in (original.replace('height 2', 'height 999'),
                            original.replace('height 2', 'height 0'),
                            original.replace('width 3', 'width -1'),
                            original.replace('height 2', 'length 2'),
                            original.replace('type octile', 'type unsupported'),
                            original.replace('...\n...\n', '..\n...\n'),
                            original.replace('...\n...\n', '.X.\n...\n')):
            with self.subTest(header=replacement[:40]):
                self.map.write_text(replacement)
                with self.assertRaises(PlanLoadError):
                    load_map(self.map)
        self.map.write_text(original)
        self.assertEqual(load_map(self.map).height, 2)

    def test_lorr_integer_fields_never_truncate_or_accept_booleans(self):
        for key in ('agentMaxCounter', 'teamSize', 'makespan'):
            original = self.data[key]
            for value in (True, 1.5, '2', -1):
                with self.subTest(field=key, value=value):
                    self.data[key] = value
                    with self.assertRaisesRegex(PlanLoadError, key):
                        self.load()
            self.data[key] = original

    def test_timing_warnings_preserve_original_records_and_monotonic_progress(self):
        self.data['actualSchedule'] = ['1000:7']
        progress = []
        plan = self.load(progress=lambda percent, message: progress.append(percent))
        self.assertEqual(plan.tasks[0].assignments, ((1000, 0),))
        self.assertEqual(plan.tasks[0].completions, ((1, 0, 0),))
        warnings = plan.metadata['warnings']
        self.assertTrue(any('Assignments beyond' in note for note in warnings))
        self.assertTrue(any('without a matching assignment' in note for note in warnings))
        self.assertEqual(progress, sorted(progress))
        self.assertEqual(progress[0], 0)
        self.assertEqual(progress[-1], 100)
        self.assertEqual(plan.max_time, 2)
        self.assertEqual(len(plan.events), 2)

    def test_consistent_records_do_not_produce_warnings(self):
        self.assertFalse(self.load().metadata.get('warnings'))
