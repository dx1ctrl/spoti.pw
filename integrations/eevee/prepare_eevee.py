#!/usr/bin/env python3
"""Disable Eevee lyric replacement when packaging it with spoti.pw.

SPDX-License-Identifier: GPL-3.0-only
Compatibility adaptation for EeveeSpotifyNext, derived from EeveeSpotify by
Eevee/whoeevee, the Meeep1/Skye Revived fork, and w3ltyyy's Next fork.
Upstream: https://github.com/w3ltyyy/EeveeSpotifyNext
Pinned source: 8a9e4c3c1ca9a8991023d8b16be159aa73420017
The upstream GPL-3.0 license and attribution must accompany this adaptation.

This does not establish compatibility with any additional Spotify version.
Only the two lyric-integration changes below are permitted. Premium and session
protection code are preserved. Both files are validated before either is written.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


PINNED_COMMIT = "8a9e4c3c1ca9a8991023d8b16be159aa73420017"
PREFERENCES_PATH = Path(
    "Sources/EeveeSpotify/Lyrics/Models/Settings/LyricsSource+UserDefaults.swift"
)
LOADER_PATH = Path("Sources/EeveeSpotify/DataLoaderServiceHooks.x.swift")


class PreparationError(Exception):
    """The input is not the reviewed, unmodified upstream source."""


@dataclass(frozen=True)
class SourcePatch:
    path: Path
    sha256: str
    before: str
    after: str


PATCHES = (
    SourcePatch(
        PREFERENCES_PATH,
        "7047372a18eed3c96e2f6d0c66575fa5d6001622d0d2d8e589086e1f4fe9615e",
        """        get {
            if let rawValue = container.object(forKey: lyricsSourceKey) as? Int {
                return LyricsSource(rawValue: rawValue) ?? .defaultSource
            }

            return LyricsSource.defaultSource
        }""",
        """        get {
            // spoti.pw supplies lyrics; never activate Eevee's replacement hooks.
            return .notReplaced
        }""",
    ),
    SourcePatch(
        LOADER_PATH,
        "cde96f8e90eab8c0e5e8d1e93b3d42174423c800a064960c32c92df3c3df8c4b",
        """        guard
            let url = task.currentRequest?.url,
            url.isLyrics,
            response.statusCode != 200""",
        """        guard
            BaseLyricsGroup.isActive,
            let url = task.currentRequest?.url,
            url.isLyrics,
            response.statusCode != 200""",
    ),
)


def verify_checkout(root: Path) -> None:
    """Require the reviewed commit, rather than a branch that can move."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise PreparationError("source must be a Git checkout of the pinned commit") from exc
    lines = result.stdout.splitlines()
    if len(lines) != 2 or Path(lines[0]).resolve() != root.resolve():
        raise PreparationError("source must point to the checkout root")
    if lines[1] != PINNED_COMMIT:
        raise PreparationError(f"expected Git HEAD {PINNED_COMMIT}; found {lines[1]}")


def apply_patches(root: Path) -> tuple[Path, ...]:
    """Validate all source bytes and exact matches, then make only these changes.

    LF and CRLF checkouts share a canonical hash; original line endings are kept.
    Already-patched inputs are rejected, as are edits outside the matched blocks.
    """
    planned: list[tuple[Path, bytes]] = []
    for patch in PATCHES:
        path = root / patch.path
        try:
            raw = path.read_bytes()
            decoded = raw.decode("utf-8")
        except (OSError, UnicodeError) as exc:
            raise PreparationError(f"cannot read UTF-8 source: {patch.path}") from exc

        text = decoded.replace("\r\n", "\n")
        if "\r" in text:
            raise PreparationError(f"unexpected line endings in {patch.path}")
        count = text.count(patch.before)
        if count != 1:
            raise PreparationError(f"expected exactly one patch target in {patch.path}; found {count}")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest != patch.sha256:
            raise PreparationError(f"upstream SHA-256 mismatch in {patch.path}: {digest}")

        replacement = text.replace(patch.before, patch.after, 1)
        if b"\r\n" in raw:
            if b"\n" in raw.replace(b"\r\n", b""):
                raise PreparationError(f"mixed line endings in {patch.path}")
            replacement = replacement.replace("\n", "\r\n")
        planned.append((path, replacement.encode("utf-8")))

    for path, replacement in planned:
        path.write_bytes(replacement)
    return tuple(path for path, _ in planned)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="EeveeSpotifyNext checkout at the pinned commit")
    args = parser.parse_args(argv)
    try:
        verify_checkout(args.source)
        changed = apply_patches(args.source)
    except (PreparationError, OSError) as exc:
        print(f"Eevee preparation refused: {exc}", file=sys.stderr)
        return 1
    for path in changed:
        print(f"Patched {path.relative_to(args.source)}")
    print("Eevee lyric replacement disabled; runtime compatibility still requires device testing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
