// SPDX-License-Identifier: GPL-3.0-or-later
// Hooks only the existing mod's artwork field; no Spotify playback hooks.
import Orion
import UIKit
import ObjectiveC

struct SpotiVisualEffectsHookGroup: HookGroup { }

private var spotiVisualEffectsActivationScheduled = false

func activateSpotiVisualEffects() {
    guard !spotiVisualEffectsActivationScheduled else { return }
    spotiVisualEffectsActivationScheduled = true
    // dyld has registered Objective-C classes before constructors run; waiting
    // for the main queue also lets both injected tweaks finish initialization.
    DispatchQueue.main.async {
        guard #available(iOS 26.0, *), let fieldClass = NSClassFromString("SGRArtworkField") else { return }
        let selectors = ["layoutSubviews", "didMoveToWindow", "setMotionHeld:", "motionHeld", "showsBackdrop", "fieldColor"]
        guard selectors.allSatisfy({ class_getInstanceMethod(fieldClass, NSSelectorFromString($0)) != nil }) else { return }
        installSpotiVisualEffectsObservers()
        SpotiVisualEffectsHookGroup().activate()
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
