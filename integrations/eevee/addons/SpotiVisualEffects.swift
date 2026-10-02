// SPDX-License-Identifier: GPL-3.0-or-later
// Original player decoration for the optional Eevee integration. This owns only
// its own layers; it never changes Spotify's views, artwork, controls or audio.
import UIKit
import QuartzCore
import ObjectiveC

private var spotiVisualEffectsAssociation: UInt8 = 0

private struct SpotiVisualEffectsConfiguration: Equatable {
    let style: String
    let intensity: CGFloat
    let motion: Bool

    static func read() -> Self {
        let defaults = UserDefaults.standard
        let selected = defaults.string(forKey: "spotifyglass.redesign.visuals.style") ?? "off"
        let value = (defaults.object(forKey: "spotifyglass.redesign.visuals.intensity") as? NSNumber)?.doubleValue ?? 0.65
        return Self(
            style: ["artwork", "neon", "glass"].contains(selected) ? selected : "off",
            intensity: CGFloat(value.isFinite ? min(1, max(0, value)) : 0.65),
            motion: (defaults.object(forKey: "spotifyglass.redesign.visuals.motion") as? NSNumber)?.boolValue ?? true
        )
    }
}

// These getter signatures belong to SGRArtworkField, not to a guessed Spotify
// class. Activation checks every selector; the packaged 0.22.0 dylib contains
// the class and selectors and SGRField.h declares their return types.
private func spotiFieldFlag(_ field: UIView, _ name: String) -> Bool {
    let selector = NSSelectorFromString(name)
    guard let method = class_getInstanceMethod(type(of: field), selector) else { return false }
    typealias Getter = @convention(c) (AnyObject, Selector) -> Bool
    return unsafeBitCast(method_getImplementation(method), to: Getter.self)(field, selector)
}

private func spotiFieldColor(_ field: UIView) -> UIColor {
    field.perform(NSSelectorFromString("fieldColor"))?.takeUnretainedValue() as? UIColor ?? .systemPurple
}

// Called only by the narrow SGRArtworkField hook. A player is the only owner in
// the pinned mod that enables showsBackdrop, so album/playlist fields stay intact.
func updateSpotiVisualEffects(for field: UIView) {
    guard Thread.isMainThread, spotiFieldFlag(field, "showsBackdrop") else { return }
    SpotiVisualEffectsRegistry.shared.register(field)
}

func installSpotiVisualEffectsObservers() {
    _ = SpotiVisualEffectsRegistry.shared
}

private final class SpotiVisualEffectsRegistry {
    static let shared = SpotiVisualEffectsRegistry()
    private let fields = NSHashTable<UIView>.weakObjects()
    private var configuration = SpotiVisualEffectsConfiguration.read()
    private var observers: [NSObjectProtocol] = []
    private var transitioning = false
    private var appActive = UIApplication.shared.applicationState == .active

    private init() {
        observe("spotifyglass.redesign.visuals.changed") { [weak self] _ in
            guard let self = self else { return }
            self.configuration = .read()
            self.refreshAll()
        }
        observers.append(NotificationCenter.default.addObserver(forName: UserDefaults.didChangeNotification, object: nil, queue: .main) { [weak self] _ in
            guard let self = self else { return }
            let updated = SpotiVisualEffectsConfiguration.read()
            guard updated != self.configuration else { return }
            self.configuration = updated
            self.refreshAll()
        })
        observe("spotifyglass.redesign.fieldColorDidChange") { [weak self] note in
            guard let self = self, let field = note.object as? UIView,
                  self.fields.contains(field) else { return }
            self.refresh(field)
        }
        observe("spotifyglass.playerTransition") { [weak self] _ in
            self?.transitioning = true
            self?.refreshAll()
        }
        observe("spotifyglass.playerTransitionEnded") { [weak self] _ in
            self?.transitioning = false
            self?.refreshAll()
        }
        observers.append(NotificationCenter.default.addObserver(forName: UIApplication.willResignActiveNotification, object: nil, queue: .main) { [weak self] _ in
            // UIKit sends willResign before applicationState necessarily changes.
            self?.appActive = false
            self?.refreshAll()
        })
        observers.append(NotificationCenter.default.addObserver(forName: UIApplication.didBecomeActiveNotification, object: nil, queue: .main) { [weak self] _ in
            self?.appActive = true
            self?.refreshAll()
        })
        for name in [Notification.Name.NSProcessInfoPowerStateDidChange,
                     UIAccessibility.reduceMotionStatusDidChangeNotification] {
            observers.append(NotificationCenter.default.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in
                self?.refreshAll()
            })
        }
    }

    private func observe(_ name: String, handler: @escaping (Notification) -> Void) {
        observers.append(NotificationCenter.default.addObserver(forName: Notification.Name(name), object: nil, queue: .main, using: handler))
    }

    func register(_ field: UIView) {
        fields.add(field)
        refresh(field)
    }

    private func refreshAll() {
        for field in fields.allObjects { refresh(field) }
    }

    private func refresh(_ field: UIView) {
        let existing = objc_getAssociatedObject(field, &spotiVisualEffectsAssociation) as? SpotiVisualEffectsDecoration
        guard configuration.style != "off", configuration.intensity > 0 else {
            existing?.remove()
            objc_setAssociatedObject(field, &spotiVisualEffectsAssociation, nil, .OBJC_ASSOCIATION_RETAIN_NONATOMIC)
            return
        }
        let decoration: SpotiVisualEffectsDecoration
        if let existing = existing {
            decoration = existing
        } else {
            decoration = SpotiVisualEffectsDecoration(field: field)
            objc_setAssociatedObject(field, &spotiVisualEffectsAssociation, decoration, .OBJC_ASSOCIATION_RETAIN_NONATOMIC)
        }
        decoration.update(configuration, transitioning: transitioning, appActive: appActive)
    }
}

private final class SpotiVisualEffectsDecoration {
    private weak var field: UIView?
    private let root = CALayer()
    private let wash = CAGradientLayer()
    private let upperGlow = CAGradientLayer()
    private let lowerGlow = CAGradientLayer()
    private let pane = CAGradientLayer()
    private let rim = CAGradientLayer()
    private var previousConfiguration: SpotiVisualEffectsConfiguration?
    private var previousColor: UIColor?
    private var previousSize = CGSize.zero
    private var moving = false

    init(field: UIView) {
        self.field = field
        root.name = "spoti.visuals.decoration"
        root.masksToBounds = true
        for layer in [wash, upperGlow, lowerGlow, pane, rim] {
            layer.actions = ["bounds": NSNull(), "position": NSNull(), "colors": NSNull(),
                             "opacity": NSNull(), "transform": NSNull(), "backgroundColor": NSNull()]
            root.addSublayer(layer)
        }
        for glow in [upperGlow, lowerGlow] {
            glow.type = .radial
            glow.startPoint = CGPoint(x: 0.5, y: 0.5)
            glow.endPoint = CGPoint(x: 1, y: 1)
            glow.locations = [0, 0.45, 1]
        }
        wash.startPoint = CGPoint(x: 0.2, y: 0)
        wash.endPoint = CGPoint(x: 0.8, y: 1)
        pane.cornerRadius = 32
        pane.cornerCurve = .continuous
        pane.borderWidth = 0.5
        pane.masksToBounds = true
        pane.startPoint = .zero
        pane.endPoint = CGPoint(x: 1, y: 1)
        rim.startPoint = CGPoint(x: 0, y: 0.5)
        rim.endPoint = CGPoint(x: 1, y: 0.5)
        field.layer.addSublayer(root)
    }

    func remove() {
        stopMotion()
        root.removeFromSuperlayer()
    }

    func update(_ configuration: SpotiVisualEffectsConfiguration, transitioning: Bool, appActive: Bool) {
        guard let field = field else { return }
        // Keep the effect within one screen even when Spotify expands the
        // scrolling background to include the queue and recommendations.
        let screenHeight = field.window?.bounds.height ?? UIScreen.main.bounds.height
        let size = CGSize(width: max(0, field.bounds.width), height: max(0, min(field.bounds.height, screenHeight)))
        let color = spotiFieldColor(field)
        if size != previousSize {
            previousSize = size
            layout(size)
        }
        if configuration != previousConfiguration || previousColor?.isEqual(color) != true {
            previousConfiguration = configuration
            previousColor = color
            paint(configuration, color: color)
        }
        let shouldMove = configuration.motion && configuration.style != "glass"
            && size.width > 0 && size.height > 0 && field.window != nil
            && appActive && UIApplication.shared.applicationState == .active
            && !UIAccessibility.isReduceMotionEnabled
            && !ProcessInfo.processInfo.isLowPowerModeEnabled
            && !spotiFieldFlag(field, "motionHeld") && !transitioning && isVisible(field)
        if shouldMove != moving {
            shouldMove ? startMotion() : stopMotion()
        }
    }

    private func isVisible(_ field: UIView) -> Bool {
        var view: UIView? = field
        while let current = view {
            if current.isHidden || current.alpha < 0.01 { return false }
            view = current.superview
        }
        return true
    }

    private func layout(_ size: CGSize) {
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        root.frame = CGRect(origin: .zero, size: size)
        wash.frame = root.bounds
        let diameter = size.width * 1.65
        upperGlow.frame = CGRect(x: -diameter * 0.35, y: -diameter * 0.2, width: diameter, height: diameter)
        lowerGlow.frame = CGRect(x: size.width - diameter * 0.65, y: size.height * 0.40, width: diameter, height: diameter)
        pane.frame = CGRect(x: 14, y: size.height * 0.54, width: max(0, size.width - 28), height: size.height * 0.32)
        rim.frame = CGRect(x: size.width * 0.12, y: max(0, size.height - 2), width: size.width * 0.76, height: 1)
        CATransaction.commit()
    }

    private func paint(_ configuration: SpotiVisualEffectsConfiguration, color: UIColor) {
        let strength = configuration.intensity
        var hue: CGFloat = 0.74
        var saturation: CGFloat = 0.6
        var brightness: CGFloat = 0
        var alpha: CGFloat = 0
        if !color.getHue(&hue, saturation: &saturation, brightness: &brightness, alpha: &alpha) {
            hue = 0.74
            saturation = 0.35
        }
        let primary: UIColor
        let secondary: UIColor
        if configuration.style == "neon" {
            primary = UIColor(red: 0.65, green: 0.18, blue: 1, alpha: 1)
            secondary = UIColor(red: 0.04, green: 0.86, blue: 1, alpha: 1)
        } else {
            primary = UIColor(hue: hue, saturation: min(0.90, max(0.28, saturation)), brightness: 1, alpha: 1)
            secondary = UIColor(hue: (hue + 0.12).truncatingRemainder(dividingBy: 1), saturation: 0.52, brightness: 0.95, alpha: 1)
        }
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        if configuration.style == "glass" {
            wash.colors = [UIColor.black.withAlphaComponent(0.36 * strength).cgColor,
                           UIColor.black.withAlphaComponent(0.78 * strength).cgColor]
            upperGlow.opacity = 0
            lowerGlow.opacity = 0
            pane.opacity = Float(strength)
            pane.colors = [UIColor.white.withAlphaComponent(0.11).cgColor,
                           UIColor.white.withAlphaComponent(0.025).cgColor,
                           UIColor.black.withAlphaComponent(0.10).cgColor]
            pane.borderColor = UIColor.white.withAlphaComponent(0.20).cgColor
            rim.opacity = 0
        } else {
            wash.colors = [UIColor.black.withAlphaComponent(0.08 * strength).cgColor,
                           UIColor.black.withAlphaComponent(0.35 * strength).cgColor]
            upperGlow.opacity = 1
            lowerGlow.opacity = 1
            upperGlow.colors = [primary.withAlphaComponent(0.58 * strength).cgColor,
                                primary.withAlphaComponent(0.22 * strength).cgColor, UIColor.clear.cgColor]
            lowerGlow.colors = [secondary.withAlphaComponent(0.36 * strength).cgColor,
                                secondary.withAlphaComponent(0.12 * strength).cgColor, UIColor.clear.cgColor]
            pane.opacity = 0
            rim.opacity = configuration.style == "neon" ? Float(strength) : 0
            rim.colors = [primary.withAlphaComponent(0).cgColor, primary.cgColor,
                          secondary.cgColor, secondary.withAlphaComponent(0).cgColor]
        }
        CATransaction.commit()
    }

    private func startMotion() {
        moving = true
        // Core Animation composites two slow glows. No display link, timer,
        // bitmap blur or work on each rendered frame is introduced.
        for (index, glow) in [upperGlow, lowerGlow].enumerated() {
            let drift = CABasicAnimation(keyPath: "transform.translation.x")
            drift.fromValue = index == 0 ? -12 : 12
            drift.toValue = index == 0 ? 12 : -12
            drift.duration = index == 0 ? 7.5 : 9.5
            drift.autoreverses = true
            drift.repeatCount = .infinity
            drift.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
            glow.add(drift, forKey: "spoti.visuals.drift")
            let breathe = CABasicAnimation(keyPath: "opacity")
            breathe.fromValue = 0.72
            breathe.toValue = 1
            breathe.duration = index == 0 ? 5.5 : 8
            breathe.autoreverses = true
            breathe.repeatCount = .infinity
            breathe.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
            glow.add(breathe, forKey: "spoti.visuals.breathe")
        }
    }

    private func stopMotion() {
        moving = false
        upperGlow.removeAllAnimations()
        lowerGlow.removeAllAnimations()
    }
}
