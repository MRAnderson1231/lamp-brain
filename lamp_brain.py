"""Webcam -> FastVLM (MLX) -> emotion.txt -> the Blender lamp mirrors your mood.

Run from your own terminal (it needs camera permission):

    uv run lamp_brain.py                      # 4-bit model, webcam
    uv run lamp_brain.py --model models/FastVLM-0.5B-8bit
    uv run lamp_brain.py --image some_face.jpg   # classify one picture and exit

Everything runs on this Mac; no frame leaves the machine.
"""
import argparse
import collections
import statistics
import time
from pathlib import Path

import mlx.core as mx
from PIL import Image
from mlx_vlm import generate, load
from mlx_vlm.prompt_utils import apply_chat_template
from mlx_vlm.utils import load_config

HERE = Path(__file__).resolve().parent
EMOTION_FILE = HERE / "emotion.txt"
LABELS = ["neutral", "happy", "laughing", "sad", "surprised"]

# Keep this short: the 0.5B model stops following long instructions and starts
# explaining the question instead of answering it.
QUESTION = (
    "What is the facial expression of the person? "
    "Answer with one word: neutral, happy, laughing, sad, or surprised."
)

# words the model tends to say instead of a label
SYNONYMS = {
    "laugh": "laughing", "smil": "happy", "joy": "happy", "cheer": "happy",
    "unhappy": "sad", "cry": "sad", "frown": "sad", "upset": "sad", "depress": "sad",
    "shock": "surprised", "surpris": "surprised", "amaz": "surprised", "astonish": "surprised",
    "calm": "neutral", "serious": "neutral", "none": "neutral",
}


def parse_label(text):
    t = text.strip().lower()
    for label in LABELS:
        if t.startswith(label):
            return label
    # "unhappy" contains "happy", so check synonyms before a loose label search
    for stem, label in SYNONYMS.items():
        if stem in t:
            return label
    for label in LABELS:
        if label in t:
            return label
    return None


class EmotionReader:
    def __init__(self, model_path):
        t = time.perf_counter()
        self.model, self.processor = load(model_path)
        self.config = load_config(model_path)
        self.prompt = apply_chat_template(self.processor, self.config, QUESTION, num_images=1)
        self.load_s = time.perf_counter() - t

    def read(self, image):
        """image: PIL.Image. Returns (label or None, raw text, seconds)."""
        t = time.perf_counter()
        out = generate(self.model, self.processor, self.prompt, image=[image],
                       max_tokens=6, temperature=0.0, verbose=False)
        dt = time.perf_counter() - t
        text = getattr(out, "text", out)
        return parse_label(text), text.strip(), dt


class Stabiliser:
    """Majority vote over the last few frames so the lamp doesn't flicker."""

    def __init__(self, window=3):
        self.recent = collections.deque(maxlen=window)
        self.current = "neutral"

    def update(self, label):
        if label is None:
            return self.current
        self.recent.append(label)
        top, count = collections.Counter(self.recent).most_common(1)[0]
        if count * 2 > len(self.recent) and len(self.recent) >= min(2, self.recent.maxlen):
            self.current = top
        return self.current


def write_emotion(label):
    EMOTION_FILE.write_text(label + "\n")


def summary(times, reader, model_path):
    if not times:
        return
    ts = sorted(times)
    p95 = ts[min(len(ts) - 1, int(0.95 * len(ts)))]
    print("\n--- %s ---" % model_path)
    print("frames: %d | load: %.2fs" % (len(ts), reader.load_s))
    print("latency ms  mean %.0f | median %.0f | p95 %.0f  (%.1f readings/s)" % (
        1000 * statistics.mean(ts), 1000 * statistics.median(ts), 1000 * p95, 1 / statistics.mean(ts)))
    print("peak memory: %.2f GB" % (mx.get_peak_memory() / 1e9))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=str(HERE / "models" / "FastVLM-0.5B-4bit"))
    ap.add_argument("--image", help="classify one image file and exit")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--interval", type=float, default=0.15, help="pause between readings, seconds")
    ap.add_argument("--window", type=int, default=3, help="frames in the majority vote")
    ap.add_argument("--show", action="store_true", help="open a preview window with the label")
    args = ap.parse_args()

    print("loading", args.model)
    reader = EmotionReader(args.model)
    print("loaded in %.2fs" % reader.load_s)

    if args.image:
        img = Image.open(args.image).convert("RGB")
        reader.read(img)                       # warm-up
        label, raw, dt = reader.read(img)
        print("raw=%r label=%s %.0f ms" % (raw, label, dt * 1000))
        if label:
            write_emotion(label)
        return

    import cv2
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        raise SystemExit("Could not open the camera. Run this from Terminal and allow camera access "
                         "(System Settings > Privacy & Security > Camera).")
    stab = Stabiliser(args.window)
    times, last_written, warm = [], None, False
    print("watching... Ctrl-C to stop")
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            frame = cv2.flip(frame, 1)
            img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            label, raw, dt = reader.read(img)
            if warm:
                times.append(dt)
            warm = True
            stable = stab.update(label)
            if stable != last_written:
                write_emotion(stable)
                last_written = stable
            print("%-10s -> %-9s | lamp: %-9s | %4.0f ms" % (raw[:10], label or "?", stable, dt * 1000), flush=True)
            if args.show:
                cv2.putText(frame, "%s  %.0f ms" % (stable, dt * 1000), (20, 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 3)
                cv2.imshow("lamp brain", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        write_emotion("neutral")
        summary(times, reader, args.model)


if __name__ == "__main__":
    main()
