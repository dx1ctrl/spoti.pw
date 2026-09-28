"""Offline integration tests against temporary copies of pinned upstream files.

SPDX-License-Identifier: GPL-3.0-only
Fixtures derive from EeveeSpotifyNext by Eevee/whoeevee, Meeep1/Skye, and
w3ltyyy, commit 8a9e4c3c1ca9a8991023d8b16be159aa73420017 (GPL-3.0).
Usage: python test_prepare_eevee.py /path/to/pinned/EeveeSpotifyNext
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import prepare_eevee as preparation


FIXTURES: Path | None = None
UNCHANGED_PATHS = (
    Path("Sources/EeveeSpotify/SessionProtection.x.swift"),
    Path("Sources/EeveeSpotify/Tweak.x.swift"),
)


class PrepareEeveeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "source"
        if FIXTURES is None:
            self.fail("pass the pinned upstream checkout as the test script argument")
        for relative in (preparation.PREFERENCES_PATH, preparation.LOADER_PATH, *UNCHANGED_PATHS):
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Normalize fixture line endings; a separate test covers CRLF inputs.
            destination.write_bytes((FIXTURES / relative).read_text(encoding="utf-8").encode("utf-8"))
        self.original = {
            path.relative_to(self.root): path.read_bytes()
            for path in self.root.rglob("*") if path.is_file()
        }

    def test_only_two_lyrics_changes_preserving_settings_and_premium_code(self):
        changed = preparation.apply_patches(self.root)
        self.assertEqual({p.relative_to(self.root) for p in changed}, {
            preparation.PREFERENCES_PATH, preparation.LOADER_PATH,
        })
        expected_preferences = self.original[preparation.PREFERENCES_PATH].decode().replace(
            """            if let rawValue = container.object(forKey: lyricsSourceKey) as? Int {
                return LyricsSource(rawValue: rawValue) ?? .defaultSource
            }

            return LyricsSource.defaultSource""",
            """            // spoti.pw supplies lyrics; never activate Eevee's replacement hooks.
            return .notReplaced""",
        )
        self.assertEqual((self.root / preparation.PREFERENCES_PATH).read_text(encoding="utf-8"), expected_preferences)
        original_loader = self.original[preparation.LOADER_PATH].decode()
        expected_loader = original_loader.replace(
            "        guard\n            let url = task.currentRequest?.url,\n            url.isLyrics,",
            "        guard\n            BaseLyricsGroup.isActive,\n            let url = task.currentRequest?.url,\n            url.isLyrics,",
        )
        self.assertEqual((self.root / preparation.LOADER_PATH).read_text(encoding="utf-8"), expected_loader)
        for relative, content in self.original.items():
            if relative not in {preparation.PREFERENCES_PATH, preparation.LOADER_PATH}:
                self.assertEqual((self.root / relative).read_bytes(), content)

    def test_changed_upstream_outside_target_fails_before_any_write(self):
        loader = self.root / preparation.LOADER_PATH
        loader.write_bytes(loader.read_bytes() + b"// unexpected upstream change\n")
        before = {p: (self.root / p).read_bytes() for p in self.original}
        with self.assertRaisesRegex(preparation.PreparationError, "SHA-256 mismatch"):
            preparation.apply_patches(self.root)
        self.assertEqual(before, {p: (self.root / p).read_bytes() for p in self.original})

    def test_missing_or_duplicate_target_is_rejected_without_partial_write(self):
        loader = self.root / preparation.LOADER_PATH
        original = self.original[preparation.LOADER_PATH]
        target = preparation.PATCHES[1].before.encode()
        for malformed in (original.replace(target, b"// missing target"), original + target):
            with self.subTest(duplicated=malformed.endswith(target)):
                loader.write_bytes(malformed)
                with self.assertRaisesRegex(preparation.PreparationError, "exactly one patch target"):
                    preparation.apply_patches(self.root)
                self.assertEqual(loader.read_bytes(), malformed)
                self.assertEqual(
                    (self.root / preparation.PREFERENCES_PATH).read_bytes(),
                    self.original[preparation.PREFERENCES_PATH],
                )

    def test_crlf_is_preserved_and_second_application_is_rejected(self):
        for source_patch in preparation.PATCHES:
            path = self.root / source_patch.path
            path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        preparation.apply_patches(self.root)
        for source_patch in preparation.PATCHES:
            content = (self.root / source_patch.path).read_bytes()
            self.assertIn(b"\r\n", content)
            self.assertNotIn(b"\n", content.replace(b"\r\n", b""))
        with self.assertRaises(preparation.PreparationError):
            preparation.apply_patches(self.root)

    def test_cli_rejects_wrong_commit_before_changes(self):
        result = type("GitResult", (), {"stdout": f"{self.root.resolve()}\n{'0' * 40}\n"})()
        with patch.object(preparation.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(preparation.PreparationError, "expected Git HEAD"):
                preparation.verify_checkout(self.root)
        self.assertEqual(self.original, {p: (self.root / p).read_bytes() for p in self.original})


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: test_prepare_eevee.py /path/to/pinned/EeveeSpotifyNext")
    FIXTURES = Path(sys.argv.pop(1)).resolve()
    preparation.verify_checkout(FIXTURES)
    unittest.main()
