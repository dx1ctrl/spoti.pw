#!/usr/bin/env python3
"""Read-only, standard-library inspection of Spotify IPA inputs and spoti.pw builds.

Usage: python inspect_ipa.py PATH.ipa [--built] [--expected-version 9.1.78]
Prints JSON; exit 0 means all requested static checks passed, 1 means a failure.
Does not extract, execute, sign, or modify the archive. Device behavior is untested.
"""
import argparse
import hashlib
import json
import plistlib
import re
import struct
import sys
import zipfile
from collections import Counter
from pathlib import Path


THIN = {
    b"\xce\xfa\xed\xfe": ("<", False), b"\xcf\xfa\xed\xfe": ("<", True),
    b"\xfe\xed\xfa\xce": (">", False), b"\xfe\xed\xfa\xcf": (">", True),
}
FAT = {
    b"\xca\xfe\xba\xbe": (">", False), b"\xbe\xba\xfe\xca": ("<", False),
    b"\xca\xfe\xba\xbf": (">", True), b"\xbf\xba\xfe\xca": ("<", True),
}
ARCHES = {7: "i386", 0x1000007: "x86_64", 12: "arm", 0x100000C: "arm64"}
DYLIB_COMMANDS = {0xC, 0x18, 0x1F, 0x20, 0x23}


def unpack(fmt, data, offset=0):
    if offset < 0 or offset + struct.calcsize(fmt) > len(data):
        raise ValueError("Truncated Mach-O structure")
    return struct.unpack_from(fmt, data, offset)


def thin_macho(data):
    magic = bytes(data[:4])
    if magic not in THIN:
        raise ValueError("Not a thin Mach-O")
    endian, is64 = THIN[magic]
    header_size = 32 if is64 else 28
    if len(data) < header_size:
        raise ValueError("Truncated Mach-O header")
    cpu, subtype, filetype, ncmds, sizeofcmds, _ = unpack(endian + "6I", data, 4)
    end = header_size + sizeofcmds
    if end > len(data) or ncmds > sizeofcmds // 8:
        raise ValueError("Invalid Mach-O load-command bounds")
    loads, encryption = [], []
    offset = header_size
    for _ in range(ncmds):
        if offset + 8 > end:
            raise ValueError("Load-command header exceeds declared bounds")
        command, size = unpack(endian + "2I", data, offset)
        if size < 8 or size % 4 or offset + size > end:
            raise ValueError("Invalid Mach-O load-command size")
        base_command = command & 0x7FFFFFFF
        if base_command in DYLIB_COMMANDS:
            if size < 24:
                raise ValueError("Truncated dylib load command")
            name_offset = unpack(endian + "I", data, offset + 8)[0]
            if name_offset < 24 or name_offset >= size:
                raise ValueError("Invalid dylib name offset")
            raw = bytes(data[offset + name_offset:offset + size])
            if b"\0" not in raw:
                raise ValueError("Unterminated dylib install name")
            loads.append({"command": hex(command), "name": raw.split(b"\0", 1)[0].decode("utf-8", "replace")})
        elif base_command in (0x21, 0x2C):
            required = 24 if base_command == 0x2C else 20
            if size < required:
                raise ValueError("Truncated encryption load command")
            cryptoff, cryptsize, cryptid = unpack(endian + "3I", data, offset + 8)
            if cryptsize and cryptoff + cryptsize > len(data):
                raise ValueError("Encryption range exceeds Mach-O slice")
            encryption.append({"command": hex(command), "cryptid": cryptid,
                               "cryptoff": cryptoff, "cryptsize": cryptsize})
        offset += size
    if offset != end:
        raise ValueError("Load commands do not consume their declared size")
    return {"architecture": ARCHES.get(cpu, hex(cpu)), "cpu_type": cpu,
            "cpu_subtype": subtype, "filetype": filetype, "bits": 64 if is64 else 32,
            "encryption_commands": encryption, "dylib_loads": loads,
            "non_system_loads": [x["name"] for x in loads
                                 if not x["name"].startswith(("/System/Library/", "/usr/lib/"))]}


def inspect_macho(data):
    view = memoryview(data)
    magic = bytes(view[:4])
    if magic in THIN:
        return [thin_macho(view)]
    if magic not in FAT:
        raise ValueError("Executable is not a recognized Mach-O")
    endian, is64 = FAT[magic]
    count = unpack(endian + "I", view, 4)[0]
    entry_size = 32 if is64 else 20
    table_end = 8 + count * entry_size
    if not count or table_end > len(view):
        raise ValueError("Invalid fat Mach-O architecture table")
    result, ranges = [], []
    for i in range(count):
        pos = 8 + i * entry_size
        cpu, subtype = unpack(endian + "2I", view, pos)
        offset, size = unpack(endian + ("2Q" if is64 else "2I"), view, pos + 8)
        if offset < table_end or not size or offset + size > len(view):
            raise ValueError("Fat Mach-O slice exceeds archive member bounds")
        if any(offset < stop and offset + size > start for start, stop in ranges):
            raise ValueError("Overlapping fat Mach-O slices")
        ranges.append((offset, offset + size))
        item = thin_macho(view[offset:offset + size])
        if item["cpu_type"] != cpu or item["cpu_subtype"] != subtype:
            raise ValueError("Fat and thin Mach-O architecture fields disagree")
        item.update(fat_offset=offset, fat_size=size)
        result.append(item)
    return result


def inspect(path, built=False, expected_version="9.1.78"):
    result = {"path": str(path.resolve()), "built_checks": built, "errors": [], "warnings": []}
    errors, warnings = result["errors"], result["warnings"]
    with path.open("rb") as stream:
        result["sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    result["size_bytes"] = path.stat().st_size
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        result["zip_crc_ok"] = bad is None
        if bad:
            errors.append(f"ZIP CRC failure: {bad}")
        names = archive.namelist()
        duplicates = [name for name, count in Counter(names).items() if count > 1]
        if duplicates:
            errors.append("Duplicate ZIP members: " + ", ".join(duplicates))
        roots = sorted({match.group(1) for name in names
                        if (match := re.fullmatch(r"(Payload/[^/]+\.app/)Info\.plist", name))})
        if len(roots) != 1:
            raise ValueError(f"Expected one top-level app Info.plist; found {len(roots)}")
        app = roots[0]
        info = plistlib.loads(archive.read(app + "Info.plist"))
        if not isinstance(info, dict):
            raise ValueError("Host Info.plist is not a dictionary")
        keys = ("CFBundleIdentifier", "CFBundleShortVersionString", "CFBundleVersion",
                "CFBundleExecutable", "MinimumOSVersion", "UIDesignRequiresCompatibility",
                "NSSupportsLiveActivities", "NSSupportsLiveActivitiesFrequentUpdates")
        result["app_root"] = app
        result["info"] = {key: info.get(key) for key in keys}
        if info.get("CFBundleIdentifier") != "com.spotify.client":
            errors.append("Host bundle ID is not com.spotify.client")
        if str(info.get("CFBundleShortVersionString")) != expected_version:
            errors.append(f"Host version is not expected Spotify {expected_version}")
        executable = info.get("CFBundleExecutable")
        if not isinstance(executable, str) or not executable or "/" in executable or "\\" in executable:
            raise ValueError("Missing or invalid CFBundleExecutable")
        if executable != "Spotify":
            errors.append("Host executable is not named Spotify (flag extractor requires it)")
        if not info.get("CFBundleVersion"):
            errors.append("Host CFBundleVersion is missing")
        slices = inspect_macho(archive.read(app + executable))
        result["host_macho"] = slices
        if not any(item["architecture"] == "arm64" for item in slices):
            errors.append("Host has no arm64 Mach-O slice")
        for item in slices:
            if item["filetype"] != 2:
                errors.append(f"Host {item['architecture']} slice is not MH_EXECUTE")
            if any(command["cryptid"] != 0 for command in item["encryption_commands"]):
                errors.append(f"Host {item['architecture']} slice is marked encrypted (cryptid != 0)")
            if not item["encryption_commands"]:
                warnings.append(f"Host {item['architecture']} slice has no encryption command; no encrypted range is declared")
        dylibs = sorted(name for name in names if name.startswith(app) and name.lower().endswith(".dylib"))
        result["bundled_dylibs"] = dylibs
        result["recognized_mod_dylibs"] = [name for name in dylibs
                                           if name.rsplit("/", 1)[-1].lower() in
                                           ("spotifyglass.dylib", "spotifyglassappgroups.dylib")]
        if built:
            for key, value in (("UIDesignRequiresCompatibility", False),
                               ("NSSupportsLiveActivities", True),
                               ("NSSupportsLiveActivitiesFrequentUpdates", True)):
                if info.get(key) is not value:
                    errors.append(f"Built host plist must set {key}={value}")
            for expected in ("spotifyglass.dylib", "spotifyglassappgroups.dylib"):
                if not any(name.rsplit("/", 1)[-1].lower() == expected for name in dylibs):
                    errors.append(f"Missing injected {expected}")
                for item in slices:
                    if not any(load["name"].rsplit("/", 1)[-1].lower() == expected for load in item["dylib_loads"]):
                        errors.append(f"Host {item['architecture']} does not directly load {expected}")
            extension = app + "PlugIns/SpotifyGlassLiveActivity.appex/"
            extinfo = plistlib.loads(archive.read(extension + "Info.plist"))
            result["live_activity_info"] = extinfo
            for key in ("CFBundleShortVersionString", "CFBundleVersion"):
                if extinfo.get(key) != info.get(key):
                    errors.append(f"Live Activity {key} differs from host")
            if extinfo.get("CFBundleIdentifier") != info.get("CFBundleIdentifier") + ".liveactivity":
                errors.append("Live Activity bundle identifier differs from expected host suffix")
            if extinfo.get("MinimumOSVersion") != "17.0":
                errors.append("Live Activity minimum OS is not 17.0")
            if extinfo.get("NSExtension", {}).get("NSExtensionPointIdentifier") != "com.apple.widgetkit-extension":
                errors.append("Live Activity does not declare the WidgetKit extension point")
            result["live_activity_macho"] = inspect_macho(archive.read(extension + "SpotifyGlassLiveActivity"))
            widget = app + "PlugIns/WidgetExtension.appex/WidgetExtension"
            if widget in names:
                result["widget_macho"] = inspect_macho(archive.read(widget))
                for item in result["widget_macho"]:
                    if not any(load["name"].endswith("/SpotifyGlassAppGroups.dylib") for load in item["dylib_loads"]):
                        errors.append(f"Widget {item['architecture']} does not load the App Group shim")
            else:
                warnings.append("Original WidgetExtension is absent")
            actions = json.loads(archive.read(app + "Metadata.appintents/extract.actionsdata"))
            action_text = json.dumps(actions.get("actions", {}))
            intents = ("SGPlayQueuedTrackIntent", "SGLiveActivityActionIntent")
            result["host_intents_present"] = {intent: intent in action_text for intent in intents}
            for intent, present in result["host_intents_present"].items():
                if not present:
                    errors.append(f"Host metadata lacks {intent}")
        result["static_checks_passed"] = not errors
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ipa", type=Path)
    parser.add_argument("--built", action="store_true", help="Also check expected spoti.pw packaging")
    parser.add_argument("--expected-version", default="9.1.78")
    args = parser.parse_args()
    try:
        result = inspect(args.ipa, args.built, args.expected_version)
    except (OSError, ValueError, KeyError, TypeError, EOFError, RuntimeError,
            struct.error, zipfile.BadZipFile, plistlib.InvalidFileException) as exc:
        result = {"path": str(args.ipa.resolve()), "static_checks_passed": False,
                  "errors": [f"{type(exc).__name__}: {exc}"]}
    print(json.dumps(result, indent=2, ensure_ascii=True, default=str))
    return 0 if result["static_checks_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
