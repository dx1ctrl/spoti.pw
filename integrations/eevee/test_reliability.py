"""Regression tests using original pinned fixtures and real Foundation Swift code.

SPDX-License-Identifier: GPL-3.0-only
Usage: python test_reliability.py /path/to/original/EeveeSpotifyNext
Only Windows without a Swift compiler skips the Swift runtime test. macOS CI
fails if swiftc is missing. No network requests are started by these tests.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import reliability


FIXTURES: Path | None = None


SWIFT_TESTS = r'''
enum BasePremiumPatchingGroup { static var isActive = true }
enum HookTarget { case v91, legacy }
enum EeveeSpotify { static var hookTarget = HookTarget.v91 }
let tweakInitTime = Date(timeIntervalSinceNow: -60)

@main struct ReliabilityTests {
    static func main() {
        func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
            precondition(condition(), message)
        }
        let root = "https://spclient.wg.spotify.com"
        for service in ["Ads", "Events", "Formats", "InStream", "Slots", "State", "Targeting", "Settings", "Preview", "Testing", "PodcastTesting"] {
            let url = URL(string: "\(root)/esperanto/spotify.ads.esperanto.proto.\(service)/GetAds")!
            expect(url.isAdRelated, "known advertising namespace: \(service)")
        }
        // Real non-ad service identifiers from the host binary; URLs are constructed fixtures.
        for service in [
            "spotify.metadata_esperanto.proto.ClassicMetadataService/GetMetadata",
            "spotify.mdata_esperanto.proto.MetadataService/GetMetadata",
            "spotify.download.esperanto.proto.Download/RequestSegmentData",
            "spotify.connectivity.traffic.esperanto.proto.TrafficAdapter/GetState",
            "spotify.read_reporting_esperanto.proto.ReadReportingService/Read",
            "spotify.player.proto.Player/Load",
            "spotify.ads.esperanto.proto.SlotsExtra/Get",
            "spotify.ads.esperanto.proto.Unknown/Get"
        ] {
            let url = URL(string: "\(root)/esperanto/\(service)")!
            expect(!url.isAdRelated, "must preserve non-allowlisted service \(service)")
        }
        for path in ["/metadata/adaptive", "/esperanto/", "/esperanto", "/ever-adaptive/slot", "/adsong/Load"] {
            expect(!URL(string: root + path)!.isAdRelated, "substring false positive: \(path)")
        }
        for path in ["/ads/v1/request", "/ad-logic/v1/request", "/dac/view/v1/display"] {
            expect(URL(string: root + path)!.isAdRelated, "existing explicit ad route \(path)")
        }
        for path in ["/product-state/v1", "/auth/expire", "/license/check", "/token/revoke", "/session/purge", "/apresolve", "/v1/customize"] {
            expect(!shouldBlock(URL(string: root + path)!), "v9.1 session refresh must pass: \(path)")
        }
        BasePremiumPatchingGroup.isActive = false
        expect(!shouldBlock(URL(string: root + "/ads/v1/request")!), "disabled patch must pass requests")
        BasePremiumPatchingGroup.isActive = true
        expect(shouldBlock(URL(string: root + "/ads/v1/request")!), "enabled explicit ad route")
        EeveeSpotify.hookTarget = .legacy
        expect(shouldBlock(URL(string: root + "/session/purge")!), "legacy behavior preserved")

        let sessionA = URLSession(configuration: .ephemeral)
        let sessionB = URLSession(configuration: .ephemeral)
        defer { sessionA.invalidateAndCancel(); sessionB.invalidateAndCancel() }
        let endpoint = URL(string: root + "/v1/customize")!
        let taskA = sessionA.dataTask(with: endpoint)
        let taskB = sessionB.dataTask(with: endpoint)
        let loader = TaskResponseBuffer()
        let bootstrap = TaskResponseBuffer()
        loader.append(Data("a".utf8), for: taskA)
        loader.append(Data("b".utf8), for: taskB)
        loader.append(Data("c".utf8), for: taskA)
        bootstrap.append(Data("bootstrap".utf8), for: taskA)
        expect(loader.take(for: taskA) == Data("ac".utf8), "same URL tasks must not merge")
        expect(loader.take(for: taskA) == nil, "terminal take must clear buffer")
        expect(loader.take(for: taskB) == Data("b".utf8), "other task must remain intact")
        expect(bootstrap.take(for: taskA) == Data("bootstrap".utf8), "hook buffers must be independent")
        DispatchQueue.concurrentPerform(iterations: 1000) { index in
            loader.append(Data([UInt8(index % 2)]), for: index % 2 == 0 ? taskA : taskB)
        }
        expect(loader.take(for: taskA) == Data(repeating: 0, count: 500), "concurrent task A chunks")
        expect(loader.take(for: taskB) == Data(repeating: 1, count: 500), "concurrent task B chunks")
        let markers = CustomizeStateStore.shared
        markers.markHandledCustomizeTask(taskA)
        expect(!markers.consumeHandledCustomizeTask(taskB), "session task identifiers must not collide")
        expect(markers.consumeHandledCustomizeTask(taskA), "marked task must be found")
        expect(!markers.consumeHandledCustomizeTask(taskA), "marker must be consumed once")
        print("Swift network reliability tests passed")
    }
}
'''


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "source"
        assert FIXTURES is not None
        for relative in reliability.ORIGINAL_HASHES:
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((FIXTURES / relative).read_bytes().replace(b"\r\n", b"\n"))
        self.original = self.snapshot()

    def snapshot(self):
        return {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def test_plan_is_read_only_and_preserves_coexistence_guard(self):
        plan = dict(reliability.plan_patches(self.root))
        self.assertEqual(self.snapshot(), self.original)
        self.assertEqual(set(plan), {self.root / p for p in (*reliability.ORIGINAL_HASHES, reliability.SUPPORT)})
        loader = plan[self.root / reliability.LOADER].decode()
        self.assertIn("""        guard
            BaseLyricsGroup.isActive,
            let url = task.currentRequest?.url,
            url.isLyrics,
            response.statusCode != 200""", loader)
        self.assertNotIn("task.taskIdentifier", loader)
        self.assertNotIn("obtainData(for: url)", loader)
        bootstrap = plan[self.root / reliability.BOOTSTRAP].decode()
        self.assertIn("URLSessionHelper.bootstrap.obtainData(for: task)", bootstrap)
        self.assertNotIn("URLSessionHelper.shared", bootstrap)
        for body in (loader, bootstrap):
            self.assertIn("task.currentRequest?.url ?? task.originalRequest?.url", body)
            self.assertIn("if let data = bufferedData", body)

    def test_changed_input_and_existing_support_refuse_without_writes(self):
        for relative in reliability.ORIGINAL_HASHES:
            with self.subTest(source=relative):
                path = self.root / relative
                path.write_bytes(self.original[relative] + b"// changed upstream\n")
                before = self.snapshot()
                with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                    reliability.plan_patches(self.root)
                self.assertEqual(before, self.snapshot())
                path.write_bytes(self.original[relative])
        support = self.root / reliability.SUPPORT
        support.write_bytes(b"// existing support must not be overwritten\n")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "already exists"):
            reliability.plan_patches(self.root)
        self.assertEqual(before, self.snapshot())

    def test_crlf_and_second_application(self):
        for relative, data in self.original.items():
            (self.root / relative).write_bytes(data.replace(b"\n", b"\r\n"))
        plan = reliability.plan_patches(self.root)
        for path, data in plan:
            if path.relative_to(self.root) != reliability.SUPPORT:
                self.assertIn(b"\r\n", data)
                self.assertNotIn(b"\n", data.replace(b"\r\n", b""))
            path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            reliability.plan_patches(self.root)

    def test_mixed_line_endings_refuse(self):
        path = self.root / reliability.LOADER
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n", 1))
        with self.assertRaisesRegex(ValueError, "line endings"):
            reliability.plan_patches(self.root)

    def test_swift_foundation_regressions(self):
        swiftc = shutil.which("swiftc")
        if swiftc is None:
            if sys.platform == "win32":
                self.skipTest("Swift compiler unavailable on Windows; macOS CI requires it")
            self.fail("Swift compiler is required on macOS/Linux CI")
        plan = dict(reliability.plan_patches(self.root))
        directory = Path(self.temporary.name)
        support = directory / "NetworkReliability.swift"
        support.write_bytes(plan[self.root / reliability.SUPPORT])
        extension = directory / "URL+Extension.swift"
        extension.write_bytes(plan[self.root / reliability.URL_EXTENSION])
        loader = plan[self.root / reliability.LOADER].decode().replace("\r\n", "\n")
        store = loader[loader.index("final class CustomizeStateStore {"):loader.index("class SPTDataLoaderServiceHook:")]
        block = loader[loader.index("    func shouldBlock("):loader.index("    // orion:new\n    func shouldModify(")]
        test = directory / "ReliabilityTests.swift"
        test.write_text("import Foundation\n#if canImport(FoundationNetworking)\nimport FoundationNetworking\n#endif\n" + store + block + SWIFT_TESTS, encoding="utf-8")
        executable = directory / ("reliability-tests.exe" if sys.platform == "win32" else "reliability-tests")
        subprocess.run([swiftc, "-swift-version", "5", "-parse-as-library", str(support), str(extension), str(test), "-o", str(executable)], check=True, timeout=120)
        subprocess.run([str(executable)], check=True, timeout=30)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: test_reliability.py /path/to/original/EeveeSpotifyNext")
    FIXTURES = Path(sys.argv.pop(1)).resolve()
    unittest.main()
