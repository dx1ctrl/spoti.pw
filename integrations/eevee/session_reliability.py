"""Preserve the server-issued OAuth token expiry in the pinned Eevee source.

SPDX-License-Identifier: GPL-3.0-only
Derived from EeveeSpotifyNext; see bundled license and source attribution.
"""
from pathlib import Path
import hashlib

SOURCE = Path("Sources/EeveeSpotify/SessionProtection.x.swift")
EXPECTED_SHA256 = "f3097b80b589a36d7baa0c91a9c23f6d7d57d6b9e52da9b8a03ba1fc235df240"
START = "// MARK: - OauthAccessTokenBridge — Extend token expiry"
END = "// NOTE: ColdStartupTimeKeeperImplementation is a pure Swift class (not NSObject)."


def plan_patches(root):
    raw = (root / SOURCE).read_bytes()
    text = raw.decode("utf-8").replace("\r\n", "\n")
    if "\r" in text or hashlib.sha256(text.encode()).hexdigest() != EXPECTED_SHA256:
        raise ValueError("Unreviewed OAuth session source")
    if b"\r\n" in raw and b"\n" in raw.replace(b"\r\n", b""):
        raise ValueError("Mixed line endings in OAuth session source")
    if text.count(START) != 1 or text.count(END) != 1:
        raise ValueError("OAuth expiry hook boundaries changed")
    first, last = text.index(START), text.index(END)
    if first >= last:
        raise ValueError("OAuth expiry hook boundaries are out of order")
    text = text[:first] + (
        "// Spotify owns OAuth token expiry. Extending the date only in this process\n"
        "// cannot extend server validity and prevents normal expiry-based refresh.\n"
        "// Do not hook the token getter/setter or start a background expiry extender.\n\n"
    ) + text[last:]
    if b"\r\n" in raw:
        text = text.replace("\n", "\r\n")
    return [(root / SOURCE, text.encode())]
