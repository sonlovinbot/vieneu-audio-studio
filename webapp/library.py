"""Studio library: run history + extra metadata for the user's saved voices.

The voices themselves (speaker embedding + reference codes) are persisted by the
upstream ``apps.user_voices`` store, so they load instantly and are shared with
the Gradio app. This module only keeps what the Studio UI adds on top: the
reference clip for preview, when / with which model a voice was made, and the
history of generated audio (capped, oldest pruned first).

    $VIENEU_HOME/studio/          (default ~/.vieneu/studio)
      voices.json                 name -> {id, created, model, clip}
      voice_clips/<id><ext>
      history.json                runs, newest first
      history/<id>.wav

Everything lives outside the package, so ``uv sync`` / upgrades never touch it.
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("vieneu.studio.library")

DEFAULT_MAX_RUNS = 50
CLIP_EXTS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm", ".aac"}
_ID_RE = re.compile(r"^[0-9a-f]{12}$")


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _valid_id(run_id: str) -> bool:
    return bool(_ID_RE.match(run_id or ""))


class Library:
    def __init__(self, root: Path, max_runs: int = DEFAULT_MAX_RUNS) -> None:
        self.root = Path(root)
        self.max_runs = max(1, int(max_runs))
        self._lock = threading.RLock()

    # ── paths ──────────────────────────────────────────────────────────────
    @property
    def _voices_file(self) -> Path:
        return self.root / "voices.json"

    @property
    def _clips_dir(self) -> Path:
        return self.root / "voice_clips"

    @property
    def _history_file(self) -> Path:
        return self.root / "history.json"

    @property
    def _history_dir(self) -> Path:
        return self.root / "history"

    # ── JSON I/O ───────────────────────────────────────────────────────────
    def _read(self, path: Path, default: Any) -> Any:
        """Read JSON; a corrupt file is moved aside (not deleted) and treated as empty."""
        if not path.is_file():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            aside = path.with_name(f"{path.name}.corrupt-{int(time.time())}")
            try:
                path.replace(aside)
            except OSError:
                pass
            log.warning("File thư viện hỏng (%s), đã chuyển sang %s: %s", path.name, aside.name, e)
            return default

    def _write(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # ── saved-voice metadata ───────────────────────────────────────────────
    def voice_meta(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            data = self._read(self._voices_file, {})
            return data if isinstance(data, dict) else {}

    def put_voice_meta(self, name: str, clip: bytes, suffix: str, model: str) -> Dict[str, Any]:
        """Store the reference clip + metadata for ``name`` (replacing any previous one)."""
        suffix = suffix.lower() if suffix and suffix.lower() in CLIP_EXTS else ".wav"
        with self._lock:
            meta = self.voice_meta()
            self._remove_clip(meta.get(name))
            vid = _new_id()
            self._clips_dir.mkdir(parents=True, exist_ok=True)
            (self._clips_dir / f"{vid}{suffix}").write_bytes(clip)
            entry = {"id": vid, "created": time.time(), "model": model, "clip": f"{vid}{suffix}"}
            meta[name] = entry
            self._write(self._voices_file, meta)
            return dict(entry)

    def rename_voice_meta(self, old: str, new: str) -> None:
        with self._lock:
            meta = self.voice_meta()
            if old in meta:
                meta[new] = meta.pop(old)
                self._write(self._voices_file, meta)

    def drop_voice_meta(self, name: str) -> None:
        with self._lock:
            meta = self.voice_meta()
            entry = meta.pop(name, None)
            if entry is not None:
                self._remove_clip(entry)
                self._write(self._voices_file, meta)

    def voice_clip_path(self, name: str) -> Optional[Path]:
        entry = self.voice_meta().get(name) or {}
        clip = entry.get("clip")
        if not clip or Path(clip).name != clip:   # never follow a path out of the folder
            return None
        p = self._clips_dir / clip
        return p if p.is_file() else None

    def _remove_clip(self, entry: Optional[Dict[str, Any]]) -> None:
        clip = (entry or {}).get("clip")
        if clip and Path(clip).name == clip:
            try:
                (self._clips_dir / clip).unlink()
            except OSError:
                pass

    # ── history ────────────────────────────────────────────────────────────
    def list_runs(self) -> List[Dict[str, Any]]:
        with self._lock:
            data = self._read(self._history_file, [])
            return data if isinstance(data, list) else []

    def add_run(self, kind: str, text: str, voice: str, model: str, audio: bytes,
                duration: float, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        with self._lock:
            run_id = _new_id()
            self._history_dir.mkdir(parents=True, exist_ok=True)
            (self._history_dir / f"{run_id}.wav").write_bytes(audio)
            run: Dict[str, Any] = {
                "id": run_id, "kind": kind, "created": time.time(), "text": text,
                "voice": voice, "model": model, "duration": round(float(duration), 2),
                "bytes": len(audio),
            }
            if extra:
                run.update(extra)
            runs = [run] + self.list_runs()
            for old in runs[self.max_runs:]:
                self._remove_run_audio(old.get("id", ""))
            self._write(self._history_file, runs[: self.max_runs])
            return dict(run)

    def run_audio_path(self, run_id: str) -> Optional[Path]:
        if not _valid_id(run_id):
            return None
        p = self._history_dir / f"{run_id}.wav"
        return p if p.is_file() else None

    def delete_run(self, run_id: str) -> bool:
        if not _valid_id(run_id):
            return False
        with self._lock:
            runs = self.list_runs()
            keep = [r for r in runs if r.get("id") != run_id]
            if len(keep) == len(runs):
                return False
            self._remove_run_audio(run_id)
            self._write(self._history_file, keep)
            return True

    def clear_runs(self) -> int:
        with self._lock:
            runs = self.list_runs()
            for r in runs:
                self._remove_run_audio(r.get("id", ""))
            self._write(self._history_file, [])
            return len(runs)

    def _remove_run_audio(self, run_id: str) -> None:
        if _valid_id(run_id):
            try:
                (self._history_dir / f"{run_id}.wav").unlink()
            except OSError:
                pass
