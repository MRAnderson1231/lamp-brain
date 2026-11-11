import AVFoundation
import CoreImage
import SwiftUI
import Video

/// Ties the three pieces together: camera frames in, an emotion out, the lamp reacting.
@Observable
@MainActor
final class AppState {
    let director = LampDirector()
    let reader = EmotionReader()
    private let camera = CameraController()

    private(set) var frame: CVImageBuffer?
    private(set) var emotion: Emotion = .neutral
    private(set) var latencyMS: Int?
    private(set) var heard = ""

    private var stabiliser = Stabiliser()
    private var pinnedUntil = Date.distantPast

    /// Runs until the view goes away.
    func run() async {
        camera.start()
        let frames = AsyncStream<CMSampleBuffer>(bufferingPolicy: .bufferingNewest(1)) {
            camera.attach(continuation: $0)
        }
        async let loading: () = reader.load()
        async let watching: () = watch()
        for await sample in frames {
            if let buffer = sample.imageBuffer { frame = buffer }
        }
        camera.detatch()
        _ = await (loading, watching)
    }

    /// Clicking a mood shows it for a few seconds, whatever the camera sees.
    func pin(_ emotion: Emotion) {
        pinnedUntil = Date().addingTimeInterval(6)
        show(emotion)
    }

    private func watch() async {
        while !Task.isCancelled {
            guard reader.ready, let frame else {
                try? await Task.sleep(for: .milliseconds(150))
                continue
            }
            if let reading = await reader.read(frame) {
                heard = reading.text.trimmingCharacters(in: .whitespacesAndNewlines)
                latencyMS = Int(reading.seconds * 1000)
                let stable = stabiliser.update(Emotion.parse(reading.text))
                if Date() >= pinnedUntil { show(stable) }
            }
            try? await Task.sleep(for: .milliseconds(120))
        }
    }

    private func show(_ next: Emotion) {
        guard next != emotion else { return }
        emotion = next
        director.set(next)
    }
}
