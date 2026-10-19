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


LOOP_LIMIT = float(os.environ.get("VIENEU_MULTI_LOOP_LIMIT", "0.24"))   # giọng thật ≤ ~0,21; hỏng ≥ ~0,22–0,9


def loop_score(wav, sr: int) -> float:
    """Độ "lặp" của audio: model đôi khi sinh hỏng thành một âm lặp đi lặp lại ("so we're so we're…").
    Đo độ giống nhau giữa phổ 20 ms và phổ cách nó 0,2–2 giây; giọng nói thật ~0,1–0,2, audio hỏng ≥ 0,6."""
    import numpy as np
    x = np.asarray(wav, dtype=np.float32).squeeze()
    hop = max(1, int(sr * 0.02))
    n = len(x) // hop
    if n < 120:                                   # < 2,4 giây: quá ngắn để đo, coi như ổn
        return 0.0
    fr = x[: n * hop].reshape(n, hop) * np.hanning(hop)
    spec = np.abs(np.fft.rfft(fr, axis=1))
    bands = np.array_split(spec, 32, axis=1)
    f = np.log1p(np.stack([b.mean(1) for b in bands], 1) * 50)
    f = (f - f.mean(0)) / (f.std(0) + 1e-6)
    norms = np.linalg.norm(f, axis=1) + 1e-6
    best = 0.0
    for lag in range(10, min(100, n // 2)):
        c = (f[:-lag] * f[lag:]).sum(1) / (norms[:-lag] * norms[lag:])
        best = max(best, float(c.mean()))
    return best


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
            kw = {"text": req["text"], "language": req.get("language") or None}
            if req.get("ref_audio"):
                kw["ref_audio"] = req["ref_audio"]
                kw["ref_text"] = req.get("ref_text") or None
            elif req.get("instruct"):
                kw["instruct"] = req["instruct"]
            if req.get("speed"):
                kw["speed"] = float(req["speed"])
            steps = int(req.get("num_step") or 32)
            chunk = float(req.get("chunk_seconds") or 0)

            def config(chunk_s: float):
                cfg: dict = {}
                if steps != 32:
                    cfg["num_step"] = steps
                if chunk_s:                      # đoạn dài: sinh từng khúc ngắn rồi ghép (ổn định hơn)
                    cfg["audio_chunk_duration"] = cfg["audio_chunk_threshold"] = chunk_s
                return OmniVoiceGenerationConfig(**cfg) if cfg else None

            # Lần đầu theo yêu cầu; audio bị lặp (hỏng) → khúc ngắn hơn cùng seed → seed khác.
            plan = [(seed, chunk)]
            if chunk:
                plan += [(seed, 4.0), (seed + 1009 if seed else 1009, 5.0)]
            else:
                plan += [(seed + 1009 if seed else 1009, 0.0)]
            t = time.time()
            for tries, (s_, c_) in enumerate(plan):
                if s_:
                    torch.manual_seed(s_)
                    np.random.seed(s_)
                cfg = config(c_)
                if cfg is not None:
                    kw["generation_config"] = cfg
                else:
                    kw.pop("generation_config", None)
                wav = model.generate(**kw)[0]
                if device == "mps":
                    torch.mps.synchronize()
                wav = np.asarray(wav, dtype=np.float32).squeeze()
                score = loop_score(wav, sr)
                if score < LOOP_LIMIT:
                    break
                print(f"loop_score={score:.2f} ≥ {LOOP_LIMIT} (seed {s_}, khúc {c_}s) → tạo lại", file=sys.stderr, flush=True)
            sf.write(req["out"], wav, sr, subtype="PCM_16")
            send({"id": rid, "ok": True, "duration": round(len(wav) / sr, 2), "sample_rate": sr,
                  "seconds": round(time.time() - t, 2), "retries": tries, "loop_score": round(score, 3)})
        except Exception as e:  # noqa: BLE001
            send({"id": rid, "ok": False, "error": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        send({"ready": False, "error": f"{type(e).__name__}: {e}"})
        raise
