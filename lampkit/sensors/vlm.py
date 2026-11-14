"""FastVLM as a slow, semantic second opinion -> `obs.vlm` every few seconds.

Instead of letting the model write a sentence and parsing it (what lamp_brain.py does), we
score fixed options: one forward pass over the prompt, then compare the log-probabilities of
each option's first token. Deterministic, no parsing, and the softmax over options doubles as
a confidence. If the installed mlx-vlm does not expose what we need, it falls back to
generation + keyword matching.

FastVLM's weights are licensed for research only; swap `vlm.model` for an Apache-licensed
VLM before any product use. Status: not yet exercised on this machine.
"""
from __future__ import annotations

import math
import threading
import time

from ..types import OBS_VLM, Event

QUESTION = ("Look at the student. Which word best describes them right now? "
            "Answer with one word: engaged, confused, frustrated, bored, tired, sad.")
OPTIONS = ["engaged", "confused", "frustrated", "bored", "tired", "sad"]


class VlmSensor:
    def __init__(self, cfg: dict, clock, frame_source):
        from mlx_vlm import load
        from mlx_vlm.prompt_utils import apply_chat_template
        from mlx_vlm.utils import load_config

        c = cfg["vlm"]
        self.c, self.clock, self.frame_source = c, clock, frame_source
        self.model, self.processor = load(c["model"])
        self.config = load_config(c["model"])
        self.prompt = apply_chat_template(self.processor, self.config, QUESTION, num_images=1)
        tok = getattr(self.processor, "tokenizer", self.processor)
        self.option_ids = [tok.encode(" " + o, add_special_tokens=False)[0] for o in OPTIONS]
        self.out: list[Event] = []
        self.lock = threading.Lock()
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _probs_by_scoring(self, image) -> dict[str, float]:
        import mlx.core as mx
        from mlx_vlm.utils import prepare_inputs

        inputs = prepare_inputs(self.processor, [image], [self.prompt])
        logits = self.model(inputs["input_ids"], inputs["pixel_values"], inputs.get("attention_mask"))
        logits = getattr(logits, "logits", logits)
        last = logits[0, -1]
        vals = [float(last[i]) for i in self.option_ids]
        mx.eval(last)
        m = max(vals)
        ex = [math.exp(v - m) for v in vals]
        z = sum(ex)
        return {o: e / z for o, e in zip(OPTIONS, ex)}

    def _probs_by_generation(self, image) -> dict[str, float]:
        from mlx_vlm import generate

        out = generate(self.model, self.processor, self.prompt, image=[image], max_tokens=8, temperature=0.0, verbose=False)
        text = getattr(out, "text", out).lower()
        hits = [o for o in OPTIONS if o in text]
        return {o: (1.0 if hits and o == hits[0] else 0.0) for o in OPTIONS}

    def _loop(self) -> None:
        from PIL import Image

        scorer = self._probs_by_scoring
        while self.running:
            frame = self.frame_source()
            if frame is not None:
                img = Image.fromarray(frame[:, :, ::-1])
                t0 = time.monotonic()
                try:
                    probs = scorer(img)
                except Exception:
                    scorer = self._probs_by_generation
                    probs = scorer(img)
                ev = Event(self.clock.now(), OBS_VLM, {"probs": {k: round(v, 3) for k, v in probs.items()},
                                                       "ms": round((time.monotonic() - t0) * 1000)}, "vlm")
                with self.lock:
                    self.out.append(ev)
            time.sleep(self.c["interval"])

    def poll(self, t: float) -> list[Event]:
        with self.lock:
            out, self.out = self.out, []
        return out

    def close(self):
        self.running = False
        self.thread.join(timeout=2.0)
