// SPDX-License-Identifier: GPL-3.0-or-later
// Original Song tools companion code for the optional Eevee integration.
// No spoti.pw implementation is copied into this addon.
import Foundation

enum SpotiToolsLinks {
    // Accept only public track/episode identifiers. Never retain tracking queries,
    // credentials, arbitrary hosts, local files, or another app's URL scheme.
    static func spotifyURL(from input: String) -> URL? {
        let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
        var parts: [String]
        if text.hasPrefix("spotify:") {
            parts = text.components(separatedBy: ":")
            guard parts.count == 3, parts.removeFirst() == "spotify" else { return nil }
        } else {
            guard let components = URLComponents(string: text),
                  components.scheme?.lowercased() == "https",
                  components.host?.lowercased() == "open.spotify.com",
                  components.user == nil, components.password == nil,
                  components.port == nil else { return nil }
            parts = components.path.components(separatedBy: "/")
            guard parts.first == "" else { return nil }
            parts.removeFirst()
            if parts.count == 3, parts[0].hasPrefix("intl-"),
               parts[0].dropFirst(5).allSatisfy({ $0.isASCII && ($0.isLetter || $0 == "-") }),
               parts[0].count > 5 {
                parts.removeFirst()
            }
        }
        guard parts.count == 2, ["track", "episode"].contains(parts[0]),
              parts[1].utf8.count == 22,
              parts[1].utf8.allSatisfy({ (48...57).contains($0) || (65...90).contains($0) || (97...122).contains($0) }) else {
            return nil
        }
        return URL(string: "https://open.spotify.com/\(parts[0])/\(parts[1])")
    }

    static func searchURL(title: String, artist: String, service: SpotiToolsSearchService) -> URL? {
        let query = [title, artist].map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }.joined(separator: " ")
        guard !query.isEmpty else { return nil }
        var components = URLComponents()
        components.scheme = "https"
        components.host = service == .appleMusic ? "music.apple.com" : "www.youtube.com"
        components.path = service == .appleMusic ? "/search" : "/results"
        components.queryItems = [URLQueryItem(name: service == .appleMusic ? "term" : "search_query", value: query)]
        return components.url
    }
}

enum SpotiToolsSearchService { case appleMusic, youtube }

struct SpotiToolsTrack: Codable, Equatable {
    let title: String
    let artist: String
    let album: String
    let position: Double?
    let spotifyLink: String?

    init?(title: String, artist: String = "", album: String = "", position: Double? = nil, spotifyLink: String? = nil) {
        let cleanTitle = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleanTitle.isEmpty else { return nil }
        self.title = String(cleanTitle.prefix(1024))
        self.artist = String(artist.trimmingCharacters(in: .whitespacesAndNewlines).prefix(1024))
        self.album = String(album.trimmingCharacters(in: .whitespacesAndNewlines).prefix(1024))
        self.position = position.flatMap { $0.isFinite && $0 >= 0 ? $0 : nil }
        self.spotifyLink = spotifyLink.flatMap { SpotiToolsLinks.spotifyURL(from: $0)?.absoluteString }
    }

    var details: String { [title, artist].filter { !$0.isEmpty }.joined(separator: " — ") }

    var reportedPosition: String {
        guard let seconds = position, seconds.isFinite, seconds >= 0,
              seconds < Double(Int.max / 2) else { return "Unavailable" }
        let whole = Int(seconds)
        if whole >= 3600 {
            return "\(whole / 3600):" + String(format: "%02d:%02d", (whole / 60) % 60, whole % 60)
        }
        return String(format: "%d:%02d", whole / 60, whole % 60)
    }

    fileprivate var isValid: Bool {
        guard !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              title.count <= 1024, artist.count <= 1024, album.count <= 1024 else { return false }
        if let value = position, !value.isFinite || value < 0 { return false }
        if let value = spotifyLink, SpotiToolsLinks.spotifyURL(from: value)?.absoluteString != value { return false }
        return true
    }
}

struct SpotiToolsBookmark: Codable, Equatable, Identifiable {
    let id: UUID
    let savedAt: Date
    let track: SpotiToolsTrack

    init(track: SpotiToolsTrack, id: UUID = UUID(), savedAt: Date = Date()) {
        self.id = id
        self.savedAt = savedAt
        self.track = track
    }
}

enum SpotiToolsStorageError: LocalizedError {
    case full, invalidData

    var errorDescription: String? {
        switch self {
        case .full: return "You have 100 bookmarks. Remove one before saving another."
        case .invalidData: return "Saved bookmarks could not be read. Clear all bookmarks to reset this list."
        }
    }
}

enum SpotiToolsBookmarkCodec {
    static let limit = 100
    private struct Envelope: Codable {
        let version: Int
        let bookmarks: [SpotiToolsBookmark]
    }

    private static func validate(_ bookmarks: [SpotiToolsBookmark]) throws {
        guard bookmarks.count <= limit,
              Set(bookmarks.map(\.id)).count == bookmarks.count,
              bookmarks.allSatisfy({ $0.track.isValid && $0.savedAt.timeIntervalSince1970.isFinite }) else {
            throw SpotiToolsStorageError.invalidData
        }
    }

    static func encode(_ bookmarks: [SpotiToolsBookmark]) throws -> Data {
        try validate(bookmarks)
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .secondsSince1970
        return try encoder.encode(Envelope(version: 1, bookmarks: bookmarks))
    }

    static func decode(_ data: Data) throws -> [SpotiToolsBookmark] {
        do {
            let decoder = JSONDecoder()
            decoder.dateDecodingStrategy = .secondsSince1970
            let envelope = try decoder.decode(Envelope.self, from: data)
            guard envelope.version == 1 else { throw SpotiToolsStorageError.invalidData }
            try validate(envelope.bookmarks)
            return envelope.bookmarks
        } catch {
            throw SpotiToolsStorageError.invalidData
        }
    }

    static func adding(_ bookmark: SpotiToolsBookmark, to bookmarks: [SpotiToolsBookmark]) throws -> [SpotiToolsBookmark] {
        guard bookmarks.count < limit else { throw SpotiToolsStorageError.full }
        let updated = [bookmark] + bookmarks
        try validate(updated)
        return updated
    }
}

// The store is instantiated only by the visible page. Nothing records history
// automatically. The prefix allows spoti.pw's existing reset to remove this data.
struct SpotiToolsBookmarkStore {
    static let key = "spotifyglass.songTools.bookmarks.v1"
    let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) { self.defaults = defaults }

    func load() throws -> [SpotiToolsBookmark] {
        guard let value = defaults.object(forKey: Self.key) else { return [] }
        let data: Data
        if let json = value as? String {
            data = Data(json.utf8)
        } else if let legacy = value as? Data {
            data = legacy
        } else {
            throw SpotiToolsStorageError.invalidData
        }
        return try SpotiToolsBookmarkCodec.decode(data)
    }

    func save(_ bookmarks: [SpotiToolsBookmark]) throws {
        let data = try SpotiToolsBookmarkCodec.encode(bookmarks)
        guard let json = String(data: data, encoding: .utf8) else { throw SpotiToolsStorageError.invalidData }
        // Mod settings exports accept JSON values, but skip NSData. A JSON string
        // preserves these bookmarks when the user exports and restores settings.
        defaults.set(json, forKey: Self.key)
    }

    func clear() { defaults.removeObject(forKey: Self.key) }
}
