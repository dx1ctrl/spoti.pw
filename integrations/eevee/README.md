# Optional Eevee package

This separate workflow adds a source-built EeveeSpotifyNext library to an existing
spoti.pw 0.22.0 artifact. It does not modify spoti.pw's implementation. The source
is pinned to `8a9e4c3c1ca9a8991023d8b16be159aa73420017` from
<https://github.com/w3ltyyy/EeveeSpotifyNext> and carries its GPL-3.0 license.

Eevee's own lyrics handling is disabled to avoid competing with spoti.pw. The
workflow preserves the existing app extensions and App Intents metadata and
checks that they remain present. The output includes the patched Eevee source,
license, package and SHA-256 checksum.

Run **Build spoti.pw with Eevee**, providing the successful original build's run
ID. That run must still contain an accessible `spoti.ipa` artifact. This workflow
pins the SHA-256 of the verified Spotify 9.1.78 / spoti.pw 0.22.0 input from run
`36457343317`; another input requires a new compatibility review. Install the combined IPA using the same Sideloadly
account and bundle-ID settings as before, without deleting the original app.

Upstream reports 9.1.x support and tested 9.1.58. A successful build does not prove
playback works on 9.1.78: verify selection of individual tracks, repeated skips,
ad behavior and app stability on the device. This does not upgrade a Spotify
account or enable server-controlled downloads, Very High quality, or Premium
features on Spotify Connect devices. Eevee also changes session/logout handling;
its behavior comes from the pinned upstream source.

To return to the previous behavior, reinstall the original spoti.pw IPA with the
same signing settings. No combined IPA is published as a public release here.
