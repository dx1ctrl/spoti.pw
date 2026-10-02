// SPDX-License-Identifier: GPL-3.0-or-later
// Original visual style controls for the optional Eevee integration.
import SwiftUI
import UIKit
import Combine

private enum SpotiVisualChoice: String, CaseIterable, Identifiable {
    case off, artwork, neon, glass

    var id: String { rawValue }

    var title: String {
        switch self {
        case .off: return "Original player"
        case .artwork: return "Artwork aura"
        case .neon: return "Purple neon"
        case .glass: return "Minimal glass"
        }
    }

    var detail: String {
        switch self {
        case .off: return "Additional effects off"
        case .artwork: return "Soft aurora glows in your artwork’s colors"
        case .neon: return "Purple and cyan light on a dark stage"
        case .glass: return "A quiet, smoked-glass panel behind the controls"
        }
    }

    var accent: Color {
        switch self {
        case .off: return .white
        case .artwork: return Color(red: 0.55, green: 0.91, blue: 0.79)
        case .neon: return Color(red: 0.76, green: 0.59, blue: 1)
        case .glass: return Color(red: 0.80, green: 0.87, blue: 0.95)
        }
    }
}

private enum SpotiVisualPreferences {
    static let styleKey = "spotifyglass.redesign.visuals.style"
    static let intensityKey = "spotifyglass.redesign.visuals.intensity"
    static let motionKey = "spotifyglass.redesign.visuals.motion"
    static let changed = Notification.Name("spotifyglass.redesign.visuals.changed")

    static var style: SpotiVisualChoice {
        SpotiVisualChoice(rawValue: UserDefaults.standard.string(forKey: styleKey) ?? "off") ?? .off
    }

    static var intensity: Double {
        guard let value = UserDefaults.standard.object(forKey: intensityKey) as? NSNumber,
              value.doubleValue.isFinite else { return 0.65 }
        return min(1, max(0, value.doubleValue))
    }

    static var motion: Bool {
        guard let value = UserDefaults.standard.object(forKey: motionKey) as? NSNumber else { return true }
        return value.boolValue
    }

    static func set(_ value: Any, forKey key: String) {
        UserDefaults.standard.set(value, forKey: key)
        NotificationCenter.default.post(name: changed, object: nil)
    }
}

struct SpotiVisualsView: View {
    @State private var choice = SpotiVisualPreferences.style
    @State private var intensity = SpotiVisualPreferences.intensity
    @State private var motion = SpotiVisualPreferences.motion

    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 8) {
                    Label("Make the player yours", systemImage: "sparkles")
                        .font(.headline)
                    Text("Three looks for the full-screen player. Choose one below, then open a song.")
                        .font(.subheadline).foregroundColor(.secondary)
                }
                .padding(.vertical, 4)
            } footer: {
                Text("Requires iOS 26 and Redesigned UI. To enable it, hold Home → Mod Settings → Appearance → Redesigned UI, then restart Spotify once. These visual style controls apply without another restart.")
            }

            Section(header: Text("Choose your style")) {
                Button { select(.off) } label: {
                    HStack(spacing: 12) {
                        Image(systemName: "circle.slash").foregroundColor(.secondary)
                            .frame(width: 24)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(SpotiVisualChoice.off.title).foregroundColor(.primary)
                            Text(SpotiVisualChoice.off.detail).font(.caption).foregroundColor(.secondary)
                        }
                        Spacer()
                        if choice == .off {
                            Image(systemName: "checkmark.circle.fill").foregroundColor(.white)
                        }
                    }
                    .padding(.vertical, 3)
                }
                .buttonStyle(.plain)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel("Original player. Additional effects off.")
                .accessibilityAddTraits(choice == .off ? .isSelected : [])

                ForEach([SpotiVisualChoice.artwork, .neon, .glass]) { style in
                    Button { select(style) } label: {
                        SpotiVisualStyleCard(style: style, selected: choice == style,
                                             intensity: intensity)
                    }
                    .buttonStyle(.plain)
                    .listRowInsets(EdgeInsets(top: 7, leading: 0, bottom: 7, trailing: 0))
                    .listRowBackground(Color.clear)
                    .listRowSeparator(.hidden)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("\(style.title). \(style.detail).")
                    .accessibilityAddTraits(choice == style ? .isSelected : [])
                }
            }

            Section(header: Text("Fine-tune"), footer: Text("Motion adds a slow drift to Artwork aura and Purple neon. It pauses with playback, while Spotify is inactive, and with Reduce Motion or Low Power Mode. The glass panel stays still. For a fully static background, also turn off Moving background in Mod Settings → Player → Now playing, then restart Spotify.")) {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Text("Intensity")
                        Spacer()
                        Text("\(Int((intensity * 100).rounded()))%")
                            .monospacedDigit().foregroundColor(.secondary)
                    }
                    Slider(value: intensityBinding, in: 0...1, step: 0.05)
                        .tint(choice.accent)
                        .accessibilityLabel("Visual intensity")
                        .accessibilityValue("\(Int((intensity * 100).rounded())) percent")
                    HStack {
                        Text("Subtle")
                        Spacer()
                        Text("Bold")
                    }
                    .font(.caption).foregroundColor(.secondary)
                }
                .padding(.vertical, 6)
                .disabled(choice == .off)

                Toggle(isOn: motionBinding) {
                    Label("Gentle motion", systemImage: "wind")
                }
                .tint(choice.accent)
                .disabled(choice == .off || choice == .glass)
            }
        }
        .eeveeSettingsListStyle()
        .preferredColorScheme(.dark)
        .onAppear(perform: reload)
        .onReceive(NotificationCenter.default.publisher(for: UserDefaults.didChangeNotification)
            .receive(on: DispatchQueue.main)) { _ in reload() }
    }

    private var intensityBinding: Binding<Double> {
        Binding(get: { intensity }, set: {
            intensity = min(1, max(0, $0.isFinite ? $0 : 0.65))
            SpotiVisualPreferences.set(intensity, forKey: SpotiVisualPreferences.intensityKey)
        })
    }

    private var motionBinding: Binding<Bool> {
        Binding(get: { motion }, set: {
            motion = $0
            SpotiVisualPreferences.set($0, forKey: SpotiVisualPreferences.motionKey)
        })
    }

    private func select(_ style: SpotiVisualChoice) {
        choice = style
        SpotiVisualPreferences.set(style.rawValue, forKey: SpotiVisualPreferences.styleKey)
    }

    private func reload() {
        choice = SpotiVisualPreferences.style
        intensity = SpotiVisualPreferences.intensity
        motion = SpotiVisualPreferences.motion
    }
}

private struct SpotiVisualStyleCard: View {
    let style: SpotiVisualChoice
    let selected: Bool
    let intensity: Double

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            SpotiVisualIllustration(style: style, intensity: intensity)
                .frame(height: 168)
                .accessibilityHidden(true)
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(style.title).font(.headline).foregroundColor(.white)
                    Text(style.detail).font(.caption).foregroundColor(.white.opacity(0.7))
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
                Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                    .font(.title3).foregroundColor(selected ? style.accent : .white.opacity(0.35))
            }
            .padding(16)
        }
        .background(Color(red: 0.08, green: 0.085, blue: 0.10))
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous)
            .strokeBorder(selected ? style.accent.opacity(0.85) : .white.opacity(0.09),
                          lineWidth: selected ? 1.5 : 1))
        .contentShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
    }
}

// Small, static illustrations keep the selection screen quiet and inexpensive.
// The real player effect uses its artwork and is rendered by SpotiVisualsEffects.
private struct SpotiVisualIllustration: View {
    let style: SpotiVisualChoice
    let intensity: Double

    private var strength: Double { 0.15 + intensity * 0.7 }

    var body: some View {
        GeometryReader { geometry in
            ZStack {
                Color(red: 0.025, green: 0.03, blue: 0.045)
                backdrop(width: geometry.size.width)
                HStack(spacing: 22) {
                    sampleArtwork
                        .frame(width: 100, height: 100)
                        .rotationEffect(.degrees(style == .artwork ? -5 : 0))
                    VStack(alignment: .leading, spacing: 13) {
                        VStack(alignment: .leading, spacing: 6) {
                            Capsule().fill(.white.opacity(0.88)).frame(width: 72, height: 5)
                            Capsule().fill(.white.opacity(0.30)).frame(width: 49, height: 4)
                        }
                        Capsule().fill(.white.opacity(0.12)).frame(height: 3)
                            .overlay(alignment: .leading) {
                                Capsule().fill(style.accent).frame(width: 31, height: 3)
                            }
                        HStack(spacing: 20) {
                            Image(systemName: "backward.end.fill").font(.system(size: 11))
                            Image(systemName: "play.fill").font(.system(size: 19))
                            Image(systemName: "forward.end.fill").font(.system(size: 11))
                        }
                        .foregroundColor(.white.opacity(0.9))
                    }
                    .frame(width: 98)
                    .padding(14)
                    .background {
                        if style == .glass {
                            RoundedRectangle(cornerRadius: 18, style: .continuous)
                                .fill(.ultraThinMaterial)
                                .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous)
                                    .strokeBorder(.white.opacity(0.11 + intensity * 0.17)))
                        }
                    }
                }
            }
            .clipped()
        }
    }

    @ViewBuilder
    private func backdrop(width: CGFloat) -> some View {
        switch style {
        case .artwork:
            Ellipse().fill(Color(red: 0.2, green: 0.82, blue: 0.65).opacity(strength))
                .frame(width: width * 0.8, height: 155).blur(radius: 40)
                .offset(x: -width * 0.2, y: 8)
            Ellipse().fill(Color(red: 0.94, green: 0.63, blue: 0.32).opacity(strength * 0.8))
                .frame(width: width * 0.6, height: 110).blur(radius: 40)
                .offset(x: width * 0.25, y: -37)
        case .neon:
            Ellipse().fill(Color.purple.opacity(strength))
                .frame(width: width * 0.7, height: 130).blur(radius: 32)
                .offset(x: -width * 0.25, y: 24)
            Ellipse().fill(Color.cyan.opacity(strength * 0.75))
                .frame(width: width * 0.45, height: 65).blur(radius: 30)
                .offset(x: width * 0.28, y: -38)
            Capsule().fill(Color.purple.opacity(strength)).frame(width: 2, height: 95)
                .shadow(color: .purple.opacity(strength), radius: 12)
                .offset(x: -width * 0.43)
        case .glass:
            LinearGradient(colors: [.white.opacity(strength * 0.17), .clear],
                           startPoint: .topLeading, endPoint: .bottomTrailing)
            Ellipse().fill(Color(red: 0.33, green: 0.43, blue: 0.51).opacity(strength * 0.5))
                .frame(width: width * 0.6, height: 90).blur(radius: 45)
                .offset(x: -width * 0.17, y: -18)
        case .off:
            Color.clear
        }
    }

    private var sampleArtwork: some View {
        ZStack {
            LinearGradient(colors: artworkColors, startPoint: .topLeading, endPoint: .bottomTrailing)
            Circle().strokeBorder(.white.opacity(0.3), lineWidth: 18)
                .frame(width: 98, height: 98).offset(x: 27, y: -15)
            Circle().fill(.black.opacity(0.15)).frame(width: 70, height: 70)
                .offset(x: -30, y: 37)
            Image(systemName: "music.note").font(.system(size: 30, weight: .medium))
                .foregroundColor(.white.opacity(0.92))
        }
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous)
            .strokeBorder(.white.opacity(0.16)))
        .shadow(color: .black.opacity(0.35), radius: 16, y: 9)
    }

    private var artworkColors: [Color] {
        switch style {
        case .artwork: return [Color(red: 0.12, green: 0.56, blue: 0.45), Color(red: 0.92, green: 0.61, blue: 0.31)]
        case .neon: return [Color(red: 0.39, green: 0.16, blue: 0.68), Color(red: 0.13, green: 0.38, blue: 0.52)]
        case .glass, .off: return [Color(red: 0.22, green: 0.29, blue: 0.34), Color(red: 0.10, green: 0.13, blue: 0.17)]
        }
    }
}
