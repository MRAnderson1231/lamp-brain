import glob, os, sys

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

CAP = {
    "1_phone_pickup": ("拿起手机", "底座检测到手机离座（反射层，<10 ms）",
                       "头先转、身体跟上，盯着你，轻轻摇头", "变冷、微亮"),
    "2_stuck_hint": ("卡住了", "Margin：同一题停笔 40 秒 + 反复擦除",
                     "凑近看 → 看你一眼 → 对 iPad 点头“指”一下，Margin 同步亮出提示", "聚焦、变亮"),
    "3_wrong_answer": ("写错了", "Margin 核对答案", "歪头、抬一下头：“嗯？”", "略暗、略冷，不出声"),
    "4_correct": ("答对了", "Margin 核对答案", "两下开心点头 + 小跳", "亮度脉冲、变暖"),
    "5_fatigue_break": ("学太久了", "连续学习时长 + 眨眼变慢 / 打哈欠",
                        "看向你 → 伸懒腰 → 左右晃", "逐渐变暖、变暗，提示休息"),
    "6_comfort": ("情绪低落", "长时间不动 + 坐姿塌陷 + 叹气（FastVLM 综合判断）",
                  "慢慢靠近、放低姿态、轻轻点头", "暖、柔，像呼吸一样起伏"),
    "7_away_sleep": ("你离开了", "座位无人", "看向座位、左右找一找，然后垂头睡去", "渐暗到几乎熄灭"),
    "8_wake_hello": ("你回来了", "有人坐下", "醒来、抬头、点头打招呼，回到工作姿态", "渐亮"),
}
FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"
ft = ImageFont.truetype(FONT, 34, index=1)
fs = ImageFont.truetype(FONT, 21)
fl = ImageFont.truetype(FONT, 17)


def caption(im, key, idx, total):
    title, trig, act, light = CAP[key]
    im = im.convert("RGBA")
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    W, H = im.size
    d.text((28, 22), "%d / 8" % (idx + 1), font=fl, fill=(255, 255, 255, 150))
    d.text((28, 44), title, font=ft, fill="white")
    rows = (("触发", trig), ("动作", act), ("灯光", light))
    for i, (k, v) in enumerate(rows):
        y = 98 + i * 30
        d.text((28, y), k, font=fl, fill=(224, 138, 60, 255))
        d.text((78, y - 3), v, font=fs, fill=(235, 235, 238, 255))
    return Image.alpha_composite(im, ov).convert("RGB")


keys = list(CAP)
ff = imageio_ffmpeg.get_ffmpeg_exe()
all_w = imageio_ffmpeg.write_frames("/tmp/bl/anim/margin_lamp_behaviours.mp4", (960, 540), fps=24,
                                    quality=8, macro_block_size=8)
all_w.send(None)
sheet_rows = []
for idx, k in enumerate(keys):
    frames = sorted(glob.glob("/tmp/bl/anim/%s/*.png" % k))
    if not frames:
        print("missing", k); continue
    w = imageio_ffmpeg.write_frames("/tmp/bl/anim/%s.mp4" % k, (960, 540), fps=24, quality=8, macro_block_size=8)
    w.send(None)
    for f in frames:
        im = caption(Image.open(f), k, idx, len(frames))
        a = im.tobytes()
        w.send(a); all_w.send(a)
    for _ in range(12):
        all_w.send(a)
    w.close()
    picks = [frames[int(i * (len(frames) - 1) / 3)] for i in range(4)]
    row = Image.new("RGB", (4 * 480, 270))
    for j, p in enumerate(picks):
        row.paste(Image.open(p).resize((480, 270)), (j * 480, 0))
    d = ImageDraw.Draw(row)
    d.rectangle((0, 0, 330, 44), fill=(8, 10, 14))
    d.text((14, 6), "%d  %s · 灯光%s" % (idx + 1, CAP[k][0], CAP[k][3].split("，")[0]), font=fs, fill="white")
    sheet_rows.append(row)
all_w.close()
for half, rows in (("a", sheet_rows[:4]), ("b", sheet_rows[4:])):
    sh = Image.new("RGB", (4 * 480, 270 * len(rows)))
    for i, r in enumerate(rows):
        sh.paste(r, (0, 270 * i))
    sh.save("/tmp/bl/anim/sheet_%s.png" % half)
print("done", len(sheet_rows))
