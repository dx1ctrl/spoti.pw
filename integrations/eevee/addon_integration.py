"""Add the spoti.pw Song tools and visual styles to Reincarnated settings."""
from pathlib import Path
import hashlib

SETTINGS = Path("Sources/EeveeSpotify/Settings/Views/EeveeSettingsView.swift")
MAKEFILE = Path("Makefile")
HASHES = {
    SETTINGS: "991aa96a5e791f72a25189c02838125896284a06f65e47403147b45d6fc0b400",
    MAKEFILE: "0387f23d6fd0092e38b72dee755edd04f3f7390dbb9e41bad0567b575ed269ad",
}
ADDONS = Path(__file__).with_name("addons")


def validated_text(root, relative):
    raw = (root / relative).read_bytes()
    text = raw.decode("utf-8").replace("\r\n", "\n")
    if "\r" in text or hashlib.sha256(text.encode()).hexdigest() != HASHES[relative]:
        raise ValueError(f"Unreviewed Reincarnated input: {relative}")
    if b"\r\n" in raw and b"\n" in raw.replace(b"\r\n", b""):
        raise ValueError(f"Mixed line endings: {relative}")
    return text, b"\r\n" in raw


def replace_once(text, before, after):
    if text.count(before) != 1:
        raise ValueError("Reincarnated settings target is missing or duplicated")
    return text.replace(before, after, 1)


def plan_patches(root):
    planned = []
    settings, crlf = validated_text(root, SETTINGS)
    settings = replace_once(settings, """            ForEach(Self.groups) { group in
                SettingsGroupSection(group: group) { entry in
                    SettingsNavigator.push(entry.make(), title: entry.key.localized)
                }
            }
""", """            ForEach(Self.groups) { group in
                SettingsGroupSection(group: group) { entry in
                    SettingsNavigator.push(entry.make(), title: entry.key.localized)
                }
            }

            Section(header: Text("spoti.pw")) {
                Button { SettingsNavigator.push(SpotiToolsView(), title: "Song tools") } label: {
                    SettingsLabel(title: "Song tools", icon: "music.note.list", color: Color(hex: "#64D2FF"), chevron: true)
                }
                Button { SettingsNavigator.push(SpotiVisualsView(), title: "Visual styles") } label: {
                    SettingsLabel(title: "Visual styles", icon: "sparkles", color: Color(hex: "#BF5AF2"), chevron: true)
                }
            }
""")
    settings = replace_once(
        settings,
        '            SettingsEntry(key: "lyrics", icon: "quote.bubble.fill", color: .blue) { AnyView(EeveeLyricsSettingsView()) },\n',
        "",
    )
    planned.append((root / SETTINGS, settings.replace("\n", "\r\n").encode() if crlf else settings.encode()))

    makefile, crlf = validated_text(root, MAKEFILE)
    makefile = replace_once(
        makefile,
        "EeveeSpotify_EXTRA_FRAMEWORKS = EeveeSwiftProtobuf",
        "EeveeSpotify_EXTRA_FRAMEWORKS = EeveeSwiftProtobuf\nEeveeSpotify_FRAMEWORKS += MediaPlayer",
    )
    planned.append((root / MAKEFILE, makefile.replace("\n", "\r\n").encode() if crlf else makefile.encode()))

    sources = sorted([*ADDONS.glob("SpotiTools*.swift"), *ADDONS.glob("SpotiVisual*.swift")])
    required = {"SpotiToolsModels.swift", "SpotiToolsView.swift", "SpotiVisualsView.swift",
                "SpotiVisualEffects.swift", "SpotiVisualEffects.x.swift", "SpotiVisualEvents.swift"}
    if not required.issubset({source.name for source in sources}):
        raise ValueError("Required Song tools or visual source files are missing")

    for source in sources:
        content = source.read_bytes().replace(b".eeveeSettingsListStyle()", b".eeveeSettingsStyle()")
        destination = root / "Sources/EeveeSpotify/SpotiTools" / source.name
        if destination.exists():
            raise ValueError(f"Refusing to overwrite an existing addon: {destination.name}")
        planned.append((destination, content))
    return planned
