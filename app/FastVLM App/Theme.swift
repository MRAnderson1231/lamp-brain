import SwiftUI

/// Flat gouache colours on warm paper, in the spirit of mid-century concept art.
enum Palette {
    static let paper = Color(red: 0.968, green: 0.949, blue: 0.906)
    static let ink = Color(red: 0.17, green: 0.165, blue: 0.20)
    static let coral = Color(red: 0.91, green: 0.333, blue: 0.227)
    static let mustard = Color(red: 0.949, green: 0.761, blue: 0.188)
    static let violet = Color(red: 0.482, green: 0.369, blue: 0.655)
    static let teal = Color(red: 0.184, green: 0.651, blue: 0.627)
    static let grass = Color(red: 0.49, green: 0.722, blue: 0.29)
    static let pencil = Color(red: 0.435, green: 0.627, blue: 0.867)
}

/// A four-sided shape with each corner nudged inward, so nothing is quite square.
struct Quad: Shape {
    var tl = CGSize.zero
    var tr = CGSize.zero
    var br = CGSize.zero
    var bl = CGSize.zero

    func path(in r: CGRect) -> Path {
        Path { p in
            p.move(to: CGPoint(x: r.minX + tl.width, y: r.minY + tl.height))
            p.addLine(to: CGPoint(x: r.maxX - tr.width, y: r.minY + tr.height))
            p.addLine(to: CGPoint(x: r.maxX - br.width, y: r.maxY - br.height))
            p.addLine(to: CGPoint(x: r.minX + bl.width, y: r.maxY - bl.height))
            p.closeSubpath()
        }
    }
}

/// Atomic-age sparkle: eight strokes through a point, alternating long and short.
struct Starburst: Shape {
    func path(in r: CGRect) -> Path {
        Path { p in
            let c = CGPoint(x: r.midX, y: r.midY)
            let radius = min(r.width, r.height) / 2
            for i in 0..<4 {
                let a = Double(i) * .pi / 4
                let len = radius * (i % 2 == 0 ? 1.0 : 0.55)
                let d = CGPoint(x: cos(a) * len, y: sin(a) * len)
                p.move(to: CGPoint(x: c.x - d.x, y: c.y - d.y))
                p.addLine(to: CGPoint(x: c.x + d.x, y: c.y + d.y))
            }
        }
    }
}

/// Blue-pencil construction lines running to two vanishing points off the page.
struct PencilLines: View {
    var body: some View {
        Canvas { ctx, size in
            let w = size.width, h = size.height
            var path = Path()
            let left = CGPoint(x: -0.35 * w, y: 0.58 * h)
            let right = CGPoint(x: 1.4 * w, y: 0.50 * h)
            for i in 0..<7 {
                let t = CGFloat(i) / 6
                path.move(to: left)
                path.addLine(to: CGPoint(x: w * 1.05, y: h * (-0.25 + 1.5 * t)))
                path.move(to: right)
                path.addLine(to: CGPoint(x: -0.05 * w, y: h * (-0.15 + 1.3 * t)))
            }
            // a few verticals, like the corners of buildings never inked in
            for x in [0.07, 0.31, 0.585, 0.93] {
                path.move(to: CGPoint(x: w * x, y: h * 0.04))
                path.addLine(to: CGPoint(x: w * (x + 0.012), y: h * 0.97))
            }
            ctx.stroke(path, with: .color(Palette.pencil.opacity(0.22)), lineWidth: 1)
        }
        .allowsHitTesting(false)
    }
}

extension Font {
    /// SF in its wide, heavy cut for display text.
    static func display(_ size: CGFloat) -> Font {
        .system(size: size, weight: .black).width(.expanded)
    }

    static func label(_ size: CGFloat = 11) -> Font {
        .system(size: size, weight: .semibold).width(.expanded)
    }
}
