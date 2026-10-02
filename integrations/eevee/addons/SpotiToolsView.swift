// SPDX-License-Identifier: GPL-3.0-or-later
// Original Song tools companion code for the optional Eevee integration.
import SwiftUI
import UIKit
import MediaPlayer

private struct SpotiToolsSnapshot {
    let track: SpotiToolsTrack
    let artwork: UIImage?

    static func read() -> SpotiToolsSnapshot? {
        guard let info = MPNowPlayingInfoCenter.default().nowPlayingInfo,
              let title = info[MPMediaItemPropertyTitle] as? String else { return nil }
        let identifier = info[MPNowPlayingInfoPropertyExternalContentIdentifier]
        let link = (identifier as? String) ?? (identifier as? URL)?.absoluteString
        guard let track = SpotiToolsTrack(
            title: title,
            artist: info[MPMediaItemPropertyArtist] as? String ?? "",
            album: info[MPMediaItemPropertyAlbumTitle] as? String ?? "",
            position: (info[MPNowPlayingInfoPropertyElapsedPlaybackTime] as? NSNumber)?.doubleValue,
            spotifyLink: link
        ) else { return nil }
        let artwork = (info[MPMediaItemPropertyArtwork] as? MPMediaItemArtwork)?
            .image(at: CGSize(width: 1024, height: 1024))
        return SpotiToolsSnapshot(track: track, artwork: artwork)
    }
}

private struct SpotiToolsShareItem: Identifiable {
    let id = UUID()
    let items: [Any]
}

private struct SpotiToolsShareSheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        let controller = UIActivityViewController(activityItems: items, applicationActivities: nil)
        // The base app may not declare photo-library permission. Files, AirDrop,
        // and other sharing destinations do not require adding that permission.
        let info = Bundle.main.infoDictionary ?? [:]
        if info["NSPhotoLibraryAddUsageDescription"] == nil && info["NSPhotoLibraryUsageDescription"] == nil {
            controller.excludedActivityTypes = [.saveToCameraRoll]
        }
        return controller
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}

struct SpotiToolsView: View {
    @State private var snapshot: SpotiToolsSnapshot?
    @State private var bookmarks: [SpotiToolsBookmark] = []
    @State private var storageError: String?
    @State private var status: String?
    @State private var shareItem: SpotiToolsShareItem?
    @State private var confirmClear = false
    private let store = SpotiToolsBookmarkStore()

    var body: some View {
        List {
            Section(header: Text("Song snapshot"), footer: Text("Refresh reads Spotify’s last published song details. Reported position may lag playback; saved bookmarks are notes and do not resume playback.")) {
                if let snapshot = snapshot {
                    HStack(alignment: .top, spacing: 12) {
                        if let artwork = snapshot.artwork {
                            Image(uiImage: artwork).resizable().scaledToFit()
                                .frame(width: 64, height: 64).cornerRadius(8).accessibilityHidden(true)
                        }
                        VStack(alignment: .leading, spacing: 4) {
                            Text(snapshot.track.title).font(.headline)
                            if !snapshot.track.artist.isEmpty { Text(snapshot.track.artist).foregroundColor(.secondary) }
                            if !snapshot.track.album.isEmpty { Text(snapshot.track.album).font(.caption).foregroundColor(.secondary) }
                            Text("Reported position: \(snapshot.track.reportedPosition)")
                                .font(.caption).foregroundColor(.secondary)
                        }
                    }
                } else {
                    Text("No song details are available. Play a song in Spotify, then refresh.")
                        .foregroundColor(.secondary)
                }
                Button(action: refresh) { Label("Refresh song details", systemImage: "arrow.clockwise") }
                if let status = status { Text(status).font(.footnote).foregroundColor(.secondary) }
            }

            if let snapshot = snapshot {
                toolsSection(snapshot)
            }

            Section(header: Text("Bookmarks (\(bookmarks.count)/100)"), footer: Text("Saved only when you tap Save bookmark. Included in mod settings exports; importing settings replaces this list. Removing the app or resetting mod settings removes bookmarks.")) {
                if let storageError = storageError {
                    Text(storageError).foregroundColor(.red)
                } else if bookmarks.isEmpty {
                    Text("No saved bookmarks.").foregroundColor(.secondary)
                }
                ForEach(bookmarks) { bookmark in
                    VStack(alignment: .leading, spacing: 6) {
                        Text(bookmark.track.title).font(.headline)
                        if !bookmark.track.artist.isEmpty { Text(bookmark.track.artist).foregroundColor(.secondary) }
                        Text("Reported position: \(bookmark.track.reportedPosition)")
                            .font(.caption).foregroundColor(.secondary)
                        Text(bookmark.savedAt, style: .date).font(.caption).foregroundColor(.secondary)
                        HStack {
                            Button("Copy note") { copy(bookmarkNote(bookmark), message: "Bookmark copied.") }
                            Spacer()
                            Button("Remove") { removeBookmark(bookmark.id) }.foregroundColor(.red)
                                .accessibilityLabel("Remove bookmark for \(bookmark.track.title)")
                        }
                        .buttonStyle(BorderlessButtonStyle())
                    }
                    .padding(.vertical, 4)
                }
                if !bookmarks.isEmpty || storageError != nil {
                    Button("Clear all bookmarks") { confirmClear = true }.foregroundColor(.red)
                }
            }
        }
        .eeveeSettingsListStyle()
        .preferredColorScheme(.dark)
        .onAppear { refresh(); loadBookmarks() }
        .sheet(item: $shareItem) { SpotiToolsShareSheet(items: $0.items) }
        .alert(isPresented: $confirmClear) {
            Alert(title: Text("Clear all bookmarks?"), message: Text("This removes every saved Song tools bookmark from this app."),
                  primaryButton: .destructive(Text("Clear all")) {
                    store.clear(); bookmarks = []; storageError = nil; status = "Bookmarks cleared."
                  }, secondaryButton: .cancel())
        }
    }

    private func toolsSection(_ snapshot: SpotiToolsSnapshot) -> some View {
        Section(header: Text("Tools")) {
            Button { copy(snapshot.track.details, message: "Song details copied.") } label: {
                Label("Copy title and artist", systemImage: "doc.on.doc")
            }
            if let value = snapshot.track.spotifyLink, let url = URL(string: value) {
                Button { copy(value, message: "Clean Spotify link copied.") } label: {
                    Label("Copy clean Spotify link", systemImage: "link")
                }
                Button { shareItem = SpotiToolsShareItem(items: [url]) } label: {
                    Label("Share Spotify link", systemImage: "square.and.arrow.up")
                }
            }
            if let artwork = snapshot.artwork {
                Button { shareItem = SpotiToolsShareItem(items: [artwork]) } label: {
                    Label("Share artwork", systemImage: "photo")
                }
            }
            Button(action: saveBookmark) { Label("Save bookmark", systemImage: "bookmark") }
                .disabled(storageError != nil || bookmarks.count >= SpotiToolsBookmarkCodec.limit)
            if bookmarks.count >= SpotiToolsBookmarkCodec.limit {
                Text("Remove a bookmark to save another.").font(.footnote).foregroundColor(.secondary)
            }
            if let url = SpotiToolsLinks.searchURL(title: snapshot.track.title, artist: snapshot.track.artist, service: .appleMusic) {
                Link(destination: url) { Label("Search Apple Music", systemImage: "magnifyingglass") }
            }
            if let url = SpotiToolsLinks.searchURL(title: snapshot.track.title, artist: snapshot.track.artist, service: .youtube) {
                Link(destination: url) { Label("Search YouTube", systemImage: "magnifyingglass") }
            }
        }
    }

    private func refresh() {
        snapshot = SpotiToolsSnapshot.read()
        status = nil
    }

    private func copy(_ text: String, message: String) {
        UIPasteboard.general.string = text
        status = message
    }

    private func loadBookmarks() {
        do { bookmarks = try store.load(); storageError = nil }
        catch { storageError = error.localizedDescription }
    }

    private func saveBookmark() {
        // Capture again on the user's tap; don't save an earlier page snapshot.
        snapshot = SpotiToolsSnapshot.read()
        guard let snapshot = snapshot else { status = "No song details are available to save."; return }
        do {
            let updated = try SpotiToolsBookmarkCodec.adding(SpotiToolsBookmark(track: snapshot.track), to: bookmarks)
            try store.save(updated)
            bookmarks = updated
            status = "Saved bookmark for \(snapshot.track.title)."
        } catch { status = error.localizedDescription }
    }

    private func removeBookmark(_ id: UUID) {
        do {
            let updated = bookmarks.filter { $0.id != id }
            try store.save(updated)
            bookmarks = updated
            status = "Bookmark removed."
        } catch { status = error.localizedDescription }
    }

    private func bookmarkNote(_ bookmark: SpotiToolsBookmark) -> String {
        var lines = [bookmark.track.details]
        if bookmark.track.position != nil { lines.append("Reported position: \(bookmark.track.reportedPosition)") }
        if let link = bookmark.track.spotifyLink { lines.append(link) }
        return lines.joined(separator: "\n")
    }
}
