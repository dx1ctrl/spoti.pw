"""Regression tests for dependency and preservation guarantees."""
import copy
import io
import tempfile
import unittest
from pathlib import Path
import zipfile

from inspect_ipa import inspect_macho
from test_inspect_ipa import executable
from verify_package import compare_preservation, require_load, runtime_dependencies, verify_base_digest


class PackageChecks(unittest.TestCase):
    def test_string_outside_load_commands_is_not_injection(self):
        binary = executable() + b"EeveeSpotify.dylib\0"
        with self.assertRaisesRegex(ValueError, "does not load"):
            require_load(inspect_macho(binary), "/EeveeSpotify.dylib", "Host")
        require_load(inspect_macho(executable(load="@rpath/EeveeSpotify.dylib")),
                     "/EeveeSpotify.dylib", "Host")

    def test_runtime_dependencies_are_conditional_and_transitive(self):
        root = "Payload/Spotify.app/"
        eevee = root + "Frameworks/EeveeSpotify.dylib"
        orion = root + "Frameworks/Orion.framework/Orion"
        substrate = root + "Frameworks/CydiaSubstrate.framework/CydiaSubstrate"

        def archive(members):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as output:
                for name, binary in members.items():
                    output.writestr(name, binary)
            return zipfile.ZipFile(stream)

        with archive({eevee: executable(load="/usr/lib/libSystem.B.dylib")}) as package:
            self.assertEqual(runtime_dependencies(package, root, eevee), [])
        members = {eevee: executable(load="@rpath/Orion.framework/Orion")}
        with archive(members) as package:
            with self.assertRaisesRegex(ValueError, "Missing runtime"):
                runtime_dependencies(package, root, eevee)
        members[orion] = executable(load="@loader_path/../CydiaSubstrate.framework/CydiaSubstrate")
        with archive(members) as package:
            with self.assertRaisesRegex(ValueError, "CydiaSubstrate"):
                runtime_dependencies(package, root, eevee)
        members[substrate] = executable(load="/usr/lib/libSystem.B.dylib")
        with archive(members) as package:
            self.assertEqual(runtime_dependencies(package, root, eevee), sorted([orion, substrate]))

    def test_plist_changes_and_unrecognized_base_are_rejected(self):
        base = {"extensions": ["widget"], "metadata": {"actions": b"{}"},
                "plists": {"app": {"NSSupportsLiveActivities": True}, "widget": {"version": "1"}}}
        compare_preservation(copy.deepcopy(base), base)
        changed = copy.deepcopy(base)
        changed["plists"]["app"]["NSSupportsLiveActivities"] = False
        with self.assertRaisesRegex(ValueError, "Info.plist"):
            compare_preservation(changed, base)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "other.ipa"
            path.write_bytes(b"different base")
            with self.assertRaisesRegex(ValueError, "differs from the verified"):
                verify_base_digest(path)


if __name__ == "__main__":
    unittest.main()
