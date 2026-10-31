# EeveeSpotifyReincarnated integration

This workflow now builds [SideloadLabs/EeveeSpotifyReincarnated](https://github.com/SideloadLabs/EeveeSpotifyReincarnated) at pinned commit `ca363e63efd4730811a241ec48a5c0e4ef838112`. The build keeps the verified Spotify 9.1.78 base IPA and adds the pinned upstream tweak, its renamed `EeveeSwiftProtobuf` framework, bundled resources, and the upstream sideload compatibility library. The source repository documents Spotify 9.1.88 as its latest target and includes a 9.1.76 configuration, but playback on 9.1.78 still needs device verification.

The integration adds Song tools and Visual styles to Reincarnated's settings page. Eevee's lyrics replacement is forced off so it does not compete with spoti.pw lyrics. Visual hooks remain inactive at launch; open Visual styles and apply a style for the current session. The existing app extensions and App Intents metadata are checked after injection.

The combined artifact is `spoti.pw-0.22.0-reincarnated.ipa`. It includes the Reincarnated GPL-3.0 license, `.deb`, pinned source archive, checksum, and build information. Sign it over the existing Spotify app with the same Apple Account and bundle identifier used previously.

The build uses the 9.1.78 IPA at SHA-256 `07d51db51a5468c8b42308078c929ceaf4eb21fea8fde930fc599a15cccecc57`, originally produced by run `36457343317`. It does not silently switch the Spotify app version. Reincarnated is a separate upstream implementation from the previous EeveeSpotifyNext pin, so the previous integration's source patches are not applied to it.

After installing, confirm cold launch, local playback through multiple full tracks, track selection, and a longer session. Test Connect separately; Spotify streams the audio on the remote device. Keep the previous IPA available until playback and launch are verified on the phone.
