"""SRT → speech for the Gradio app: read a Vietnamese subtitle file, speak every
cue with one preset voice, lay the clips on the subtitle timeline (or back to
back), and write one WAV/MP3.

Deliberately small: no translation, no video, no burned-in subtitles — the
desktop app does those. This is "I already have the Vietnamese script with
timestamps, give me the audio".

Timeline rule: each cue starts at its SRT start time. A clip that runs past
the next cue's start does not overlap it — the next cue is pushed later by the
overrun (and the status says how many cues moved and by how much). Nothing is
time-stretched, so the voice always sounds natural; a script written for
faster speech simply ends a little later.
"""
from __future__ import annotations

import os
import re
import tempfile
import time
from dataclasses import dataclass
from typing import Callable, Iterator, Optional

import numpy as np
import soundfile as sf

_TIME = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})")
_TAG = re.compile(r"<[^>]+>|\{[^}]+\}")


@dataclass
class Cue:
    index: int
    start_ms: int
    end_ms: int
    text: str


def _ms(m: re.Match) -> int:
    h, mi, s, frac = m.groups()
    frac = (frac + "000")[:3]
    return ((int(h) * 60 + int(mi)) * 60 + int(s)) * 1000 + int(frac)


def parse_srt(text: str) -> list[Cue]:
    """Tolerant .srt parser: blank-line separated blocks, optional index line,
    `HH:MM:SS,mmm --> HH:MM:SS,mmm`, then one or more text lines. HTML/ASS
    tags are stripped; empty cues are dropped; cues come back sorted by start."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")
    cues: list[Cue] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        ti = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if ti is None:
            continue
        times = _TIME.findall(lines[ti])
        if len(times) < 2:
            continue
        a, b = (_ms(_TIME.search(lines[ti])), None)
        # second timestamp: search after the arrow
        after = lines[ti].split("-->", 1)[1]
        mb = _TIME.search(after)
        if not mb:
            continue
        b = _ms(mb)
        body = " ".join(_TAG.sub("", l) for l in lines[ti + 1:]).strip()
        body = re.sub(r"\s+", " ", body)
        if not body:
            continue
        cues.append(Cue(index=len(cues) + 1, start_ms=a, end_ms=max(b, a + 100), text=body))
    cues.sort(key=lambda c: c.start_ms)
    for i, c in enumerate(cues):
        c.index = i + 1
    return cues


def _to_mono_f32(w) -> np.ndarray:
    w = np.asarray(w, dtype=np.float32)
    if w.ndim > 1:
        w = w.mean(axis=-1) if w.shape[-1] <= 8 else w.mean(axis=0)
    return w


def lay_on_timeline(clips: list[np.ndarray], cues: list[Cue], sr: int) -> tuple[np.ndarray, int, float]:
    """Place clips at their cue starts; a clip that overruns pushes the next
    cue later instead of overlapping it. Returns (track, cues_pushed, max_shift_s)."""
    starts: list[int] = []
    pushed, max_shift = 0, 0.0
    cursor = 0
    for c, w in zip(cues, clips):
        want = int(c.start_ms * sr / 1000)
        at = max(want, cursor)
        if at > want:
            pushed += 1
            max_shift = max(max_shift, (at - want) / sr)
        starts.append(at)
        cursor = at + len(w)
    total = max((s + len(w) for s, w in zip(starts, clips)), default=0)
    out = np.zeros(total + sr // 2, dtype=np.float32)
    for s, w in zip(starts, clips):
        out[s:s + len(w)] += w
    return out, pushed, max_shift


def concatenate(clips: list[np.ndarray], sr: int, gap_s: float = 0.5) -> np.ndarray:
    gap = np.zeros(int(gap_s * sr), dtype=np.float32)
    parts: list[np.ndarray] = []
    for i, w in enumerate(clips):
        if i:
            parts.append(gap)
        parts.append(w)
    return np.concatenate(parts) if parts else np.zeros(sr, dtype=np.float32)


def write_audio(track: np.ndarray, sr: int, fmt: str) -> tuple[str, str]:
    """Write to a temp file; MP3 when libsndfile can, else WAV. Returns (path, note)."""
    peak = float(np.abs(track).max()) if track.size else 0.0
    if peak > 0.98:
        track = track * (0.98 / peak)
    if fmt.lower() == "mp3" and "MP3" in sf.available_formats():
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tmp.close()
        try:
            sf.write(tmp.name, track, sr, format="MP3")
            return tmp.name, ""
        except Exception as e:  # noqa: BLE001 — fall back to WAV below
            note = f" (MP3 không ghi được: {e}; đã xuất WAV)"
            os.unlink(tmp.name)
    else:
        note = " (MP3 không khả dụng trên máy này; đã xuất WAV)" if fmt.lower() == "mp3" else ""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    tmp.close()
    sf.write(tmp.name, track, sr)
    return tmp.name, note


def srt_to_speech(
    tts,
    srt_path: Optional[str],
    voice_id: Optional[str],
    keep_timing: bool,
    fmt: str,
    stop_requested: Callable[[], bool],
    batch_size: int = 32,
) -> Iterator[tuple[Optional[str], str]]:
    """Gradio generator: yields (audio_path | None, status). Progress lines use the
    app's "Đang xử lý batch i/n" form so the time estimate box works."""
    if tts is None:
        yield None, "⚠️ Vui lòng tải model trước!"
        return
    if not hasattr(tts, "infer_batch") or not hasattr(tts, "get_preset_voice"):
        yield None, "⚠️ SRT → giọng nói chỉ hỗ trợ VieNeu v3 (Turbo hoặc Nano)."
        return
    if not srt_path:
        yield None, "⚠️ Hãy tải lên file .srt."
        return
    try:
        raw = open(srt_path, "r", encoding="utf-8-sig", errors="replace").read()
    except Exception as e:  # noqa: BLE001
        yield None, f"❌ Không đọc được file: {e}"
        return
    cues = parse_srt(raw)
    if not cues:
        yield None, "❌ File không có câu thoại nào (định dạng .srt: số thứ tự, mốc thời gian, lời)."
        return
    if not voice_id:
        voice_id = getattr(tts, "_default_voice", None)
    try:
        tts.get_preset_voice(voice_id)
    except Exception as e:  # noqa: BLE001
        yield None, f"❌ Giọng không hợp lệ: {e}"
        return

    sr = int(getattr(tts, "sample_rate", 48000))
    n = len(cues)
    # Only the PyTorch/CUDA engine batches; on CPU (ONNX) infer_batch would run
    # the cues one after another anyway, so go cue by cue there and report
    # per cue — a 32-cue "batch" on CPU is minutes of silence in the status.
    dev = getattr(getattr(tts, "engine", None), "device", None)
    is_cuda = dev is not None and getattr(dev, "type", None) == "cuda"
    if not is_cuda:
        batch_size = 1
    batches = [cues[i:i + batch_size] for i in range(0, n, batch_size)]
    unit = "batch" if is_cuda else "đoạn"
    clips: list[np.ndarray] = []
    t0 = time.time()
    where = f"GPU, gộp {batch_size} câu/lượt" if is_cuda else "CPU, từng câu"
    yield None, f"📄 {n} câu thoại, giọng {voice_id} ({where}). Đang xử lý {unit} 1/{len(batches)}..."
    for bi, batch in enumerate(batches, 1):
        if stop_requested():
            yield None, "⏹️ Đã dừng."
            return
        try:
            wavs = tts.infer_batch([c.text for c in batch], voice=voice_id)
        except Exception as e:  # noqa: BLE001
            yield None, f"❌ Lỗi tổng hợp ở {unit} {bi}: {e}"
            return
        clips.extend(_to_mono_f32(w) for w in wavs)
        done = min(bi * batch_size, n)
        if bi < len(batches):
            yield None, f"🔊 Xong {done}/{n} câu ({time.time() - t0:.0f}s). Đang xử lý {unit} {bi + 1}/{len(batches)}..."

    if keep_timing:
        track, pushed, max_shift = lay_on_timeline(clips, cues, sr)
        timing_note = (
            f" {pushed} câu phải lùi lại (tối đa {max_shift:.1f}s) vì giọng đọc dài hơn khung thời gian."
            if pushed else " Mọi câu đều khớp mốc thời gian."
        )
    else:
        track = concatenate(clips, sr)
        timing_note = " Các câu nối tiếp nhau, cách 0,5 giây."
    path, note = write_audio(track, sr, fmt)
    dur = len(track) / sr
    yield path, (
        f"✅ Xong {n} câu trong {time.time() - t0:.1f}s — audio {dur / 60:.0f} phút {dur % 60:.0f} giây."
        + timing_note + note
    )
