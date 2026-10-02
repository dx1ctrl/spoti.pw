// SPDX-License-Identifier: GPL-3.0-only
// Reliability helpers for the pinned EeveeSpotifyNext integration.
import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

enum NetworkReliability {
    // These service names occur in Spotify 9.1.78's advertising namespace.
    // "ad" is also present in Metadata, Download, ReadReporting and TrafficAdapter.
    private static let adServices: Set<String> = [
        "ads", "events", "formats", "instream", "slots", "state", "targeting",
        "settings", "preview", "testing", "podcasttesting"
    ]

    static func isEsperantoAd(_ url: URL) -> Bool {
        let components = url.path.lowercased().split(separator: "/")
        guard let index = components.firstIndex(of: "esperanto"),
              index + 1 < components.count else { return false }
        let service = String(components[index + 1])
        let prefix = "spotify.ads.esperanto.proto."
        guard service.hasPrefix(prefix) else { return false }
        return adServices.contains(String(service.dropFirst(prefix.count)))
    }
}

// A URL is not a request identity: parallel tasks can request the same endpoint.
// Each hook owns a separate instance, so one hook cannot drain another's data.
final class TaskResponseBuffer {
    private let lock = NSLock()
    private var dataByTask: [ObjectIdentifier: Data] = [:]

    func append(_ data: Data, for task: URLSessionTask) {
        lock.lock(); defer { lock.unlock() }
        dataByTask[ObjectIdentifier(task), default: Data()].append(data)
    }

    func take(for task: URLSessionTask) -> Data? {
        lock.lock(); defer { lock.unlock() }
        return dataByTask.removeValue(forKey: ObjectIdentifier(task))
    }
}
