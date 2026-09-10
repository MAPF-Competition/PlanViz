"""Legend controls reflect the live palette without taking ownership of file I/O."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import unittest

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from planviz_qt.palette import Palette, load_palette
from planviz_qt.ui.legend_dialog import LegendDialog


class LegendDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.palette = load_palette()
        self.dialog = LegendDialog(self.palette)
        self.dialog.show()
        self.app.processEvents()

    def tearDown(self):
        self.dialog.close()
        self.dialog.deleteLater()
        self.app.processEvents()

    def test_modeless_window_emits_requests_without_changing_the_palette(self):
        dialog = self.dialog
        self.assertEqual(dialog.windowModality(), Qt.WindowModality.NonModal)
        self.assertEqual(dialog.windowType(), Qt.WindowType.Dialog)
        self.assertLessEqual(dialog.height(), 600)
        self.assertEqual(dialog.tabs.count(), 3)
        self.assertEqual(dialog.source_field.text(), "Built-in defaults")
        self.assertTrue(dialog.reload_button.isEnabled())
        sections = self.palette.as_dict()
        sections.pop("version")
        custom = Palette(sections, Path("/palette-source-not-opened-by-dialog.yaml"))
        dialog.set_palette(custom)
        for button, signal in ((dialog.load_button, dialog.loadRequested),
                               (dialog.reload_button, dialog.reloadRequested),
                               (dialog.save_button, dialog.saveRequested),
                               (dialog.defaults_button, dialog.defaultsRequested)):
            spy = QSignalSpy(signal)
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
            self.assertEqual(spy.count(), 1)
            self.assertIs(dialog._legend_palette, custom)
        spy = QSignalSpy(dialog.loadRequested)
        dialog.load_button.setFocus()
        QTest.keyClick(dialog.load_button, Qt.Key.Key_Space)
        self.assertEqual(spy.count(), 1)
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        self.assertFalse(dialog.isVisible())
        dialog.show()
        self.assertEqual(dialog.source_field.text(), str(custom.source))

    def test_palette_changes_refresh_all_values_and_samples_including_hidden_tabs(self):
        dialog = self.dialog
        sections = self.palette.as_dict()
        sections.pop("version")
        expected = {(section, key) for section, values in sections.items() for key in values}
        self.assertEqual(set(dialog._hex_labels), expected)
        self.assertEqual(set(dialog._swatches), expected)
        for index, (section, key) in enumerate(sorted(expected), 1):
            sections[section][key] = f"#{(0x203040 + index * 100003) % 0xffffff:06x}"
        custom = Palette(sections, Path("/custom-colors.yaml"))
        dialog.tabs.setCurrentIndex(2)
        dialog.set_palette(custom)
        self.assertEqual(dialog.tabs.currentIndex(), 2)
        for identity in expected:
            with self.subTest(color=identity):
                self.assertTrue(dialog._hex_labels[identity].text().startswith(custom.color(*identity)))
                self.assertEqual(dialog._swatches[identity].color().name(), custom.color(*identity))
        self.assertIn("70/255", dialog._hex_labels["agent", "start_fill"].text())
        self.assertIn("170/255", dialog._hex_labels["path", "executed"].text())
        dialog.set_palette(self.palette)
        self.assertTrue(dialog.reload_button.isEnabled())
        self.assertEqual(dialog.source_field.text(), "Built-in defaults")
        for identity in expected:
            self.assertEqual(dialog._swatches[identity].color().name(), self.palette.color(*identity))

    def test_task_and_errand_samples_have_distinct_fixed_shapes(self):
        def render(swatch):
            image = QImage(swatch.size(), QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            swatch.render(image)
            return image

        task = render(self.dialog._swatches["task", "assigned"])
        errand = render(self.dialog._swatches["errand", "assigned"])
        self.assertEqual(task.pixelColor(24, 15), QColor(self.palette.color("task", "assigned")))
        self.assertEqual(errand.pixelColor(24, 15), QColor(self.palette.color("errand", "assigned")))
        # The square reaches its diagonal corner; the diamond leaves it clear.
        self.assertEqual(task.pixelColor(31, 22), QColor(self.palette.color("task", "assigned")))
        self.assertNotEqual(errand.pixelColor(31, 22), QColor(self.palette.color("errand", "assigned")))


if __name__ == "__main__":
    unittest.main()
