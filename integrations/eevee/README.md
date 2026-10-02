# Optional Eevee package with reliability fixes, Song tools and visual styles

This separate workflow adds a source-built EeveeSpotifyNext library to an existing
spoti.pw 0.22.0 artifact. It does not modify spoti.pw's implementation. The source
is pinned to `8a9e4c3c1ca9a8991023d8b16be159aa73420017` from
<https://github.com/w3ltyyy/EeveeSpotifyNext> and carries its GPL-3.0 license.

Eevee's own lyrics handling is disabled to avoid competing with spoti.pw. The
Eevee settings page points to the actual lyric controls in Mod Settings. The
workflow preserves the existing app extensions and App Intents metadata and
checks that they remain present. The output includes the patched Eevee source,
license, package and SHA-256 checksum.

## Visuals 1

**EeveeSpotify → Visual styles** adds three optional treatments to the expanded
Redesigned UI player: Artwork aura, Purple neon, and Minimal glass. Styles have
an intensity control and motion switch, and can be turned off independently.
They require iOS 26 or later and Mod Settings → Appearance → Redesigned UI.
After enabling Redesigned UI, restart the app once; changing the new style
controls then applies when returning to the player.

The original companion uses its own decorative layers on the mod's existing
player background. It does not change playback, artwork, controls, app accents,
the mini-player or the native Spotify layout. Hook activation checks the target
class and selectors before installing. Motion respects Reduce Motion, Low Power
Mode, backgrounding and the player's existing pause/transition state.
The styles start off to preserve the current appearance until one is selected.

## Included reliability fixes (2026.10.01)

The package addresses demonstrated client-side bugs in the pinned Eevee code:

- Match known Esperanto advertising services rather than any URL containing
  `ad` or `slot`; legitimate metadata and download RPC names contain these strings.
- Let v9.1 product-state/session/license refresh requests pass the data-loader
  hook. Disable its blocking when Premium patching is off.
- Buffer responses by task identity, separately for the loader and bootstrap
  hooks. Task IDs are only unique inside a single URLSession; URLs are not unique
  request identities either.
- Drain state on terminal callbacks, preserve original response bytes on decode
  errors/cancellation, and finish empty responses instead of leaving callers waiting.
- Remove the local one-year OAuth expiry override and its repeating background
  extender. Spotify keeps the real token expiry and its expiry-based refresh logic.

These are plausible contributors to interrupted playback, not proof of the
reported skip's cause. The upstream logout, Ably and DeleteToken protections and
plan/capping interceptor otherwise remain unchanged. The existing customize-304
callback timing and session behavior still need device observation.

**EeveeSpotify → Song tools** adds manually saved song/time bookmarks, title/artist
copying, artwork sharing, and Apple Music/YouTube search. Clean Spotify links are
offered only when the public now-playing metadata supplies a validated identifier.
It adds no playback hooks, automatic listening history, background network calls,
extensions or entitlements. Bookmarks record the last reported position; they do
not seek or resume a song. See [Song tools details](addons/README.md).

Run **Build spoti.pw with Eevee**, providing the successful original build's run
ID. That run must still contain an accessible `spoti.ipa` artifact. This workflow
pins the SHA-256 of the verified Spotify 9.1.78 / spoti.pw 0.22.0 input from run
`36457343317`; another input requires a new compatibility review. Install the combined IPA using the same Sideloadly
account and bundle-ID settings as before, without deleting the original app.

The workflow tests source preparation, network policy, concurrent buffers and
bookmark helpers, compiles the complete iOS library, then validates the packaged
IPA and retained extensions. Its output is `spoti.pw-0.22.0-visuals.ipa`.

Upstream reports 9.1.x support and tested 9.1.58. A successful build does not prove
playback works on 9.1.78: verify selection of individual tracks, repeated skips,
ad behavior and app stability on the device. This does not upgrade a Spotify
account or enable server-controlled downloads, Very High quality, or Premium
features on Spotify Connect devices. Eevee also changes session/logout handling;
its behavior comes from the pinned upstream source except for the changes above.

## Phone verification

Install over the existing app with the same Apple Account and bundle-ID settings.
Use High or Automatic streaming quality; Very High/Lossless are server-controlled.
First test local playback through the phone/Bluetooth, with artist blocking off:
play several full tracks, change tracks, lock/unlock, background/return, and test
again after a longer listening session. Test Spotify Connect separately because
the remote device streams the audio itself. Confirm Song tools opens, can save a
bookmark, shares available artwork, and handles missing metadata gracefully.
No automatic or repeat-until-success skipping logic is added.

For the visual styles, enable Redesigned UI and restart, then select each style
in turn and open the expanded player. Check the intensity limits, motion toggle,
paused playback, Reduce Motion, Low Power Mode, rotation, background/foreground,
track changes, and opening/closing the player. Confirm taps, scrolling and lyrics
still work, and Off restores the previous background. Compilation and package
checks cannot substitute for this on-device appearance test.

To return to the previous behavior, reinstall the original spoti.pw IPA with the
same signing settings. No combined IPA is published as a public release here.
