"""Interaction tests for the offline demo, optional in bootstrap-only setups."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from nexus_ui.app import NexusWindow, make_application, ASSETS, icon
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
except ModuleNotFoundError as exc:
    if exc.name != "PySide6":
        raise
    NexusWindow = None


@unittest.skipIf(NexusWindow is None, "Install requirements-ui.txt for Qt tests")
class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app, cls.font_loaded = make_application()

    def setUp(self):
        self.window = NexusWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def ready(self, dual=False):
        self.window.check_device()
        self.window.prepare_model()
        self.window.prompt.setPlainText("Eine Testnachricht")
        if dual:
            self.window.mode.setCurrentIndex(1)
            self.window.pair_peer()

    def test_navigation_by_keyboard(self):
        for i, nav in enumerate(self.window.nav):
            nav.setFocus()
            QTest.keyClick(nav, Qt.Key.Key_Space)
            self.assertEqual(self.window.stack.currentIndex(), i)

    def test_start_requires_setup_prompt_and_peer_in_dual_mode(self):
        self.assertFalse(self.window.start.isEnabled())
        self.ready()
        self.assertTrue(self.window.start.isEnabled())
        self.window.mode.setCurrentIndex(1)
        self.assertFalse(self.window.start.isEnabled())
        self.window.pair_peer()
        self.assertTrue(self.window.start.isEnabled())
        self.window.prompt.setPlainText("  ")
        self.window.start_session()
        self.assertFalse(self.window.running)

    def test_stop_retains_prompt_and_no_further_output(self):
        self.ready()
        self.window.start.click()
        self.assertTrue(self.window.running)
        self.assertFalse(self.window.mode.isEnabled())
        self.window.stop.click()
        self.assertFalse(self.window.timer.isActive())
        text = self.window.output.toPlainText()
        QTest.qWait(600)
        self.assertEqual(text, self.window.output.toPlainText())
        self.assertEqual(self.window.prompt.toPlainText(), "Eine Testnachricht")

    def test_peer_disconnect_stops_dual_run_and_requires_manual_restart(self):
        self.ready(dual=True)
        self.window.start_session()
        self.window.disconnect_peer()
        self.assertFalse(self.window.running)
        self.assertIn("getrennt", self.window.output.toPlainText())
        self.assertFalse(self.window.start.isEnabled())
        self.window.pair_peer()
        self.assertFalse(self.window.running)
        self.assertTrue(self.window.start.isEnabled())

    def test_completion_and_error(self):
        self.ready()
        self.window.start_session()
        QTest.qWait(2400)
        self.assertFalse(self.window.running)
        self.assertIn("Demo abgeschlossen", self.window.output.toPlainText())
        self.window.start_session()
        self.window.fail_session()
        self.assertFalse(self.window.running)
        self.assertIn("Speicher reicht nicht", self.window.output.toPlainText())

    def test_pinned_icons_render(self):
        import hashlib
        import json
        manifest = json.loads((ASSETS / "icons/manifest.json").read_text())
        for name, digest in manifest["sha256"].items():
            self.assertEqual(hashlib.sha256((ASSETS / "icons" / name).read_bytes()).hexdigest(), digest)
            self.assertFalse(icon(name[:-4]).pixmap(20, 20).isNull())


if __name__ == "__main__":
    unittest.main()
