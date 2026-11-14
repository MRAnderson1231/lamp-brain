import math, random
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 2266, 1488
S = 2  # pt -> px
GROUND, SHEET, CARD = "#E4E4E6", "#FFFFFF", "#F7F7F8"
INK, INK2, INK3 = "#1C1C1E", "#6E6E73", "#A1A1A6"
HL, WARM = "#EFEBE3", "#E08A3C"
PEN = (38, 42, 58)

F = "/System/Library/Fonts/"
serif = ImageFont.truetype("/System/Library/Fonts/Supplemental/Georgia.ttf", 20 * S)
serif_i = ImageFont.truetype("/System/Library/Fonts/Supplemental/Georgia Italic.ttf", 16 * S)
title = ImageFont.truetype("/System/Library/Fonts/Supplemental/Georgia.ttf", 28 * S)
ui = ImageFont.truetype(F + "HelveticaNeue.ttc", 14 * S)
ui_b = ImageFont.truetype(F + "HelveticaNeue.ttc", 13 * S, index=1)
cjk = ImageFont.truetype(F + "Hiragino Sans GB.ttc", 15 * S)

img = Image.new("RGB", (W, H), GROUND)
d = ImageDraw.Draw(img)

# book page
px0, px1, py0 = 250 * S // 2 * 2 // 2 + 60, W - 640, 150
d.rounded_rectangle((px0, py0, px1, H + 60), 40, fill=SHEET)

# top glass bar
d.rounded_rectangle((W // 2 - 420, 34, W // 2 + 420, 122), 44, fill="#F4F4F6", outline="#D6D6DA", width=2)
d.text((W // 2, 78), "Pride and Prejudice  ·  Chapter 1", font=ui, fill=INK, anchor="mm")
for cx in (W // 2 - 370, W // 2 + 370):
    d.ellipse((cx - 26, 52, cx + 26, 104), fill="#E8E8EB")
d.text((W // 2 - 370, 78), "‹", font=title, fill=INK, anchor="mm")
d.text((W // 2 + 370, 76), "Aa", font=ui_b, fill=INK, anchor="mm")

# text
x0, x1 = px0 + 120, px1 - 120
y = py0 + 110
d.text((x0, y), "Chapter 1", font=title, fill=INK)
y += 120
LH = 34 * S
paras = [
    "It is a truth universally acknowledged, that a single man in possession of a good "
    "fortune, must be in want of a wife.",
    "However little known the feelings or views of such a man may be on his first entering "
    "a neighbourhood, this truth is so well fixed in the minds of the surrounding families, "
    "that he is considered the rightful property of some one or other of their daughters.",
    "\u201cMy dear Mr. Bennet,\u201d said his lady to him one day, \u201chave you heard that "
    "Netherfield Park is let at last?\u201d",
    "Mr. Bennet replied that he had not.",
    "\u201cBut it is,\u201d returned she; \u201cfor Mrs. Long has just been here, and she told "
    "me all about it.\u201d",
]
boxes = {}
space = d.textlength(" ", font=serif)
for pi, p in enumerate(paras):
    words = p.split(" ")
    lines, cur, cw = [], [], 0
    indent = 0 if pi == 0 else 46
    width = x1 - x0
    for w_ in words:
        lw = d.textlength(w_, font=serif)
        lim = width - (indent if not lines else 0)
        if cur and cw + space + lw > lim:
            lines.append(cur); cur, cw = [w_], lw
        else:
            cw = cw + (space if cur else 0) + lw; cur.append(w_)
    lines.append(cur)
    for li, ln in enumerate(lines):
        xx = x0 + (indent if li == 0 else 0)
        for w_ in ln:
            lw = d.textlength(w_, font=serif)
            boxes.setdefault((pi, w_), []).append((xx, y, xx + lw, y + LH))
            xx += lw + space
        y += LH
    y += 18

# highlighted first sentence (selected)
first = [b for (pi, w_), bs in boxes.items() if pi == 0 for b in bs]
rows = {}
for b in first:
    rows.setdefault(b[1], []).append(b)
hl = Image.new("RGB", (W, H), SHEET)
for ry, bs in rows.items():
    d.rounded_rectangle((min(b[0] for b in bs) - 8, ry + 6, max(b[2] for b in bs) + 8, ry + LH - 4), 10, fill=HL)

# warm "lamp hint" glow around the circled word
u = boxes[(0, "universally")][0]
glow = Image.new("L", (W, H), 0)
gd = ImageDraw.Draw(glow)
gd.ellipse((u[0] - 70, u[1] - 40, u[2] + 70, u[3] + 40), fill=150)
glow = glow.filter(ImageFilter.GaussianBlur(38))
img.paste(Image.new("RGB", (W, H), (246, 214, 176)), (0, 0), glow)
d = ImageDraw.Draw(img)

# redraw text on top
y = py0 + 110
d.text((x0, y), "Chapter 1", font=title, fill=INK)
for (pi, w_), bs in boxes.items():
    for b in bs:
        d.text((b[0], b[1] + 4), w_, font=serif, fill=INK)

random.seed(4)
def stroke(pts, width=6):
    d.line(pts, fill=PEN, width=width, joint="curve")
    for p in (pts[0], pts[-1]):
        d.ellipse((p[0] - width / 2, p[1] - width / 2, p[0] + width / 2, p[1] + width / 2), fill=PEN)

# pencil circle around "universally"
cx, cy = (u[0] + u[2]) / 2, (u[1] + u[3]) / 2 + 4
rx, ry_ = (u[2] - u[0]) / 2 + 26, LH / 2 + 4
pts = []
for i in range(80):
    t = -0.4 + i / 79 * (2 * math.pi + 0.7)
    wob = 1 + 0.035 * math.sin(3 * t + 1) + 0.02 * random.random()
    pts.append((cx + rx * wob * math.cos(t), cy + ry_ * wob * math.sin(t) * (1 + 0.06 * t / 6)))
stroke(pts)

# underline being written under "possession of a good"
seg = boxes[(0, "possession")][0], boxes[(0, "good")][0]
ux0, ux1, uy = seg[0][0] - 4, seg[1][2] + 6, seg[0][3] - 6
upts = [(ux0 + (ux1 - ux0) * i / 40, uy + 2.5 * math.sin(i / 5) + i * 0.08) for i in range(41)]
upts = upts[:30]
stroke(upts, 5)
hx, hy = upts[-1]
# Pencil hover preview
d.ellipse((hx - 9, hy - 9, hx + 9, hy + 9), outline=INK3, width=3)

# "?" in the left margin
qx, qy = px0 + 48, boxes[(0, "It")][0][1] + 6
q = [(qx + 4 + 17 * math.cos(a), qy + 18 + 17 * math.sin(a)) for a in [-math.pi * 0.95 + k / 16 * (math.pi * 1.45) for k in range(17)]]
q += [(qx + 5, qy + 48), (qx + 4, qy + 58)]
stroke(q, 5)
d.ellipse((qx - 1, qy + 70, qx + 9, qy + 80), fill=PEN)

# Margin response card
cx0, cy0 = px1 + 50, u[1] - 40
d.rounded_rectangle((cx0, cy0, W - 60, cy0 + 540), 34, fill=CARD, outline="#DEDEE2", width=2)
d.ellipse((cx0 + 40, cy0 + 48, cx0 + 58, cy0 + 66), fill=WARM)
d.text((cx0 + 76, cy0 + 57), "MARGIN", font=ui_b, fill=INK2, anchor="lm")
d.text((cx0 + 40, cy0 + 110), "universally", font=title, fill=INK)
d.text((cx0 + 40, cy0 + 190), "普遍地；被所有人", font=cjk, fill=INK)
for i, line in enumerate(["Not really everyone —", "Austen is being ironic.", "Who actually believes it?"]):
    d.text((cx0 + 40, cy0 + 262 + i * 50), line, font=serif_i, fill=INK2)
d.rounded_rectangle((cx0 + 40, cy0 + 456, cx0 + 270, cy0 + 500), 21, fill="#ECECEE")
d.text((cx0 + 155, cy0 + 478), "Try it yourself", font=ui_b, fill=INK, anchor="mm")

img.save("/tmp/bl/margin_ui.png")
print("hover_px", round(hx), round(hy))
