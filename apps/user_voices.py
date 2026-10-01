"""Voices the user saved from the Voice Cloning tab.

The SDK's ``add_voice`` registers a clone for the running session and its
``save_voices`` rewrites the *built-in* preset file inside the package, which an
upgrade would wipe. So the app keeps its own file, only with the voices the user
added, and loads it on top of the built-ins every time a v3 model is loaded:

    ~/.vieneu/user_voices_v3_turbo.json   (v3 Turbo: speaker_emb + codes)
    ~/.vieneu/user_voices_v3_nano.json    (v3 Nano:  speaker_emb + style)

``VIENEU_HOME`` overrides the folder. Saved voices show up in every preset
dropdown (story, conversation, SRT) and survive restarts.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

import numpy as np

USER_MARK = "_user"          # key set on tts._preset_voices entries that came from here
DEFAULT_DESC = "giọng đã lưu"


def _kind(tts) -> str:
    return "nano" if "nano" in type(tts).__name__.lower() else "turbo"


def voices_home() -> Path:
    return Path(os.environ.get("VIENEU_HOME") or (Path.home() / ".vieneu"))


def user_voices_path(tts) -> Path:
    return voices_home() / f"user_voices_v3_{_kind(tts)}.json"


def supports_saving(tts) -> bool:
    return tts is not None and hasattr(tts, "add_voice") and hasattr(tts, "_preset_voices")


def list_user_voices(tts) -> list[str]:
    if tts is None or not hasattr(tts, "_preset_voices"):
        return []
    return [n for n, v in tts._preset_voices.items() if isinstance(v, dict) and v.get(USER_MARK)]


def _entry_to_json(v: dict) -> dict:
    out: dict[str, Any] = {"description": v.get("description", ""), "gender": v.get("gender", "")}
    emb = v.get("speaker_emb")
    out["speaker_emb"] = [round(float(x), 6) for x in np.asarray(emb, dtype=np.float32).reshape(-1)] if emb is not None else None
    if "style" in v and isinstance(v["style"], np.ndarray):          # Nano: style tokens [50, 256]
        out["style"] = np.asarray(v["style"], dtype=np.float32).round(5).tolist()
    else:                                                            # Turbo: reference codes
        codes = v.get("codes")
        out["codes"] = None if codes is None else np.asarray(codes, dtype=np.int64).tolist()
        if isinstance(v.get("style"), str):
            out["style_name"] = v["style"]
    return out


def _entry_from_json(tts, v: dict) -> Optional[dict]:
    emb = v.get("speaker_emb")
    if emb is None:
        return None
    entry: dict[str, Any] = {
        "description": v.get("description", "") or DEFAULT_DESC,
        "gender": v.get("gender", ""),
        "speaker_emb": np.asarray(emb, dtype=np.float32),
        "podcast": True,
        USER_MARK: True,
    }
    if _kind(tts) == "nano":
        if v.get("style") is None:
            return None
        style = np.asarray(v["style"], dtype=np.float32)
        entry["style"] = style
        entry["codes"] = style
    else:
        codes = v.get("codes")
        entry["codes"] = None if codes is None else np.asarray(codes, dtype=np.int64)
        entry["style"] = v.get("style_name") or getattr(tts, "default_style", "tu_nhien")
    return entry


def load_user_voices(tts) -> list[str]:
    """Add the saved voices to ``tts._preset_voices``; returns the names loaded.
    Never raises — a broken file only means no user voices this session."""
    if not supports_saving(tts):
        return []
    path = user_voices_path(tts)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    names: list[str] = []
    for name, v in (data.get("presets") or {}).items():
        entry = _entry_from_json(tts, v) if isinstance(v, dict) else None
        if entry is None:
            continue
        tts._preset_voices[name] = entry
        names.append(name)
    return names


def _write(tts) -> Path:
    path = user_voices_path(tts)
    path.parent.mkdir(parents=True, exist_ok=True)
    presets = {n: _entry_to_json(tts._preset_voices[n]) for n in list_user_voices(tts)}
    data = {"meta": {"note": f"VieNeu v3 {_kind(tts)} voices saved from the Gradio app"}, "presets": presets}
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)
    return path


def save_user_voice(tts, name: str, ref_audio: str, *, denoise: bool = True, description: str = "") -> str:
    """Enroll ``ref_audio`` as a named preset and persist it. Returns the voice id.
    A name that belongs to a built-in voice is refused; re-saving one of the
    user's own names replaces it."""
    if not supports_saving(tts):
        raise ValueError("Chỉ VieNeu v3 (Turbo / Nano) mới lưu được giọng.")
    name = (name or "").strip()
    if not name:
        raise ValueError("Hãy đặt tên cho giọng.")
    if len(name) > 40:
        raise ValueError("Tên giọng tối đa 40 ký tự.")
    if "—" in name:
        raise ValueError("Tên giọng không được chứa dấu gạch dài (—).")
    if not ref_audio:
        raise ValueError("Hãy tải lên audio mẫu trước.")
    existing = tts._preset_voices.get(name)
    if existing is not None and not existing.get(USER_MARK):
        raise ValueError(f"'{name}' là giọng có sẵn của VieNeu, hãy chọn tên khác.")
    tts.add_voice(name, ref_audio, denoise=denoise, description=(description or "").strip() or DEFAULT_DESC)
    entry = tts._preset_voices[name]
    entry[USER_MARK] = True
    entry["podcast"] = True
    _write(tts)
    return name


def delete_user_voice(tts, name: str) -> None:
    if not supports_saving(tts) or not name:
        return
    entry = tts._preset_voices.get(name)
    if entry is None or not entry.get(USER_MARK):
        raise ValueError("Chỉ xoá được giọng do bạn lưu.")
    tts.remove_voice(name)
    _write(tts)
