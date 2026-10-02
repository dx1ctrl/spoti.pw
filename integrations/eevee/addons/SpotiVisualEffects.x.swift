// SPDX-License-Identifier: GPL-3.0-or-later
// Hooks only the existing mod's artwork field; no Spotify playback hooks.
import Orion
import UIKit
import ObjectiveC

struct SpotiVisualEffectsHookGroup: HookGroup { }

// Main-queue state only. Nothing in this file runs automatically at launch.
private var spotiVisualEffectsActivated = false

func activateSpotiVisualEffects() {
    // This is called only when the user applies a style in Visual styles.
    // A saved preference never enables hooks in a later process automatically.
    DispatchQueue.main.async {
        guard #available(iOS 26.0, *), UIApplication.shared.applicationState == .active,
              spotiVisualEffectsRequested() else { return }
        if spotiVisualEffectsActivated {
            requestSpotiVisualEffectsRefresh()
            return
        }
        guard let fieldClass = NSClassFromString("SGRArtworkField") else { return }
        let selectors = ["layoutSubviews", "didMoveToWindow", "setMotionHeld:", "motionHeld", "showsBackdrop", "fieldColor"]
        guard selectors.allSatisfy({ class_getInstanceMethod(fieldClass, NSSelectorFromString($0)) != nil }) else { return }
        installSpotiVisualEffectsObservers()
        SpotiVisualEffectsHookGroup().activate()
        spotiVisualEffectsActivated = true
        requestSpotiVisualEffectsRefresh()
    }
}

class SpotiVisualEffectsFieldHook: ClassHook<UIView> {
    typealias Group = SpotiVisualEffectsHookGroup
    static let targetName = "SGRArtworkField"

    func layoutSubviews() {
        orig.layoutSubviews()
        updateSpotiVisualEffects(for: target)
    }

    func didMoveToWindow() {
        orig.didMoveToWindow()
        updateSpotiVisualEffects(for: target)
    }

    func setMotionHeld(_ held: Bool) {
        orig.setMotionHeld(held)
        updateSpotiVisualEffects(for: target)
    }
}
