"""Color configuration validation without a QApplication or Qt imports."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from importlib import resources
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from planviz_qt.palette import Palette, PaletteError, load_palette, save_palette


class PaletteTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.folder = Path(self.directory.name)

    def load(self, text):
        source = self.folder / "custom.yaml"
        source.write_text(text, encoding="utf-8")
        return load_palette(source)

    def test_bundled_resource_and_all_semantic_defaults(self):
        palette = load_palette()
        self.assertIsNone(palette.source)
        self.assertTrue(resources.files("planviz_qt.palettes").joinpath("Color_palette.yaml").is_file())
        expected = {
            "version": 1,
            "agent": {"idle": "#00bfff", "newly_assigned": "#9acd32", "delayed": "#ffff00",
                      "errand_completed": "#32cd32", "collision": "#ff0000", "heading": "#000080",
                      "index": "#101827", "selected_outline": "#ef4444", "collision_outline": "#dc2626",
                      "start_fill": "#919baa", "start_outline": "#7b8491"},
            "task": {"unassigned": "#eeeaa2", "newly_assigned": "#9acd32", "assigned": "#ffa500",
                     "completed": "#c0c0c0", "index": "#343b46"},
            "errand": {"unassigned": "#ddd6fe", "newly_assigned": "#9acd32", "assigned": "#a78bfa",
                       "completed": "#c0c0c0", "index": "#343b46"},
            "path": {"executed": "#803bba", "remaining_errands": "#4eb1a6"},
        }
        self.assertEqual(palette.as_dict(), expected)

    def test_partial_case_insensitive_override_preserves_other_defaults(self):
        palette = self.load('Version: 1\nAgent:\n  Idle: "#342353"\n  COLLISION: "#ABCDEF"\n')
        self.assertEqual(palette.source, (self.folder / "custom.yaml").resolve())
        self.assertEqual(palette.color("AGENT", "Idle"), "#342353")
        self.assertEqual(palette.color("agent", "collision"), "#abcdef")
        self.assertEqual(palette.color("errand", "assigned"), "#a78bfa")
        self.assertEqual(load_palette().color("agent", "idle"), "#00bfff")

    def test_version_omission_and_empty_mapping_use_defaults(self):
        self.assertEqual(self.load('{}\n').as_dict(), load_palette().as_dict())
        self.assertEqual(self.load('agent:\n  idle: \'#342353\'\n').color("agent", "idle"), "#342353")

    def test_palette_and_nested_mappings_are_immutable(self):
        palette = load_palette()
        with self.assertRaises(FrozenInstanceError):
            palette.source = self.folder / "changed.yaml"
        with self.assertRaises(TypeError):
            palette._sections["agent"]["idle"] = "#342353"
        copied = palette.as_dict()
        copied["agent"]["idle"] = "#342353"
        copied["version"] = 2
        self.assertEqual(palette.color("agent", "idle"), "#00bfff")
        self.assertEqual(palette.as_dict()["version"], 1)

    def test_save_copy_is_full_schema_reopens_and_does_not_change_source(self):
        palette = self.load('agent:\n  idle: "#342353"\n')
        original_source = palette.source
        destination = self.folder / "saved.yaml"
        self.assertIsNone(save_palette(palette, destination))
        restored = load_palette(destination)
        self.assertEqual(restored.as_dict(), palette.as_dict())
        self.assertEqual(restored.source, destination.resolve())
        self.assertEqual(palette.source, original_source)
        self.assertIn("'#342353'", destination.read_text())
        self.assertEqual(set(restored.as_dict()), {"version", "agent", "task", "errand", "path"})

    def test_unknown_sections_and_color_keys_rejected(self):
        for text in ('agents: {}', 'agent:\n  idel: "#342353"', 'task:\n  heading: "#342353"'):
            with self.subTest(text=text), self.assertRaisesRegex(PaletteError, "Unknown"):
                self.load(text)
        for section, key in (("other", "idle"), ("agent", "other"), (1, "idle")):
            with self.subTest(section=section, key=key), self.assertRaises(PaletteError):
                load_palette().color(section, key)

    def test_duplicate_normalized_keys_rejected(self):
        for text in ('version: 1\nVersion: 1',
                     'agent: {}\nAgent: {}',
                     'agent:\n  idle: "#342353"\n  Idle: "#ffffff"',
                     'task:\n  assigned: "#342353"\n  assigned: "#ffffff"'):
            with self.subTest(text=text), self.assertRaisesRegex(PaletteError, "duplicate"):
                self.load(text)

    def test_invalid_or_unquoted_colors_rejected(self):
        values = ('#342353', '"#123"', '"#12345678"', '"#zzzzzz"',
                  '"red"', '"342353"', '" #342353"', '"#342353 "',
                  '123456', 'true', 'null', '["#342353"]', '{}',
                  '|\n    #342353', '!!binary "#342353"')
        for value in values:
            with self.subTest(value=value), self.assertRaisesRegex(PaletteError, "quoted hexadecimal"):
                self.load(f"agent:\n  idle: {value}\n")

    def test_invalid_versions_rejected(self):
        for version in ('0', '2', '-1', '1.0', 'true', '"1"', 'null', '[]', '{}', '0x1', '01'):
            with self.subTest(version=version), self.assertRaisesRegex(PaletteError, "version"):
                self.load(f"version: {version}\n")

    def test_custom_and_unsafe_tags_merge_keys_and_recursive_aliases_rejected(self):
        invalid = (
            '!!python/object/apply:os.system ["echo unsafe"]',
            '!Custom {agent: {idle: "#342353"}}',
            'agent: !Custom {idle: "#342353"}',
            'agent:\n  idle: !Custom "#342353"',
            'agent:\n  !Custom idle: "#342353"',
            'agent:\n  <<: {idle: "#342353"}',
            'agent: &agent\n  idle: *agent',
        )
        for text in invalid:
            with self.subTest(text=text), self.assertRaises(PaletteError):
                self.load(text)

    def test_invalid_documents_have_contextual_errors(self):
        for text in ('', '# only a comment', '[1, 2]', 'agent: [',
                     '---\n{}\n---\n{}', 'agent: null', '1: {}'):
            with self.subTest(text=text), self.assertRaisesRegex(PaletteError, "custom.yaml"):
                self.load(text)
        with self.assertRaisesRegex(PaletteError, "missing.yaml"):
            load_palette(self.folder / "missing.yaml")
        source = self.folder / "binary.yaml"
        source.write_bytes(b"\xff\xff")
        with self.assertRaisesRegex(PaletteError, "binary.yaml"):
            load_palette(source)
        with self.assertRaisesRegex(PaletteError, "Cannot save palette"):
            save_palette(load_palette(), self.folder / "missing" / "output.yaml")

    def test_reload_reads_changed_file_and_invalid_file_does_not_change_existing_palette(self):
        source = self.folder / "custom.yaml"
        palette = self.load('agent:\n  idle: "#342353"\n')
        source.write_text('agent:\n  idle: "#abcdef"\n')
        self.assertEqual(load_palette(palette.source).color("agent", "idle"), "#abcdef")
        source.write_text('agent:\n  idle: "invalid"\n')
        with self.assertRaises(PaletteError):
            load_palette(palette.source)
        self.assertEqual(palette.color("agent", "idle"), "#342353")

    def test_edited_bundled_palette_rejects_missing_and_unknown_colors_before_rendering(self):
        default = load_palette().as_dict()
        for mutation in (lambda value: value["agent"].pop("idle"),
                         lambda value: value["agent"].update(idel="#342353"),
                         lambda value: value.pop("path")):
            value = {key: dict(item) if isinstance(item, dict) else item for key, item in default.items()}
            mutation(value)
            with self.subTest(value=value), patch("planviz_qt.palette.resources.files") as resource:
                resource.return_value.joinpath.return_value.read_text.return_value = yaml.safe_dump(value)
                with self.assertRaisesRegex(PaletteError, "Cannot load bundled"):
                    load_palette()

    def test_invalid_directly_constructed_palette_does_not_overwrite_existing_file(self):
        destination = self.folder / "valid.yaml"
        save_palette(load_palette(), destination)
        before = destination.read_bytes()
        invalid = Palette({"agent": {"idle": "#342353"}})
        with self.assertRaisesRegex(PaletteError, "Cannot save palette"):
            save_palette(invalid, destination)
        self.assertEqual(destination.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
