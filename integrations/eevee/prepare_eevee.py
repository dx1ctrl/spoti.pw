#!/usr/bin/env python3
"""Prepare pinned EeveeSpotifyReincarnated sources with spoti.pw additions."""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

PINNED_COMMIT = "ca363e63efd4730811a241ec48a5c0e4ef838112"
LYRICS = Path("Sources/EeveeSpotify/Lyrics/Models/Settings/LyricsSource+UserDefaults.swift")
LYRICS_SHA256 = "7047372a18eed3c96e2f6d0c66575fa5d6001622d0d2d8e589086e1f4fe9615e"
LYRICS_ORIGINAL = """        get {
            if let rawValue = container.object(forKey: lyricsSourceKey) as? Int {
                return LyricsSource(rawValue: rawValue) ?? .defaultSource
            }

            return LyricsSource.defaultSource
        }"""
LYRICS_REPLACEMENT = """        get {
            // spoti.pw supplies lyrics; keep Eevee's replacement hooks inactive.
            return .notReplaced
        }"""


class PreparationError(Exception):
    pass


def verify_checkout(root: Path) -> None:
    try:
        result = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel", "HEAD"],
                                capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise PreparationError("source must be a Git checkout of the pinned Reincarnated commit") from exc
    lines = result.stdout.splitlines()
    if len(lines) != 2 or Path(lines[0]).resolve() != root.resolve():
        raise PreparationError("source must point to the checkout root")
    if lines[1] != PINNED_COMMIT:
        raise PreparationError(f"expected Git HEAD {PINNED_COMMIT}; found {lines[1]}")


def plan_lyrics(root: Path) -> list[tuple[Path, bytes]]:
    path = root / LYRICS
    raw = path.read_bytes()
    text = raw.decode("utf-8").replace("\r\n", "\n")
    if "\r" in text or hashlib.sha256(text.encode()).hexdigest() != LYRICS_SHA256:
        raise PreparationError("Unreviewed Reincarnated lyrics settings source")
    if text.count(LYRICS_ORIGINAL) != 1:
        raise PreparationError("Reincarnated lyrics source target is missing or duplicated")
    updated = text.replace(LYRICS_ORIGINAL, LYRICS_REPLACEMENT, 1)
    if b"\r\n" in raw:
        if b"\n" in raw.replace(b"\r\n", b""):
            raise PreparationError("Mixed line endings in lyrics settings source")
        updated = updated.replace("\n", "\r\n")
    return [(path, updated.encode())]


def write_plan(planned: list[tuple[Path, bytes]]) -> tuple[Path, ...]:
    for path, content in planned:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return tuple(path for path, _ in planned)


def prepare_integration(root: Path) -> tuple[Path, ...]:
    import addon_integration

    planned = dict(plan_lyrics(root))
    for path, content in addon_integration.plan_patches(root):
        if path in planned:
            raise PreparationError(f"Conflicting integration patch for {path.name}")
        planned[path] = content
    return write_plan(list(planned.items()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="pinned EeveeSpotifyReincarnated checkout")
    args = parser.parse_args(argv)
    try:
        verify_checkout(args.source)
        changed = prepare_integration(args.source)
    except (PreparationError, OSError, ValueError) as exc:
        print(f"Eevee preparation refused: {exc}", file=sys.stderr)
        return 1
    for path in changed:
        print(f"Patched {path.relative_to(args.source)}")
    print("Prepared Reincarnated with spoti.pw Song tools and visual styles.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
