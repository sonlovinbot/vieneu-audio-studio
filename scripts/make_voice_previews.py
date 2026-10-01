"""Sinh audio nghe thử cho mọi giọng có sẵn → webapp/static/previews/.

Gọi model trực tiếp (không qua API) nên không ghi vào Lịch sử của app.
Chạy:  uv run python scripts/make_voice_previews.py   (cần ffmpeg để nén MP3)
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unicodedata
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "webapp" / "static" / "previews"
# "VieNeu TTS" viết theo cách đọc tiếng Việt — phonemizer đọc "VieNeu" kiểu tiếng Anh.
TEXT = ("Chào bạn, đây là giọng đọc {name}. Giọng đọc được tạo bằng trí tuệ nhân tạo, "
        "sử dụng mô hình Vi Neu ti ti ét với giấy phép mã nguồn mở. "
        "Các tính năng của phần mềm này được phát triển bởi anh Đặng Hữu Sơn. "
        "Cảm ơn bạn đã sử dụng, chúc bạn có trải nghiệm thật tốt.")


def slug(name: str) -> str:
    s = unicodedata.normalize("NFD", name.replace("Đ", "D").replace("đ", "d"))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return "-".join("".join(c if c.isalnum() else " " for c in s).split())


def main() -> int:
    from vieneu import Vieneu

    only = set(sys.argv[1:])
    OUT.mkdir(parents=True, exist_ok=True)
    tts = Vieneu(mode="v3turbo")
    sr = getattr(tts, "sample_rate", 48000)
    manifest_path = OUT / "voices.json"
    manifest = json.loads(manifest_path.read_text("utf-8")).get("voices", {}) if manifest_path.exists() else {}
    voices = [(label, vid) for label, vid in tts.list_preset_voices()]
    for label, vid in voices:
        if only and vid not in only:
            continue
        t0 = time.time()
        wav = np.clip(np.asarray(tts.infer(TEXT.format(name=vid), voice=vid), dtype=np.float32), -1, 1)
        mp3 = OUT / f"{slug(vid)}.mp3"
        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            with wave.open(tmp.name, "wb") as f:
                f.setnchannels(1)
                f.setsampwidth(2)
                f.setframerate(sr)
                f.writeframes((wav * 32767).astype("<i2").tobytes())
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp.name,
                            "-ac", "1", "-ar", "44100", "-b:a", "64k", str(mp3)], check=True)
        # "⭐ Adam bựa — Nam · Bắc · Phong cách tự nhiên" → giới tính / miền / phong cách
        desc = label.split("—", 1)[1].strip() if "—" in label else ""
        parts = [p.strip() for p in desc.split("·")]
        manifest[vid] = {
            "file": mp3.name, "duration": round(len(wav) / sr, 1),
            "featured": label.startswith("⭐"),
            "gender": parts[0] if len(parts) > 0 else "",
            "region": parts[1] if len(parts) > 1 else "",
            "style": parts[2] if len(parts) > 2 else "",
        }
        print(f"✓ {vid:16s} {len(wav) / sr:5.1f}s  {mp3.stat().st_size // 1024:4d} KB  ({time.time() - t0:.0f}s)", flush=True)
    order = [vid for _, vid in voices]
    manifest = {k: manifest[k] for k in order if k in manifest}
    manifest_path.write_text(json.dumps({"text": TEXT, "voices": manifest}, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"→ {len(manifest)} giọng · {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
