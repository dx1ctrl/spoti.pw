"""Validate the pinned base IPA and preservation after Eevee injection."""
import argparse
import hashlib
import json
import plistlib
import posixpath
from pathlib import Path
import zipfile

from inspect_ipa import inspect_macho

BASE_SHA256 = "07d51db51a5468c8b42308078c929ceaf4eb21fea8fde930fc599a15cccecc57"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_base_digest(path):
    actual = sha256(path)
    if actual != BASE_SHA256:
        raise ValueError(f"Base IPA differs from the verified spoti.pw 0.22.0 build: {actual}")


def require_load(slices, suffix, label):
    for item in slices:
        if not any(load["name"].endswith(suffix) for load in item["dylib_loads"]):
            raise ValueError(f"{label} ({item['architecture']}) does not load {suffix}")


def runtime_dependencies(package, root, eevee_path):
    """Follow actual Orion/Substrate references, including Orion's weak dependency."""
    checked = set()
    pending = [eevee_path]
    names = set(package.namelist())
    while pending:
        member = pending.pop()
        if member in checked:
            continue
        checked.add(member)
        for item in inspect_macho(package.read(member)):
            for load in item["dylib_loads"]:
                name = load["name"]
                if not any(token in name.lower() for token in ("orion.", "substrate.")):
                    continue
                if name.startswith("@rpath/"):
                    dependency = root + "Frameworks/" + name.removeprefix("@rpath/")
                elif name.startswith("@loader_path/"):
                    dependency = member.rsplit("/", 1)[0] + "/" + name.removeprefix("@loader_path/")
                elif name.startswith("@executable_path/"):
                    dependency = root + name.removeprefix("@executable_path/")
                else:
                    raise ValueError(f"Unresolved jailbreak runtime dependency in {member}: {name}")
                dependency = posixpath.normpath(dependency)
                if dependency not in names:
                    raise ValueError(f"Missing runtime required by {member}: {dependency}")
                pending.append(dependency)
    return sorted(checked - {eevee_path})


def inspect(path, combined=False):
    with zipfile.ZipFile(path) as package:
        bad = package.testzip()
        if bad:
            raise ValueError(f"ZIP CRC failed: {bad}")
        all_names = package.namelist()
        names = set(all_names)
        if len(names) != len(all_names):
            raise ValueError("Duplicate ZIP members")
        roots = [name for name in names if name.startswith("Payload/")
                 and name.count("/") == 2 and name.endswith(".app/Info.plist")]
        if len(roots) != 1:
            raise ValueError("Expected exactly one main application")
        info_path = roots[0]
        info = plistlib.loads(package.read(info_path))
        if info.get("CFBundleShortVersionString") != "9.1.78":
            raise ValueError("This integration is only checked against Spotify 9.1.78")
        if info.get("CFBundleIdentifier") != "com.spotify.client" or info.get("CFBundleExecutable") != "Spotify":
            raise ValueError("Unexpected Spotify bundle ID or executable")
        root = info_path.removesuffix("Info.plist")
        main_slices = inspect_macho(package.read(root + info["CFBundleExecutable"]))
        for name in ("spotifyglass.dylib", "SpotifyGlassAppGroups.dylib"):
            if root + "Frameworks/" + name not in names:
                raise ValueError(f"The package is missing {name}")
            require_load(main_slices, "/" + name, "Main executable")
        widget_path = root + "PlugIns/WidgetExtension.appex/WidgetExtension"
        require_load(inspect_macho(package.read(widget_path)), "/SpotifyGlassAppGroups.dylib", "Widget executable")
        extensions = sorted(name for name in names if name.startswith(root + "PlugIns/")
                            and name.endswith(".appex/Info.plist"))
        if root + "PlugIns/SpotifyGlassLiveActivity.appex/Info.plist" not in extensions:
            raise ValueError("The Live Activity extension is missing")
        plists = {name: plistlib.loads(package.read(name)) for name in [info_path, *extensions]}
        for name, values in plists.items():
            executable = name.removesuffix("Info.plist") + values["CFBundleExecutable"]
            if executable not in names:
                raise ValueError(f"Missing bundle executable: {executable}")
        metadata = {name: package.read(name) for name in names
                    if name.startswith(root) and "/Metadata.appintents/" in name
                    and not name.endswith("/")}
        runtimes = []
        if combined:
            eevee_path = root + "Frameworks/EeveeSpotify.dylib"
            for relative in ("Frameworks/EeveeSpotify.dylib", "Frameworks/SwiftProtobuf.framework/SwiftProtobuf",
                             "EeveeSpotify.bundle/resolveconfiguration.bnk",
                             "EeveeSpotify.bundle/en.lproj/Localizable.strings"):
                if root + relative not in names:
                    raise ValueError(f"Missing injected dependency/resource: {relative}")
            require_load(main_slices, "/EeveeSpotify.dylib", "Main executable")
            eevee_slices = inspect_macho(package.read(eevee_path))
            require_load(eevee_slices, "/SwiftProtobuf.framework/SwiftProtobuf", "Eevee executable")
            runtimes = runtime_dependencies(package, root, eevee_path)
        return {"root": root, "version": info["CFBundleShortVersionString"],
                "extensions": extensions, "metadata": metadata, "plists": plists,
                "runtime_dependencies": runtimes}


def compare_preservation(result, base):
    if result["extensions"] != base["extensions"]:
        raise ValueError("Injection changed the extension inventory")
    if result["plists"] != base["plists"]:
        raise ValueError("Injection changed an existing application or extension Info.plist")
    if result["metadata"] != base["metadata"]:
        raise ValueError("Injection changed the existing App Intents metadata")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--combined", action="store_true")
    parser.add_argument("--base", type=Path)
    args = parser.parse_args()
    files = list(args.directory.glob("*.ipa"))
    if len(files) != 1:
        parser.error("Expected one IPA in the input directory")
    if args.combined:
        if not args.base:
            parser.error("--combined requires --base")
        verify_base_digest(args.base)
        base = inspect(args.base)
    else:
        verify_base_digest(files[0])
    result = inspect(files[0], combined=args.combined)
    if args.combined:
        compare_preservation(result, base)
    print(json.dumps({"file": files[0].name, "spotify": result["version"],
                      "extensions": result["extensions"], "combined": args.combined,
                      "runtime_dependencies": result["runtime_dependencies"],
                      "sha256": sha256(files[0])}, indent=2))


if __name__ == "__main__":
    main()
