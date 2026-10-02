// SPDX-License-Identifier: GPL-3.0-or-later
// Standalone, offline Foundation tests. Compile with SpotiToolsModels.swift.
import Foundation

@main
struct SpotiToolsTests {
    static var checks = 0

    static func check(_ condition: @autoclosure () -> Bool, _ message: String) {
        checks += 1
        precondition(condition(), message)
    }

    static func rejects(_ message: String, _ operation: () throws -> Void) {
        checks += 1
        do { try operation(); preconditionFailure(message) } catch {}
    }

    static func main() throws {
        let identifier = "0123456789ABCDEFGHIJKL"
        let canonical = "https://open.spotify.com/track/\(identifier)"
        check(SpotiToolsLinks.spotifyURL(from: "spotify:track:\(identifier)")?.absoluteString == canonical, "Spotify URI should become a clean URL")
        check(SpotiToolsLinks.spotifyURL(from: canonical + "?si=tracking&context=secret#fragment")?.absoluteString == canonical, "Drop query and fragment")
        check(SpotiToolsLinks.spotifyURL(from: "https://open.spotify.com/intl-de/track/\(identifier)?si=123")?.absoluteString == canonical, "Support localized public links")
        check(SpotiToolsLinks.spotifyURL(from: "spotify:episode:\(identifier)")?.path == "/episode/\(identifier)", "Support episodes")
        for bad in [
            "https://open.spotify.com.evil.test/track/\(identifier)",
            "https://open.spotify.com@evil.test/track/\(identifier)",
            "https://user:pass@open.spotify.com/track/\(identifier)",
            "https://open.spotify.com:8443/track/\(identifier)",
            "http://open.spotify.com/track/\(identifier)",
            "file:///track/\(identifier)", "javascript:alert(1)",
            "spotify:album:\(identifier)", "spotify:track:short",
            "spotify:track:\(identifier)?si=abc", "spotify:track:\(identifier):extra",
            "https://open.spotify.com/track/\(identifier)/extra",
            "https://open.spotify.com/track/0123456789ABCDEFGHIJK%2F",
            "https://open.spotify.com//track/\(identifier)",
            "https://open.spotify.com/intl-/track/\(identifier)"
        ] { check(SpotiToolsLinks.spotifyURL(from: bad) == nil, "Reject unsafe or malformed input: \(bad)") }

        let search = SpotiToolsLinks.searchURL(title: "A&B #1 / ?", artist: "Björk + X", service: .youtube)!
        let searchComponents = URLComponents(url: search, resolvingAgainstBaseURL: false)!
        check(searchComponents.host == "www.youtube.com", "Search stays on intended host")
        check(searchComponents.queryItems == [URLQueryItem(name: "search_query", value: "A&B #1 / ? Björk + X")], "Special characters cannot inject query parameters")
        check(searchComponents.fragment == nil, "Search does not inject fragment")
        let apple = SpotiToolsLinks.searchURL(title: "Song", artist: "Artist", service: .appleMusic)!
        check(apple.host == "music.apple.com" && apple.path == "/search", "Apple Music destination")
        check(SpotiToolsLinks.searchURL(title: " ", artist: "", service: .appleMusic) == nil, "No empty search")

        let track = SpotiToolsTrack(title: "  Test song  ", artist: "Artist", album: "Album", position: 3661.8, spotifyLink: "spotify:track:\(identifier)")!
        check(track.title == "Test song" && track.details == "Test song — Artist", "Clean metadata")
        check(track.reportedPosition == "1:01:01", "Display hours without rounding to a future second")
        check(SpotiToolsTrack(title: "Song", position: 65.9)!.reportedPosition == "1:05", "Display minutes")
        check(SpotiToolsTrack(title: "Song", position: 0)!.reportedPosition == "0:00", "Zero is valid")
        check(SpotiToolsTrack(title: "\n ") == nil, "Require title")
        for position in [-1.0, .nan, .infinity] {
            check(SpotiToolsTrack(title: "Song", position: position)!.position == nil, "Invalid position is unavailable")
        }
        check(SpotiToolsTrack(title: "Song", spotifyLink: "https://evil.test")!.spotifyLink == nil, "Do not retain arbitrary link")

        let bookmark = SpotiToolsBookmark(track: track, savedAt: Date(timeIntervalSince1970: 1000))
        let encoded = try SpotiToolsBookmarkCodec.encode([bookmark])
        let decoded = try SpotiToolsBookmarkCodec.decode(encoded)
        check(decoded == [bookmark], "Round-trip bookmarks and identifiers")
        let empty = try SpotiToolsBookmarkCodec.decode(SpotiToolsBookmarkCodec.encode([]))
        check(empty.isEmpty, "Round-trip empty list")
        let older = SpotiToolsBookmark(track: track, savedAt: Date(timeIntervalSince1970: 900))
        let added = try SpotiToolsBookmarkCodec.adding(bookmark, to: [older])
        check(added.map(\.id) == [bookmark.id, older.id], "Newest manual bookmark comes first")
        let full = (0..<100).map { _ in SpotiToolsBookmark(track: track) }
        rejects("Never silently evict saved bookmarks at limit") { _ = try SpotiToolsBookmarkCodec.adding(bookmark, to: full) }
        rejects("Reject over-limit serialized list") { _ = try SpotiToolsBookmarkCodec.encode(full + [bookmark]) }
        rejects("Reject duplicate row identifiers") { _ = try SpotiToolsBookmarkCodec.encode([bookmark, bookmark]) }
        rejects("Reject corrupt JSON") { _ = try SpotiToolsBookmarkCodec.decode(Data("not JSON".utf8)) }
        let json = try JSONSerialization.jsonObject(with: encoded) as! [String: Any]
        var wrongVersion = json
        wrongVersion["version"] = 2
        rejects("Reject future storage version") { _ = try SpotiToolsBookmarkCodec.decode(JSONSerialization.data(withJSONObject: wrongVersion)) }
        var rows = json["bookmarks"] as! [[String: Any]]
        var invalidTrack = rows[0]["track"] as! [String: Any]
        invalidTrack["spotifyLink"] = "https://evil.test"
        rows[0]["track"] = invalidTrack
        rejects("Revalidate links on decoding") { _ = try SpotiToolsBookmarkCodec.decode(JSONSerialization.data(withJSONObject: ["version": 1, "bookmarks": rows])) }
        invalidTrack["spotifyLink"] = canonical
        invalidTrack["position"] = -3
        rows[0]["track"] = invalidTrack
        rejects("Revalidate time on decoding") { _ = try SpotiToolsBookmarkCodec.decode(JSONSerialization.data(withJSONObject: ["version": 1, "bookmarks": rows])) }

        let suiteName = "SpotiToolsTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let store = SpotiToolsBookmarkStore(defaults: defaults)
        let initialStored = try store.load()
        check(initialStored.isEmpty, "New store is empty")
        try store.save([bookmark])
        let stored = try store.load()
        check(stored == [bookmark], "Store writes only requested bookmarks")
        let savedValue = defaults.object(forKey: SpotiToolsBookmarkStore.key)!
        check(savedValue is String, "Storage is eligible for mod settings JSON export")
        let exported = try JSONSerialization.data(withJSONObject: [SpotiToolsBookmarkStore.key: savedValue])
        let imported = try JSONSerialization.jsonObject(with: exported) as! [String: Any]
        store.clear()
        defaults.set(imported[SpotiToolsBookmarkStore.key], forKey: SpotiToolsBookmarkStore.key)
        let restored = try store.load()
        check(restored == [bookmark], "Settings export and restore preserve bookmarks")
        defaults.set(encoded, forKey: SpotiToolsBookmarkStore.key)
        let legacy = try store.load()
        check(legacy == [bookmark], "Read legacy Data storage")
        defaults.set(42, forKey: SpotiToolsBookmarkStore.key)
        rejects("Wrong-type stored data is not silently overwritten") { _ = try store.load() }
        check(defaults.integer(forKey: SpotiToolsBookmarkStore.key) == 42, "Read error preserves original data")
        store.clear()
        check(defaults.object(forKey: SpotiToolsBookmarkStore.key) == nil, "Explicit clear removes storage")
        print("Song tools: \(checks) checks passed")
    }
}
