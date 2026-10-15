"""Tiến trình chạy model đa ngôn ngữ OmniVoice (k2-fsa/OmniVoice).

Chạy bằng Python của môi trường riêng (~/.vieneu/engines/omnivoice/.venv) — app chính
không cần PyTorch. Giao tiếp với server qua stdin/stdout, mỗi dòng một JSON:

  vào:  {"id": "...", "text": "...", "language": "English", "instruct": "female, young adult",
         "seed": 7, "ref_audio": "/path.mp3", "ref_text": "...", "num_step": 32, "speed": 1.0,
         "out": "/tmp/x.wav"}
  ra:   {"id": "...", "ok": true, "duration": 9.2, "sample_rate": 24000, "seconds": 10.1}
        {"id": "...", "ok": false, "error": "..."}
  dòng đầu tiên ra: {"ready": true, "device": "mps"} sau khi nạp model xong.

Mọi log của thư viện đi ra stderr để stdout chỉ còn JSON.
"""
from __future__ import annotations

import json
import os
import sys
import time

_out = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8", buffering=1)
os.dup2(sys.stderr.fileno(), sys.stdout.fileno())   # print() của thư viện → stderr


def send(obj: dict) -> None:
    _out.write(json.dumps(obj, ensure_ascii=False) + "\n")
    _out.flush()


def pick_device() -> str:
    import torch
    want = os.environ.get("VIENEU_MULTI_DEVICE", "auto")
    if want != "auto":
        return want
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def main() -> None:
    import numpy as np
    import soundfile as sf
    import torch
    from omnivoice import OmniVoice
    from omnivoice.models.omnivoice import OmniVoiceGenerationConfig

    device = pick_device()
    t = time.time()
    model = OmniVoice.from_pretrained(
        os.environ.get("VIENEU_MULTI_MODEL", "k2-fsa/OmniVoice"),
        device_map=device,
        dtype=torch.float16 if device != "cpu" else torch.float32,
    )
    sr = int(getattr(model, "sampling_rate", 24000) or 24000)
    send({"ready": True, "device": device, "load_seconds": round(time.time() - t, 1), "sample_rate": sr})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        rid = req.get("id")
        try:
            seed = int(req.get("seed") or 0)
            if seed:
                torch.manual_seed(seed)
                np.random.seed(seed)
            kw = {"text": req["text"], "language": req.get("language") or None}
            if req.get("ref_audio"):
                kw["ref_audio"] = req["ref_audio"]
                kw["ref_text"] = req.get("ref_text") or None
            elif req.get("instruct"):
                kw["instruct"] = req["instruct"]
            if req.get("speed"):
                kw["speed"] = float(req["speed"])
            steps = int(req.get("num_step") or 32)
            if steps != 32:
                kw["generation_config"] = OmniVoiceGenerationConfig(num_step=steps)
            t = time.time()
            wav = model.generate(**kw)[0]
            if device == "mps":
                torch.mps.synchronize()
            wav = np.asarray(wav, dtype=np.float32).squeeze()
            sf.write(req["out"], wav, sr, subtype="PCM_16")
            send({"id": rid, "ok": True, "duration": round(len(wav) / sr, 2),
                  "sample_rate": sr, "seconds": round(time.time() - t, 2)})
        except Exception as e:  # noqa: BLE001
            send({"id": rid, "ok": False, "error": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        send({"ready": False, "error": f"{type(e).__name__}: {e}"})
        raise
