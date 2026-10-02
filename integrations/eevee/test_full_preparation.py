"""Regression checks for the complete, atomic pinned-source preparation."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import prepare_eevee
import session_reliability

FIXTURES = None


def snapshot(root):
    return {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


class IntegrationPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "eevee"
        shutil.copytree(FIXTURES / "Sources", self.root / "Sources")
        shutil.copy2(FIXTURES / "Makefile", self.root / "Makefile")

    def test_complete_preparation_keeps_lyrics_guard_and_removes_only_expiry_hook(self):
        original = (self.root / session_reliability.SOURCE).read_text(encoding="utf-8")
        prepare_eevee.prepare_integration(self.root)
        session = (self.root / session_reliability.SOURCE).read_text(encoding="utf-8")
        self.assertNotIn("class OauthAccessTokenBridgeHook", session)
        self.assertNotIn("func startExpiryExtender", session)
        self.assertTrue(session.startswith(original[:original.index(session_reliability.START)]))
        self.assertTrue(session.endswith(original[original.index(session_reliability.END):]))
        loader = (self.root / prepare_eevee.LOADER_PATH).read_text(encoding="utf-8")
        self.assertIn(prepare_eevee.PATCHES[1].after, loader)
        self.assertTrue((self.root / "Sources/EeveeSpotify/SpotiTools/SpotiToolsView.swift").is_file())
        settings = (self.root / "Sources/EeveeSpotify/Settings/Views/EeveeSettingsView.swift").read_text(encoding="utf-8")
        self.assertIn("with: SpotiToolsView()", settings)
        self.assertIn("with: SpotiVisualsView()", settings)
        tweak = (self.root / "Sources/EeveeSpotify/Tweak.x.swift").read_text(encoding="utf-8")
        original_tweak = (FIXTURES / "Sources/EeveeSpotify/Tweak.x.swift").read_text(encoding="utf-8")
        # A saved visual preference must not install new observers or hooks
        # during launch. Recovery keeps the original startup path byte-for-byte.
        self.assertEqual(tweak, original_tweak)
        self.assertNotIn("activateSpotiVisualEffects()", tweak)
        self.assertTrue((self.root / "Sources/EeveeSpotify/SpotiTools/SpotiVisualEffects.x.swift").is_file())
        self.assertNotIn("with: EeveeLyricsSettingsView()", settings)
        after = snapshot(self.root)
        with self.assertRaises((ValueError, prepare_eevee.PreparationError)):
            prepare_eevee.prepare_integration(self.root)
        self.assertEqual(after, snapshot(self.root))

    def test_late_addon_failure_writes_none_of_the_earlier_plans(self):
        path = self.root / "Makefile"
        path.write_bytes(path.read_bytes() + b"\n# upstream changed\n")
        before = snapshot(self.root)
        with self.assertRaisesRegex(ValueError, "Unreviewed input"):
            prepare_eevee.prepare_integration(self.root)
        self.assertEqual(before, snapshot(self.root))

    def test_changed_session_source_rejected_without_other_mutations(self):
        path = self.root / session_reliability.SOURCE
        path.write_bytes(path.read_bytes() + b"\n// unexpected change\n")
        before = snapshot(self.root)
        with self.assertRaisesRegex(ValueError, "Unreviewed OAuth"):
            prepare_eevee.prepare_integration(self.root)
        self.assertEqual(before, snapshot(self.root))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: test_full_preparation.py /path/to/pinned/EeveeSpotifyNext")
    FIXTURES = Path(sys.argv.pop(1)).resolve()
    prepare_eevee.verify_checkout(FIXTURES)
    unittest.main()
