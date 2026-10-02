"""Wire the independent Song tools and visual styles into pinned Eevee.

SPDX-License-Identifier: GPL-3.0-only
Eevee settings adaptation based on EeveeSpotifyNext (see bundled LICENSE).
All input validation happens before callers write any files.
"""
from pathlib import Path
import hashlib

SETTINGS = Path("Sources/EeveeSpotify/Settings/Views/EeveeSettingsView.swift")
MAKEFILE = Path("Makefile")
HASHES = {
    SETTINGS: "313d1c87f3091fc065283f16643cc29099dfda1ddbb8ffdefdacb61014b0da72",
    MAKEFILE: "2868eeec16e51670bb38f1481168ba77eb770bb2c5284085a89681dff067c2b6",
}
ADDONS = Path(__file__).with_name("addons")


def validated_text(root, relative):
    raw = (root / relative).read_bytes()
    text = raw.decode("utf-8").replace("\r\n", "\n")
    if "\r" in text or hashlib.sha256(text.encode()).hexdigest() != HASHES[relative]:
        raise ValueError(f"Unreviewed input for Song tools: {relative}")
    if b"\r\n" in raw and b"\n" in raw.replace(b"\r\n", b""):
        raise ValueError(f"Mixed line endings: {relative}")
    return text, b"\r\n" in raw


def replace_once(text, before, after):
    if text.count(before) != 1:
        raise ValueError("Song tools settings target is missing or duplicated")
    return text.replace(before, after, 1)


def plan_patches(root):
    planned = []
    settings, crlf = validated_text(root, SETTINGS)
    settings = replace_once(settings, "            EeveeSettingsVersionView()", '''            EeveeSettingsVersionView()

            Button {
                pushSettingsController(with: SpotiToolsView(), title: "Song tools")
            } label: {
                NavigationSectionView(
                    color: Color(hex: "#64D2FF"),
                    title: "Song tools",
                    imageSystemName: "music.note.list"
                )
            }
            Button {
                pushSettingsController(with: SpotiVisualsView(), title: "Visual styles")
            } label: {
                NavigationSectionView(
                    color: Color(hex: "#BF5AF2"),
                    title: "Visual styles",
                    imageSystemName: "sparkles"
                )
            }
            Text("spoti.pw integration · Visuals 2 recovery")
                .font(.caption)
                .foregroundColor(.secondary)''')
    # The integration disables Eevee lyrics in code. Show the real control location
    # instead of offering knobs which can never affect this package.
    settings = replace_once(settings, '''            Button {
                pushSettingsController(
                    with: EeveeLyricsSettingsView(),
                    title: "lyrics".localized
                )
            } label: {
                NavigationSectionView(
                    color: .blue,
                    title: "lyrics".localized,
                    imageSystemName: "quote.bubble.fill"
                )
            }''', '''            Section(header: Text("Lyrics")) {
                Text("Manage lyrics in Mod Settings → Player → Lyrics.")
                    .foregroundColor(.secondary)
            }''')
    planned.append((root / SETTINGS, settings.replace("\n", "\r\n").encode() if crlf else settings.encode()))
    makefile, crlf = validated_text(root, MAKEFILE)
    # This integration is locked to Spotify 9.1.78, whose own deployment floor is
    # iOS 16.1. Compile the companion UI against that same supported floor.
    makefile = replace_once(makefile, "TARGET := iphone:clang:latest:14.0", "TARGET := iphone:clang:latest:16.1")
    makefile = replace_once(makefile, "EeveeSpotify_EXTRA_FRAMEWORKS = SwiftProtobuf", "EeveeSpotify_EXTRA_FRAMEWORKS = SwiftProtobuf\nEeveeSpotify_FRAMEWORKS += MediaPlayer")
    planned.append((root / MAKEFILE, makefile.replace("\n", "\r\n").encode() if crlf else makefile.encode()))
    # Never initialize the visual registry or hooks from Eevee's startup path.
    # The recovery build requires an explicit Apply/style tap each session.
    sources = sorted([*ADDONS.glob("SpotiTools*.swift"), *ADDONS.glob("SpotiVisual*.swift")])
    required = {"SpotiToolsModels.swift", "SpotiToolsView.swift", "SpotiVisualsView.swift",
                "SpotiVisualEffects.swift", "SpotiVisualEffects.x.swift", "SpotiVisualEvents.swift"}
    if not required.issubset({source.name for source in sources}):
        raise ValueError("Required companion source files are missing")
    for source in sources:
        destination = root / "Sources/EeveeSpotify/SpotiTools" / source.name
        if destination.exists():
            raise ValueError(f"Refusing to overwrite an existing addon: {destination.name}")
        planned.append((destination, source.read_bytes()))
    return planned
