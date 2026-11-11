import AppKit
import SceneKit
import simd

/// Everything that can move or glow on the lamp. Angles are radians.
struct LampPose {
    var yaw: Float = 0          // whole lamp turns on its base
    var low: Float = 0          // lower arm leans forward
    var up: Float = 0           // upper arm folds forward
    var nod: Float = 0          // head pitches down
    var turn: Float = 0         // head turns on its own
    var hop: Float = 0          // height above the table, metres
    var squashUp: Float = 1
    var squashSide: Float = 1
    var glow: Float = 1
    var warmth: Float = 1       // 0 = cold blue, 1 = warm

    static func mix(_ a: LampPose, _ b: LampPose, _ t: Float) -> LampPose {
        func l(_ x: Float, _ y: Float) -> Float { x + (y - x) * t }
        return LampPose(
            yaw: l(a.yaw, b.yaw), low: l(a.low, b.low), up: l(a.up, b.up), nod: l(a.nod, b.nod),
            turn: l(a.turn, b.turn), hop: l(a.hop, b.hop), squashUp: l(a.squashUp, b.squashUp),
            squashSide: l(a.squashSide, b.squashSide), glow: l(a.glow, b.glow), warmth: l(a.warmth, b.warmth))
    }
}

/// Animation clips sampled out of Blender (see lamp_clips.py), read from clips.json.
struct ClipLibrary: Decodable {
    struct Clip: Decodable {
        let frames: Float
        let channels: [String: [Float]]
    }

    let fps: Float
    let step: Float
    let clips: [String: Clip]

    func length(_ name: String) -> Double {
        Double((clips[name]?.frames ?? 0) / fps)
    }

    func pose(_ name: String, at seconds: Double) -> LampPose {
        guard let clip = clips[name] else { return LampPose() }
        let position = Float(seconds) * fps / step
        func value(_ channel: String, _ fallback: Float) -> Float {
            guard let samples = clip.channels[channel], !samples.isEmpty else { return fallback }
            let clamped = min(max(position, 0), Float(samples.count - 1))
            let i = Int(clamped)
            let j = min(i + 1, samples.count - 1)
            return samples[i] + (samples[j] - samples[i]) * (clamped - Float(i))
        }
        return LampPose(
            yaw: value("yaw", 0), low: value("low", 0), up: value("up", 0), nod: value("nod", 0),
            turn: value("turn", 0), hop: value("hop", 0), squashUp: value("squashUp", 1),
            squashSide: value("squashSide", 1), glow: value("glow", 1), warmth: value("warmth", 1))
    }
}

/// Owns the 3D scene and plays the lamp's clips: emotion loops, one-shots, and
/// random idles while nothing is happening. Called once per rendered frame.
final class LampDirector: NSObject, SCNSceneRendererDelegate {
    let scene = SCNScene()
    let cameraNode = SCNNode()

    private let library: ClipLibrary
    private var joints: [String: SCNNode] = [:]
    private var rest: [String: simd_float4x4] = [:]
    private let spot = SCNLight()
    private var glowMaterials: [(material: SCNMaterial, strength: CGFloat)] = []

    private static let breathe = "idle_breathe"
    private static let idles = ["idle_look_left", "idle_look_right", "idle_curious", "idle_hello"]
    private static let blendSeconds = 0.35

    // requested from the main thread, consumed on the render thread
    private let lock = NSLock()
    private var requested: Emotion = .neutral

    private var emotion: Emotion = .neutral
    private var clip = LampDirector.breathe
    private var loops = true
    private var clipStart: TimeInterval = -1
    private var blendStart: TimeInterval = 0
    private var snapshot = LampPose()
    private var current = LampPose()
    private var nextIdle: TimeInterval = 0

    override init() {
        let url = Bundle.main.url(forResource: "clips", withExtension: "json")
        library = (url.flatMap { try? Data(contentsOf: $0) }
            .flatMap { try? JSONDecoder().decode(ClipLibrary.self, from: $0) })
            ?? ClipLibrary(fps: 24, step: 0.5, clips: [:])
        super.init()
        buildScene()
    }

    func set(_ emotion: Emotion) {
        lock.lock()
        requested = emotion
        lock.unlock()
    }

    // MARK: - Scene

    private func buildScene() {
        scene.background.contents = NSColor.clear
        scene.lightingEnvironment.contents = NSColor(white: 0.62, alpha: 1)
        scene.lightingEnvironment.intensity = 1.0

        if let url = Bundle.main.url(forResource: "Lamp", withExtension: "usdz"),
            let source = try? SCNScene(url: url, options: nil),
            let lamp = source.rootNode.childNode(withName: "Lamp", recursively: true)
        {
            scene.rootNode.addChildNode(lamp)
            for name in ["root", "swivel", "lower", "upper", "head"] {
                if let node = lamp.childNode(withName: "J_" + name, recursively: true) {
                    joints[name] = node
                    rest[name] = node.simdTransform
                }
            }
            restyle(lamp)
            lamp.childNode(withName: "P_BulbMesh", recursively: true)?
                .enumerateHierarchy { node, _ in node.castsShadow = false }
        }

        // the lamp's own light, sitting in the shade and pointing out of it
        spot.type = .spot
        spot.spotInnerAngle = 40
        spot.spotOuterAngle = 112
        spot.castsShadow = true
        spot.shadowRadius = 4
        spot.shadowSampleCount = 12
        spot.shadowColor = NSColor(white: 0, alpha: 0.35)
        spot.attenuationEndDistance = 7
        spot.zNear = 0.05
        let spotNode = SCNNode()
        spotNode.light = spot
        spotNode.simdPosition = simd_float3(0, 0, 0.22)
        spotNode.simdOrientation = simd_quatf(angle: .pi, axis: simd_float3(1, 0, 0))
        joints["head"]?.addChildNode(spotNode)

        // soft daylight from the upper left so the lamp reads in every mood
        let key = SCNLight()
        key.type = .directional
        key.intensity = 800
        key.color = NSColor(red: 1, green: 0.97, blue: 0.92, alpha: 1)
        key.castsShadow = true
        key.shadowRadius = 8
        key.shadowSampleCount = 16
        key.shadowColor = NSColor(red: 0.17, green: 0.165, blue: 0.2, alpha: 0.28)
        key.orthographicScale = 3
        let keyNode = SCNNode()
        keyNode.light = key
        keyNode.simdEulerAngles = simd_float3(-0.95, -0.6, 0)
        scene.rootNode.addChildNode(keyNode)

        // a skewed patch of lawn for the lamp to stand on
        let path = NSBezierPath()
        path.move(to: NSPoint(x: -0.80, y: -0.62))
        path.line(to: NSPoint(x: 1.20, y: -0.76))
        path.line(to: NSPoint(x: 0.95, y: 0.52))
        path.line(to: NSPoint(x: -0.58, y: 0.68))
        path.close()
        let lawn = SCNShape(path: path, extrusionDepth: 0)
        let lawnMaterial = SCNMaterial()
        lawnMaterial.lightingModel = .physicallyBased
        lawnMaterial.diffuse.contents = NSColor(red: 0.49, green: 0.722, blue: 0.29, alpha: 1)
        lawnMaterial.roughness.contents = 0.95
        lawnMaterial.metalness.contents = 0.0
        lawnMaterial.isDoubleSided = true
        lawn.materials = [lawnMaterial]
        let lawnNode = SCNNode(geometry: lawn)
        lawnNode.simdEulerAngles = simd_float3(-.pi / 2, 0, 0)
        lawnNode.castsShadow = false
        scene.rootNode.addChildNode(lawnNode)

        let camera = SCNCamera()
        camera.fieldOfView = 24
        camera.zNear = 0.1
        camera.zFar = 50
        cameraNode.camera = camera
        let target = simd_float3(0.12, 0.50, 0)
        cameraNode.simdPosition = target + simd_normalize(simd_float3(0.9, 0.22, 1.0)) * 3.9
        cameraNode.simdLook(at: target)
        scene.rootNode.addChildNode(cameraNode)
    }

    /// Repaint the Blender materials in flat poster colours and collect the ones that glow.
    private func restyle(_ lamp: SCNNode) {
        lamp.enumerateHierarchy { node, _ in
            for material in node.geometry?.materials ?? [] {
                material.lightingModel = .physicallyBased
                material.metalness.contents = 0.0
                switch material.name ?? "" {
                case "Lamp_Body":
                    material.diffuse.contents = NSColor(red: 0.91, green: 0.333, blue: 0.227, alpha: 1)
                    material.roughness.contents = 0.42
                case "Lamp_Bolt":
                    material.diffuse.contents = NSColor(red: 0.17, green: 0.165, blue: 0.2, alpha: 1)
                    material.roughness.contents = 0.5
                case "Lamp_Spring":
                    material.diffuse.contents = NSColor(white: 0.82, alpha: 1)
                    material.roughness.contents = 0.35
                case "Lamp_Inner":
                    material.diffuse.contents = NSColor(red: 0.98, green: 0.95, blue: 0.86, alpha: 1)
                    material.roughness.contents = 0.7
                    self.glowMaterials.append((material, 0.55))
                case "Lamp_Bulb":
                    material.diffuse.contents = NSColor.white
                    self.glowMaterials.append((material, 1.6))
                case "Lamp_Vent":
                    material.diffuse.contents = NSColor.white
                    self.glowMaterials.append((material, 1.0))
                default:
                    break
                }
            }
        }
    }

    // MARK: - Playback

    func renderer(_ renderer: SCNSceneRenderer, updateAtTime time: TimeInterval) {
        if clipStart < 0 {
            clipStart = time
            blendStart = time - Self.blendSeconds
            nextIdle = time + .random(in: 2.5...5)
        }

        lock.lock()
        let wanted = requested
        lock.unlock()
        if wanted != emotion {
            emotion = wanted
            switch wanted {
            case .happy: play("happy", loops: true, at: time)
            case .laughing: play("laugh", loops: true, at: time)
            case .sad: play("sad", loops: true, at: time)
            case .surprised: play("surprised", loops: false, at: time)
            case .neutral:
                play(Self.breathe, loops: true, at: time)
                nextIdle = time + .random(in: 2.5...6)
            }
        }

        let length = max(library.length(clip), 0.001)
        var t = time - clipStart
        if loops {
            t = t.truncatingRemainder(dividingBy: length)
        } else if t >= length {
            // a one-shot finished: fall back to breathing
            play(Self.breathe, loops: true, at: time)
            nextIdle = time + .random(in: 2.5...6)
            t = 0
        }
        if emotion == .neutral, clip == Self.breathe, time >= nextIdle {
            play(Self.idles.randomElement() ?? Self.breathe, loops: false, at: time)
            t = 0
        }

        let u = Float(min(1, (time - blendStart) / Self.blendSeconds))
        current = LampPose.mix(snapshot, library.pose(clip, at: t), u * u * (3 - 2 * u))
        apply(current)
    }

    private func play(_ name: String, loops: Bool, at time: TimeInterval) {
        snapshot = current
        clip = name
        self.loops = loops
        clipStart = time
        blendStart = time
    }

    /// Joint frames come from Blender: local Z runs along the segment and local Y is the hinge.
    private func apply(_ pose: LampPose) {
        func rotation(_ angle: Float, _ axis: simd_float3) -> simd_float4x4 {
            simd_float4x4(simd_quatf(angle: angle, axis: axis))
        }
        let x = simd_float3(1, 0, 0), y = simd_float3(0, 1, 0), z = simd_float3(0, 0, 1)

        if let node = joints["root"], let base = rest["root"] {
            var lift = matrix_identity_float4x4
            lift.columns.3 = simd_float4(0, 0, pose.hop, 1)
            let squash = simd_float4x4(diagonal: simd_float4(pose.squashSide, pose.squashSide, pose.squashUp, 1))
            node.simdTransform = base * lift * squash
        }
        if let node = joints["swivel"], let base = rest["swivel"] {
            node.simdTransform = base * rotation(pose.yaw, z)
        }
        if let node = joints["lower"], let base = rest["lower"] {
            node.simdTransform = base * rotation(pose.low, y)
        }
        if let node = joints["upper"], let base = rest["upper"] {
            node.simdTransform = base * rotation(pose.up, y)
        }
        if let node = joints["head"], let base = rest["head"] {
            node.simdTransform = base * rotation(pose.turn, x) * rotation(pose.nod, y)
        }

        let w = CGFloat(pose.warmth)
        let tint = NSColor(red: 0.50 + 0.50 * w, green: 0.66 + 0.06 * w, blue: 1.0 - 0.62 * w, alpha: 1)
        spot.color = tint
        spot.intensity = CGFloat(pose.glow) * 110
        for (material, strength) in glowMaterials {
            material.emission.contents = tint
            material.emission.intensity = CGFloat(pose.glow) * strength
        }
    }
}
