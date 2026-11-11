import SwiftUI

/// The five moods the lamp can mirror.
enum Emotion: String, CaseIterable, Identifiable {
    case neutral, happy, laughing, sad, surprised

    var id: String { rawValue }

    var title: String { rawValue.capitalized }

    /// Flat colour used for this mood across the interface.
    var color: Color {
        switch self {
        case .neutral: Palette.teal
        case .happy: Palette.mustard
        case .laughing: Palette.coral
        case .sad: Palette.violet
        case .surprised: Palette.grass
        }
    }

    /// One line under the big word.
    var caption: String {
        switch self {
        case .neutral: "The lamp is minding its own business."
        case .happy: "The lamp is pleased for you."
        case .laughing: "The lamp cannot keep still."
        case .sad: "The lamp is sad with you."
        case .surprised: "The lamp did not see that coming."
        }
    }

    /// Words the model tends to say instead of a label.
    private static let synonyms: [(stem: String, emotion: Emotion)] = [
        ("laugh", .laughing), ("smil", .happy), ("joy", .happy), ("cheer", .happy),
        ("unhappy", .sad), ("cry", .sad), ("frown", .sad), ("upset", .sad), ("depress", .sad),
        ("shock", .surprised), ("surpris", .surprised), ("amaz", .surprised), ("astonish", .surprised),
        ("calm", .neutral), ("serious", .neutral), ("none", .neutral),
    ]

    /// Turn the model's free text into a label, or nil if it said something else.
    ///
    /// The model usually answers in a sentence ("The facial expression of the person can be
    /// described as surprised…"), so this takes whichever mood word appears first.
    static func parse(_ text: String) -> Emotion? {
        let t = text.lowercased()
        var best: (index: String.Index, emotion: Emotion)?
        func consider(_ word: String, _ emotion: Emotion) {
            guard let range = t.range(of: word) else { return }
            if best == nil || range.lowerBound < best!.index { best = (range.lowerBound, emotion) }
        }
        // synonyms first, so "unhappy" wins over the "happy" inside it at the same position
        for (stem, emotion) in synonyms { consider(stem, emotion) }
        for emotion in allCases where !t.contains("un" + emotion.rawValue) { consider(emotion.rawValue, emotion) }
        return best?.emotion
    }
}

/// Majority vote over the last few readings so the lamp doesn't flicker.
struct Stabiliser {
    private var recent: [Emotion] = []
    private let window = 3
    private(set) var current: Emotion = .neutral

    mutating func update(_ reading: Emotion?) -> Emotion {
        guard let reading else { return current }
        recent.append(reading)
        if recent.count > window { recent.removeFirst() }
        guard recent.count >= 2 else { return current }
        let counts = Dictionary(grouping: recent, by: { $0 }).mapValues(\.count)
        if let top = counts.max(by: { $0.value < $1.value }), top.value * 2 > recent.count {
            current = top.key
        }
        return current
    }
}
