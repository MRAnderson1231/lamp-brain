import SceneKit
import SwiftUI

struct ContentView: View {
    @State private var app = AppState()

    var body: some View {
        ZStack {
            Palette.paper.ignoresSafeArea()
            PencilLines().ignoresSafeArea()

            HStack(spacing: 0) {
                stage
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                sidebar
                    .frame(width: 400)
                    .padding(.trailing, 44)
                    .padding(.vertical, 40)
            }

            header
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                .padding(.leading, 44)
                .padding(.top, 34)
        }
        .frame(minWidth: 1040, minHeight: 680)
        .preferredColorScheme(.light)
        .task { await app.run() }
    }

    // MARK: - Header

    private var header: some View {
        HStack(alignment: .center, spacing: 12) {
            Starburst()
                .stroke(Palette.coral, style: StrokeStyle(lineWidth: 3, lineCap: .round))
                .frame(width: 30, height: 30)
            VStack(alignment: .leading, spacing: 1) {
                Text("LAMP BRAIN")
                    .font(.display(20))
                    .tracking(1.5)
                    .foregroundStyle(Palette.ink)
                Text("It feels what you feel")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(Palette.ink.opacity(0.55))
            }
        }
    }

    // MARK: - Lamp

    private var stage: some View {
        ZStack {
            // a slanted wall behind the lamp, painted in the current mood
            Quad(tl: CGSize(width: 70, height: 60), tr: CGSize(width: 20, height: 0),
                 br: CGSize(width: 90, height: 130), bl: CGSize(width: 0, height: 60))
                .fill(app.emotion.color)
                .overlay {
                    Quad(tl: CGSize(width: 70, height: 60), tr: CGSize(width: 20, height: 0),
                         br: CGSize(width: 90, height: 130), bl: CGSize(width: 0, height: 60))
                        .stroke(Palette.ink, style: StrokeStyle(lineWidth: 3, lineJoin: .round))
                }
                .padding(.leading, 70)
                .padding(.trailing, 50)
                .padding(.top, 110)
                .padding(.bottom, 150)
                .animation(.easeInOut(duration: 0.45), value: app.emotion)

            LampView(director: app.director)
        }
    }

    // MARK: - Camera and readout

    private var sidebar: some View {
        VStack(alignment: .leading, spacing: 0) {
            Spacer(minLength: 30)

            cameraFrame
                .aspectRatio(4.0 / 3.0, contentMode: .fit)

            Text("YOU LOOK")
                .font(.label())
                .tracking(2)
                .foregroundStyle(Palette.ink.opacity(0.55))
                .padding(.top, 34)

            Text(app.emotion.title)
                .font(.display(50))
                .foregroundStyle(Palette.ink)
                .lineLimit(1)
                .minimumScaleFactor(0.6)
                .padding(.horizontal, 10)
                .background(alignment: .bottom) {
                    Quad(tl: CGSize(width: 8, height: 0), br: CGSize(width: 8, height: 0))
                        .fill(app.emotion.color)
                        .frame(height: 20)
                        .offset(y: -6)
                }
                .padding(.leading, -10)

            Text(app.emotion.caption)
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(Palette.ink.opacity(0.7))
                .padding(.top, 8)

            moodRow
                .padding(.top, 26)

            Spacer(minLength: 20)

            if !app.heard.isEmpty {
                Text("\u{201C}\(app.heard)\u{201D}")
                    .font(.system(size: 12, weight: .regular).italic())
                    .foregroundStyle(Palette.ink.opacity(0.5))
                    .lineLimit(2)
                    .padding(.bottom, 8)
                    .help("What the model said about the last frame")
            }

            footer
        }
    }

    private var cameraFrame: some View {
        let shape = Quad(tl: CGSize(width: 0, height: 14), tr: CGSize(width: 0, height: 0),
                         br: CGSize(width: 22, height: 0), bl: CGSize(width: 0, height: 10))
        return ZStack {
            shape.fill(Palette.violet).offset(x: 12, y: 12)
            Group {
                if let frame = app.frame {
                    FrameView(image: frame).scaleEffect(x: -1, y: 1)
                } else {
                    Palette.ink.overlay {
                        Text("Looking for a camera…")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundStyle(Palette.paper.opacity(0.7))
                    }
                }
            }
            .clipShape(shape)
            shape.stroke(Palette.ink, style: StrokeStyle(lineWidth: 3, lineJoin: .round))
        }
    }

    private var moodRow: some View {
        HStack(spacing: 6) {
            ForEach(Emotion.allCases) { mood in
                let active = mood == app.emotion
                Button {
                    app.pin(mood)
                } label: {
                    Text(mood.title)
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(Palette.ink.opacity(active ? 1 : 0.6))
                        .padding(.horizontal, 9)
                        .padding(.vertical, 7)
                        .background {
                            Quad(tl: CGSize(width: 4, height: 0), br: CGSize(width: 4, height: 0))
                                .fill(active ? mood.color : Palette.ink.opacity(0.07))
                        }
                }
                .buttonStyle(.plain)
                .help("Show \(mood.title.lowercased()) for a few seconds")
            }
        }
        .animation(.easeInOut(duration: 0.2), value: app.emotion)
    }

    private var footer: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(app.reader.ready ? Palette.grass : Palette.mustard)
                .frame(width: 8, height: 8)
            Text(app.reader.status)
            if let ms = app.latencyMS {
                Text("·")
                Text("\(ms) ms").monospacedDigit()
            }
            Text("·")
            Text("FastVLM on MLX")
        }
        .font(.system(size: 12, weight: .medium))
        .foregroundStyle(Palette.ink.opacity(0.6))
    }
}

/// The 3D lamp, drawn over whatever SwiftUI puts behind it.
struct LampView: NSViewRepresentable {
    let director: LampDirector

    func makeNSView(context: Context) -> SCNView {
        let view = SCNView()
        view.scene = director.scene
        view.pointOfView = director.cameraNode
        view.delegate = director
        view.backgroundColor = .clear
        view.antialiasingMode = .multisampling4X
        view.preferredFramesPerSecond = 60
        view.rendersContinuously = true
        view.isPlaying = true
        return view
    }

    func updateNSView(_ view: SCNView, context: Context) {}
}

/// Shows one camera frame; the layer takes the pixel buffer directly.
struct FrameView: NSViewRepresentable {
    let image: CVImageBuffer

    func makeNSView(context: Context) -> NSView {
        let view = NSView()
        view.wantsLayer = true
        view.layer?.contentsGravity = .resizeAspectFill
        return view
    }

    func updateNSView(_ view: NSView, context: Context) {
        view.layer?.contents = image
    }
}
