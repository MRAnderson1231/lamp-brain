import CoreImage
import FastVLM
import Foundation
import MLX
import MLXLMCommon
import MLXVLM

/// Asks FastVLM, running on MLX on this Mac, what expression is in a camera frame.
@Observable
@MainActor
final class EmotionReader {
    private(set) var ready = false
    private(set) var status = "Waking up the model…"

    // Kept short: small models stop following long instructions.
    private let question =
        "What is the facial expression of the person? Answer with one word: neutral, happy, laughing, sad, or surprised."
    private let maxTokens = 28
    private var container: ModelContainer?

    init() {
        FastVLM.register(modelFactory: VLMModelFactory.shared)
    }

    func load() async {
        guard container == nil else { return }
        do {
            MLX.GPU.set(cacheLimit: 20 * 1024 * 1024)
            container = try await VLMModelFactory.shared.loadContainer(
                configuration: FastVLM.modelConfiguration
            ) { _ in }
            ready = true
            status = "On this Mac"
        } catch {
            status = "Model failed to load"
            print("model load error: \(error)")
        }
    }

    /// Returns the model's raw answer and how long it took, or nil on failure.
    func read(_ frame: CVImageBuffer) async -> (text: String, seconds: Double)? {
        guard let container else { return nil }
        let input = UserInput(
            prompt: .text(question),
            images: [.ciImage(CIImage(cvPixelBuffer: frame))]
        )
        let limit = maxTokens
        let start = Date()
        do {
            let result = try await container.perform { context in
                let prepared = try await context.processor.prepare(input: input)
                return try MLXLMCommon.generate(
                    input: prepared, parameters: GenerateParameters(temperature: 0.0), context: context
                ) { tokens in
                    // The answer comes as a sentence; stop as soon as a mood word shows up.
                    if tokens.count >= limit { return .stop }
                    if tokens.count >= 2, Emotion.parse(context.tokenizer.decode(tokens: tokens)) != nil {
                        return .stop
                    }
                    return .more
                }
            }
            return (result.output, Date().timeIntervalSince(start))
        } catch {
            print("inference error: \(error)")
            return nil
        }
    }
}
