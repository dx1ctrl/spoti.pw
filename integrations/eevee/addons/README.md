# Song tools companion

These original GPL-3.0-or-later Swift sources add `SpotiToolsView()` to the optional
Eevee settings page. Copy only `SpotiToolsModels.swift` and `SpotiToolsView.swift`
into Eevee's source tree, and link MediaPlayer. Do not compile `tests/` into the
app. No spoti.pw implementation is changed or copied.

The page reads the current process's public `MPNowPlayingInfoCenter` dictionary
when opened, refreshed, or when Save bookmark is tapped. It offers:

- Copy title and artist.
- Copy/share a clean Spotify track or episode link **only** when the published
  external content identifier contains a validated Spotify URI or public URL.
- Share available artwork through the system share sheet. Saving to Photos is
  excluded if the existing app declares neither photo-library usage string;
  other available destinations, such as Files or AirDrop, remain system managed.
- Search Apple Music or YouTube with the displayed song and artist, only on tap.
- Manually save up to 100 local bookmarks, copy their notes, remove individual
  bookmarks, or clear the list with confirmation. Nothing is recorded automatically.

Song details may be unavailable. The reported position is the last value Spotify
published and may lag playback. Bookmarks are notes, not resume/seek controls, and
contain no artwork, credentials, or audio. Mod settings exports include bookmarks;
importing settings replaces the list, including clearing it if the imported file
predates bookmarks. The app's normal device backup may also include its
preferences. Removing the app or resetting mod settings deletes these bookmarks.
Corrupt or unknown-format data is preserved until explicitly cleared. Storage is
a JSON string so the mod's existing settings export can round-trip it.

The page installs no hooks, timers, notifications, networking client, playback
commands, extra app extensions, or entitlements. Existing settings page styling
is reused. Device verification is still required for the available metadata,
navigation, iPad/iPhone share sheet, and search handoff.

Run the standalone offline Foundation tests on a host with Swift installed:

```sh
swiftc integrations/eevee/addons/SpotiToolsModels.swift \
  integrations/eevee/addons/tests/SpotiToolsTests.swift -o /tmp/spoti-tools-tests
/tmp/spoti-tools-tests
```

These tests cover strict URL validation, query encoding, position formatting,
bookmark serialization, bounded storage, corrupt-data handling, and explicit
deletion. A successful Foundation test does not verify UIKit or SwiftUI behavior.
