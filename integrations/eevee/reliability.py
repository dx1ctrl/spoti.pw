"""Plan narrowly scoped network fixes for the pinned Eevee source; never write.

SPDX-License-Identifier: GPL-3.0-only
Adaptation of EeveeSpotifyNext, pinned at
8a9e4c3c1ca9a8991023d8b16be159aa73420017, by Eevee/whoeevee, Meeep1/Skye,
and w3ltyyy. See upstream LICENSE and integrations/eevee/README.md.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


LOADER = Path("Sources/EeveeSpotify/DataLoaderServiceHooks.x.swift")
URL_EXTENSION = Path("Sources/EeveeSpotify/Shared/Models/Extensions/URL+Extension.swift")
HELPER = Path("Sources/EeveeSpotify/Shared/Helpers/URLSessionHelper.swift")
BOOTSTRAP = Path("Sources/EeveeSpotify/Premium/DynamicPremium+ModifyBootstrap.x.swift")
SUPPORT = Path("Sources/EeveeSpotify/Shared/Helpers/NetworkReliability.swift")
ORIGINAL_HASHES = {
    LOADER: "cde96f8e90eab8c0e5e8d1e93b3d42174423c800a064960c32c92df3c3df8c4b",
    URL_EXTENSION: "85bec172cc75836feaa65892e137a7fbfa5701cf41d16c9ed09ed8f9c12342df",
    HELPER: "a10862de119dd8f5ddb7d9279ea2a9d5e74e4421276ff01cf2603b3304b74329",
    BOOTSTRAP: "99456aef06eddee391e2b028b9011bc6bb7af6aa1b0c2e1041cf50e8f2e887aa",
}


def once(text: str, before: str, after: str) -> str:
    count = text.count(before)
    if count != 1:
        raise ValueError(f"reliability patch expected one match, found {count}: {before[:90]!r}")
    return text.replace(before, after, 1)


def section(text: str, start: str, end: str, replacement: str) -> str:
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError("reliability section boundaries changed")
    first = text.index(start)
    last = text.index(end, first)
    return text[:first] + replacement + text[last:]


def patch_url(text: str) -> str:
    return once(
        text,
        'if path.contains("/esperanto/") && (path.contains("ad") || path.contains("slot")) {',
        'if NetworkReliability.isEsperantoAd(self) {',
    )


def patch_helper(text: str) -> str:
    text = section(
        text,
        "    static let shared = URLSessionHelper()",
        "    static var DarwinVersion: String {",
        """    static let shared = URLSessionHelper()
    static let bootstrap = URLSessionHelper()
    private let responseBuffer = TaskResponseBuffer()

    private init() {}

""",
    )
    return section(
        text,
        "    func setOrAppend(_ data: Data, for url: URL) {",
        "\n}\n",
        """    func setOrAppend(_ data: Data, for task: URLSessionTask) {
        responseBuffer.append(data, for: task)
    }

    func obtainData(for task: URLSessionTask) -> Data? {
        responseBuffer.take(for: task)
    }""",
    )


def patch_loader(text: str) -> str:
    text = once(text, "private var handledTasks = Set<Int>()", "private var handledTasks = Set<ObjectIdentifier>()")
    text = once(text, "func markHandledCustomizeTask(_ id: Int)", "func markHandledCustomizeTask(_ task: URLSessionTask)")
    text = once(text, "handledTasks.insert(id)", "handledTasks.insert(ObjectIdentifier(task))")
    text = once(text, "func consumeHandledCustomizeTask(_ id: Int)", "func consumeHandledCustomizeTask(_ task: URLSessionTask)")
    text = once(text, "handledTasks.remove(id)", "handledTasks.remove(ObjectIdentifier(task))")
    text = section(
        text,
        "        let elapsed = Date().timeIntervalSince(tweakInitTime)",
        "        // Only block these after startup (30s) to allow initial login/initialization",
        """        guard BasePremiumPatchingGroup.isActive else { return false }
        if url.isAdRelated { return true }

        // v9.1 needs Spotify's normal session, product-state and license refreshes.
        if EeveeSpotify.hookTarget == .v91 { return false }

        let elapsed = Date().timeIntervalSince(tweakInitTime)
        let path = url.path.lowercased()
        if url.isDeleteToken || url.isSessionInvalidation || path.contains("session/purge") || path.contains("token/revoke") {
            return true
        }

""",
    )
    old_guard = """        guard let url = task.currentRequest?.url else {
            orig.URLSession(session, task: task, didCompleteWithError: error)
            return
        }"""
    text = once(text, old_guard, """        // Always drain this hook's state, including cancellation and missing URLs.
        let bufferedData = URLSessionHelper.shared.obtainData(for: task)
        let handledCustomize = CustomizeStateStore.shared.consumeHandledCustomizeTask(task)
        guard let url = task.currentRequest?.url ?? task.originalRequest?.url else {
            if let data = bufferedData { respondWithCustomData(data, task: task, session: session) }
            orig.URLSession(session, task: task, didCompleteWithError: error)
            return
        }""")
    text = once(text, """        if CustomizeStateStore.shared.consumeHandledCustomizeTask(task.taskIdentifier) {
            orig.URLSession(session, task: task, didCompleteWithError: nil)""", """        if handledCustomize {
            orig.URLSession(session, task: task, didCompleteWithError: error)""")
    text = once(text, """        guard error == nil, shouldModify(url) else {
            orig.URLSession(session, task: task, didCompleteWithError: error)
            return
        }""", """        guard error == nil, shouldModify(url) else {
            if let data = bufferedData { respondWithCustomData(data, task: task, session: session) }
            orig.URLSession(session, task: task, didCompleteWithError: error)
            return
        }""")
    text = once(text, """        guard let buffer = URLSessionHelper.shared.obtainData(for: url) else {
            // Customize 304 fallback: serve cached modified data when no buffer available
            if url.isCustomize, let cached = CustomizeStateStore.shared.cachedCustomizeData {
                respondWithCustomData(cached, task: task, session: session)
                orig.URLSession(session, task: task, didCompleteWithError: nil)
            }
            return
        }""", """        guard let buffer = bufferedData else {
            // An empty response must still complete; only replay a cache for a real 304.
            if url.isCustomize, (task.response as? HTTPURLResponse)?.statusCode == 304,
               let cached = CustomizeStateStore.shared.cachedCustomizeData {
                respondWithCustomData(cached, task: task, session: session)
            }
            orig.URLSession(session, task: task, didCompleteWithError: nil)
            return
        }""")
    text = once(text, """        catch {
            orig.URLSession(session, task: task, didCompleteWithError: error)
        }
    }

    func URLSession(""", """        catch {
            // A local decoder failure must not turn a valid Spotify response into an error.
        }
        respondWithCustomData(buffer, task: task, session: session)
        orig.URLSession(session, task: task, didCompleteWithError: nil)
    }

    func URLSession(""")
    text = once(text, "if let url = task.currentRequest?.url, url.isCustomize, response.statusCode == 304 {", "if BasePremiumPatchingGroup.isActive, let url = task.currentRequest?.url, url.isCustomize, response.statusCode == 304 {")
    text = once(text, """                orig.URLSession(session, dataTask: task, didReceiveResponse: fakeResponse, completionHandler: handler)
                respondWithCustomData(cached, task: task, session: session)
                CustomizeStateStore.shared.markHandledCustomizeTask(task.taskIdentifier)""", """                CustomizeStateStore.shared.markHandledCustomizeTask(task)
                orig.URLSession(session, dataTask: task, didReceiveResponse: fakeResponse, completionHandler: handler)
                respondWithCustomData(cached, task: task, session: session)""")
    # Preserve the exact coexistence guard expected by the main preparation module.
    text = once(text, """        guard
            let url = task.currentRequest?.url,
            url.isLyrics,
            response.statusCode != 200""", """        guard
            BaseLyricsGroup.isActive,
            let url = task.currentRequest?.url,
            url.isLyrics,
            response.statusCode != 200""")
    text = once(text, """        } catch {
            orig.URLSession(session, task: task, didCompleteWithError: error)
        }
    }

    func URLSession(""", """        } catch {
            // Forward the response/disposition callback; the task owns its completion.
            orig.URLSession(session, dataTask: task, didReceiveResponse: response, completionHandler: handler)
        }
    }

    func URLSession(""")
    text = once(text, """        guard let url = task.currentRequest?.url else {
            return
        }""", """        guard let url = task.currentRequest?.url ?? task.originalRequest?.url else {
            orig.URLSession(session, dataTask: task, didReceiveData: data)
            return
        }""")
    return once(text, "URLSessionHelper.shared.setOrAppend(data, for: url)", "URLSessionHelper.shared.setOrAppend(data, for: task)")


def patch_bootstrap(text: str) -> str:
    text = once(text, """        guard 
            let request = task.currentRequest,
            let url = request.url
        else {
            return
        }""", """        guard let url = task.currentRequest?.url ?? task.originalRequest?.url else {
            orig.URLSession(session, dataTask: task, didReceiveData: data)
            return
        }""")
    text = once(text, "URLSessionHelper.shared.setOrAppend(data, for: url)", "URLSessionHelper.bootstrap.setOrAppend(data, for: task)")
    text = once(text, """        guard
            let request = task.currentRequest,
            let url = request.url
        else {
            return
        }""", """        let bufferedData = URLSessionHelper.bootstrap.obtainData(for: task)
        guard let url = task.currentRequest?.url ?? task.originalRequest?.url else {
            if let data = bufferedData { orig.URLSession(session, dataTask: task, didReceiveData: data) }
            orig.URLSession(session, task: task, didCompleteWithError: error)
            return
        }""")
    text = once(text, "guard let buffer = URLSessionHelper.shared.obtainData(for: url) else {", "guard let buffer = bufferedData else {")
    text = once(text, """        orig.URLSession(session, task: task, didCompleteWithError: error)
    }
}""", """        // Includes parse errors and cancellations: preserve the original response body.
        if let data = bufferedData { orig.URLSession(session, dataTask: task, didReceiveData: data) }
        orig.URLSession(session, task: task, didCompleteWithError: error)
    }
}""")
    return text


TRANSFORMS = {LOADER: patch_loader, URL_EXTENSION: patch_url, HELPER: patch_helper, BOOTSTRAP: patch_bootstrap}


def plan_patches(root: Path) -> list[tuple[Path, bytes]]:
    """Validate original pinned files, preserve line endings and return all outputs.

    No mutation occurs here. The caller must combine all integration plans before
    writing. Already patched, mixed-line-ending and changed upstream inputs fail.
    """
    planned = []
    for relative, expected in ORIGINAL_HASHES.items():
        path = root / relative
        raw = path.read_bytes()
        text = raw.decode("utf-8").replace("\r\n", "\n")
        if "\r" in text or (b"\r\n" in raw and b"\n" in raw.replace(b"\r\n", b"")):
            raise ValueError(f"unexpected line endings: {relative}")
        actual = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if actual != expected:
            raise ValueError(f"upstream SHA-256 mismatch in {relative}: {actual}")
        replacement = TRANSFORMS[relative](text)
        if b"\r\n" in raw:
            replacement = replacement.replace("\n", "\r\n")
        planned.append((path, replacement.encode("utf-8")))
    destination = root / SUPPORT
    if destination.exists():
        raise ValueError(f"reliability support file already exists: {SUPPORT}")
    planned.append((destination, Path(__file__).with_name("NetworkReliability.swift").read_bytes()))
    return planned
