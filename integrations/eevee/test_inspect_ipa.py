"""Small synthetic regression checks for the internal IPA inspector."""
import hashlib
import plistlib
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

from inspect_ipa import inspect, inspect_macho


def executable(cryptid=0, load="@rpath/Test.dylib", endian="<", bits=64, cpu=0x100000C):
    raw_name = load.encode() + b"\0"
    cmdsize = (24 + len(raw_name) + 7) & ~7
    command = struct.pack(endian + "6I", 0x80000018, cmdsize, 24, 0, 0, 0)
    command += raw_name.ljust(cmdsize - 24, b"\0")
    command += struct.pack(endian + "6I", 0x2C, 24, 0, 0, cryptid, 0)
    values = [0xFEEDFACF if bits == 64 else 0xFEEDFACE, cpu, 0, 2, 2, len(command), 0]
    if bits == 64:
        values.append(0)
    return struct.pack(endian + "I" * len(values), *values) + command


def make_ipa(path, binary, version="9.1.78"):
    info = {"CFBundleIdentifier": "com.spotify.client", "CFBundleVersion": "90178000",
            "CFBundleShortVersionString": version, "CFBundleExecutable": "Spotify",
            "MinimumOSVersion": "16.1"}
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("Payload/Spotify.app/Info.plist", plistlib.dumps(info, fmt=plistlib.FMT_BINARY))
        archive.writestr("Payload/Spotify.app/Spotify", binary)


class InspectorChecks(unittest.TestCase):
    def test_thin_byte_orders_and_widths(self):
        for endian, bits, cpu, arch in [("<", 64, 0x100000C, "arm64"),
                                       (">", 32, 12, "arm")]:
            item = inspect_macho(executable(endian=endian, bits=bits, cpu=cpu))[0]
            self.assertEqual(item["architecture"], arch)
            self.assertEqual(item["encryption_commands"][0]["cryptid"], 0)
            self.assertEqual(item["dylib_loads"][0]["name"], "@rpath/Test.dylib")

    def test_fat32_and_fat64_tables(self):
        arm = executable()
        intel = executable(cpu=0x1000007, cryptid=1)
        for wide in (False, True):
            offset = 4096
            next_offset = 8192
            header = struct.pack(">2I", 0xCAFEBABF if wide else 0xCAFEBABE, 2)
            for cpu, start, binary in ((0x100000C, offset, arm), (0x1000007, next_offset, intel)):
                header += struct.pack(">2I2Q2I", cpu, 0, start, len(binary), 12, 0) if wide else struct.pack(">5I", cpu, 0, start, len(binary), 12)
            data = header.ljust(offset, b"\0") + arm
            data = data.ljust(next_offset, b"\0") + intel
            result = inspect_macho(data)
            self.assertEqual([s["architecture"] for s in result], ["arm64", "x86_64"])
            self.assertEqual(result[1]["encryption_commands"][0]["cryptid"], 1)

    def test_rejects_truncated_and_bad_command_bounds(self):
        valid = executable()
        for invalid in (b"not Mach-O", valid[:20], valid[:-1]):
            with self.assertRaises(ValueError):
                inspect_macho(invalid)
        malformed = bytearray(valid)
        struct.pack_into("<I", malformed, 36, 0xFFFFFFF8)
        with self.assertRaises(ValueError):
            inspect_macho(malformed)

    def test_ipa_pass_hash_read_only_and_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.ipa"
            make_ipa(path, executable())
            before = path.read_bytes()
            result = inspect(path)
            self.assertTrue(result["static_checks_passed"], result)
            self.assertTrue(result["zip_crc_ok"])
            self.assertEqual(result["sha256"], hashlib.sha256(before).hexdigest())
            self.assertEqual(path.read_bytes(), before)
            make_ipa(path, executable(cryptid=1))
            result = inspect(path)
            self.assertFalse(result["static_checks_passed"])
            self.assertTrue(any("encrypted" in error for error in result["errors"]))
            make_ipa(path, executable(), version="9.1.77")
            self.assertFalse(inspect(path)["static_checks_passed"])
            make_ipa(path, executable())
            data = bytearray(path.read_bytes())
            pos = data.index(b"bplist00")
            data[pos] ^= 1
            path.write_bytes(data)
            with zipfile.ZipFile(path) as archive:
                self.assertEqual(archive.testzip(), "Payload/Spotify.app/Info.plist")
            with self.assertRaises(zipfile.BadZipFile):
                inspect(path)


if __name__ == "__main__":
    unittest.main()
