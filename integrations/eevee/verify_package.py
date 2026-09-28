"""Check the known Spotify version and preservation of the existing mod package."""
import argparse
import hashlib
import json
import plistlib
from pathlib import Path
import zipfile


def inspect(path):
    with zipfile.ZipFile(path) as package:
        bad = package.testzip()
        if bad:
            raise ValueError(f"ZIP CRC failed: {bad}")
        names = set(package.namelist())
        roots = [name for name in names if name.startswith("Payload/")
                 and name.count("/") == 2 and name.endswith(".app/Info.plist")]
        if len(roots) != 1:
            raise ValueError("Expected exactly one main application")
        info_path = roots[0]
        info = plistlib.loads(package.read(info_path))
        if info.get("CFBundleShortVersionString") != "9.1.78":
            raise ValueError("This integration is only checked against Spotify 9.1.78")
        root = info_path.removesuffix("Info.plist")
        for suffix in ("/spotifyglass.dylib", "/SpotifyGlassAppGroups.dylib"):
            if not any(name.endswith(suffix) for name in names):
                raise ValueError(f"The input is missing {suffix}")
        extensions = sorted(name for name in names if name.startswith(root + "PlugIns/")
                            and name.endswith(".appex/Info.plist"))
        if not any("SpotifyGlassLiveActivity.appex/" in name for name in extensions):
            raise ValueError("The Live Activity extension is missing")
        metadata = {name: package.read(name) for name in names
                    if name.startswith(root) and "/Metadata.appintents/" in name
                    and not name.endswith("/")}
        return {"root": root, "version": info["CFBundleShortVersionString"],
                "names": names, "extensions": extensions, "metadata": metadata,
                "main": package.read(root + info["CFBundleExecutable"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--combined", action="store_true")
    parser.add_argument("--base", type=Path)
    args = parser.parse_args()
    files = list(args.directory.glob("*.ipa"))
    if len(files) != 1:
        parser.error("Expected one IPA in the input directory")
    result = inspect(files[0])
    if args.combined:
        if not args.base:
            parser.error("--combined requires --base")
        base = inspect(args.base)
        if result["extensions"] != base["extensions"]:
            raise ValueError("Injection changed the extension inventory")
        if result["metadata"] != base["metadata"]:
            raise ValueError("Injection changed the existing App Intents metadata")
        for suffix in ("/EeveeSpotify.dylib", "/SwiftProtobuf.framework/SwiftProtobuf",
                       "/EeveeSpotify.bundle/Info.plist",
                       "/EeveeSpotify.bundle/resolveconfiguration.bnk"):
            if not any(name.endswith(suffix) for name in result["names"]):
                raise ValueError(f"Missing injected dependency: {suffix}")
        if b"EeveeSpotify.dylib" not in result["main"]:
            raise ValueError("The main executable does not reference EeveeSpotify")
    print(json.dumps({"file": files[0].name, "spotify": result["version"],
                      "extensions": result["extensions"], "combined": args.combined,
                      "sha256": hashlib.sha256(files[0].read_bytes()).hexdigest()}, indent=2))


if __name__ == "__main__":
    main()
