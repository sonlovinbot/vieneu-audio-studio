"""AI Audio Studio — FastAPI backend.

A clean, single-file REST API that wraps the VieNeu-TTS SDK and serves the
static neo-brutalist web UI. Defaults to v3 Turbo (CPU/ONNX, torch-free); the
heavier v2/GPU/LoRA paths stay available as an advanced "load" option.

Run:
    uv run vieneu-studio          # or: python -m webapp.server
Then open http://127.0.0.1:8001
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import platform
import sys
import threading
import time
import wave
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import uvicorn
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ──────────────────────────────────────────────────────────────────────────
# Paths & config
# ──────────────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"
CONFIG_DIR = HERE / "config"
BRANDING = json.loads((CONFIG_DIR / "branding.json").read_text(encoding="utf-8"))

try:
    from webapp.library import Library
except ImportError:  # chạy trực tiếp như script (python webapp/server.py)
    sys.path.insert(0, str(HERE))
    from library import Library  # type: ignore[no-redef]

HOST = os.environ.get("VIENEU_HOST", "127.0.0.1")
PORT = int(os.environ.get("VIENEU_PORT", BRANDING["app"].get("default_port", 8001)))
VERSION = BRANDING["app"].get("version", "1.0.0")

# ── Bảo mật & giới hạn (đặt qua biến môi trường / HF Secrets) ──────────────
# VIENEU_API_KEY   : khóa cho các endpoint tạo giọng (tts/clone/conversation/stream).
#                    Để TRỐNG => mở tự do (hợp khi chạy local). Đặt => bắt buộc X-API-Key.
# VIENEU_ADMIN_KEY : khóa cho endpoint nguy hiểm (load/logs). Để TRỐNG => KHÓA hẳn.
API_KEY = os.environ.get("VIENEU_API_KEY", "").strip()
ADMIN_KEY = os.environ.get("VIENEU_ADMIN_KEY", "").strip()
MAX_TEXT_CHARS = int(os.environ.get("VIENEU_MAX_TEXT_CHARS", "5000"))
MAX_TURNS = int(os.environ.get("VIENEU_MAX_TURNS", "50"))
MAX_UPLOAD_MB = float(os.environ.get("VIENEU_MAX_UPLOAD_MB", "5"))
MAX_CONCURRENCY = max(1, int(os.environ.get("VIENEU_MAX_CONCURRENCY", "2")))
# VIENEU_LIBRARY   : "off" tắt Lịch sử + Giọng của tôi (nên tắt trên Space công khai,
#                    vì mọi người dùng chung một thư viện).
LIBRARY_ENABLED = os.environ.get("VIENEU_LIBRARY", "on").strip().lower() not in ("0", "off", "false", "no")
# Bản web công khai (HF Space tự đặt SPACE_ID): onboarding hướng dẫn tải về máy
# thay vì đo cấu hình server.
HOSTED = bool(os.environ.get("SPACE_ID")) or os.environ.get("VIENEU_HOSTED", "").strip().lower() in ("1", "on", "true", "yes")
# Bộ cài .zip cho nút "Tải về" (tạo bằng build-installers.sh).
DOWNLOAD_DIR = Path(os.environ.get("VIENEU_DOWNLOAD_DIR") or (HERE.parent / "dist"))
INSTALLERS = {
    "macos": "AI-Audio-Studio-macOS.zip",
    "windows": "AI-Audio-Studio-Windows.zip",
    "linux": "AI-Audio-Studio-Linux.zip",
}

# ──────────────────────────────────────────────────────────────────────────
# In-memory log capture — keeps the last N records so the UI can show logs
# without touching the filesystem.
# ──────────────────────────────────────────────────────────────────────────
LOG_BUFFER: deque = deque(maxlen=1000)


class DequeLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            LOG_BUFFER.append({
                "time": time.strftime("%H:%M:%S", time.localtime(record.created)),
                "level": record.levelname,
                "name": record.name,
                "msg": record.getMessage(),
            })
        except Exception:  # noqa: BLE001 — logging must never raise
            pass


def setup_logging() -> None:
    # Attach ONLY to root: child loggers (vieneu.*, httpx, huggingface_hub, our
    # own vieneu.studio) propagate up to root, so one handler captures everything
    # exactly once — no duplicates. (uvicorn reconfigures its own loggers after
    # this, so attaching to them here wouldn't survive anyway.)
    handler = DequeLogHandler()
    handler.setLevel(logging.INFO)
    root = logging.getLogger()
    if root.level == 0 or root.level > logging.INFO:
        root.setLevel(logging.INFO)
    if not any(isinstance(h, DequeLogHandler) for h in root.handlers):
        root.addHandler(handler)


setup_logging()
log = logging.getLogger("vieneu.studio")

# ──────────────────────────────────────────────────────────────────────────
# Model manager — lazy singleton so the server boots instantly and only
# downloads/loads the model on first synthesis request.
# ──────────────────────────────────────────────────────────────────────────
class ModelManager:
    def __init__(self) -> None:
        self._tts = None
        self._lock = threading.Lock()
        self.mode = "v3turbo"
        self.backbone_repo = "pnnbao-ump/VieNeu-TTS-v3-Turbo"
        self.device = "auto"
        self.loading = False
        self.error: Optional[str] = None

    @property
    def loaded(self) -> bool:
        return self._tts is not None

    def status(self) -> Dict[str, Any]:
        return {
            "loaded": self.loaded,
            "loading": self.loading,
            "mode": self.mode,
            "backbone_repo": self.backbone_repo,
            "device": self.device,
            "error": self.error,
            "sample_rate": getattr(self._tts, "sample_rate", 48000) if self.loaded else None,
        }

    def load(self, mode: str = "v3turbo", backbone_repo: Optional[str] = None,
             device: str = "auto", hf_token: Optional[str] = None,
             **kwargs: Any) -> None:
        """(Re)load the underlying Vieneu model. Thread-safe."""
        from vieneu import Vieneu

        # Normalize empty token → None (avoids the "Bearer " illegal-header bug).
        hf_token = (hf_token or "").strip() or None
        with self._lock:
            self.loading = True
            self.error = None
            try:
                self._tts = None
                opts: Dict[str, Any] = {"mode": mode, "device": device}
                if backbone_repo:
                    opts["backbone_repo"] = backbone_repo
                if hf_token:
                    opts["hf_token"] = hf_token
                opts.update(kwargs)
                self._tts = Vieneu(**opts)
                self._load_user_voices()
                self.mode = mode
                self.backbone_repo = backbone_repo or self.backbone_repo
                self.device = device
            except Exception as e:  # noqa: BLE001
                self.error = str(e)
                raise
            finally:
                self.loading = False

    def _load_user_voices(self) -> None:
        """Layer the voices saved in "Giọng của tôi" on top of the built-ins."""
        if not LIBRARY_ENABLED:
            return
        try:
            from apps import user_voices as uv
            names = uv.load_user_voices(self._tts)
            if names:
                log.info("Nạp %d giọng đã lưu: %s", len(names), ", ".join(names))
        except Exception as e:  # noqa: BLE001 — a bad store must not block the model
            log.warning("Không nạp được giọng đã lưu: %s", e)

    def user_voice_names(self) -> List[str]:
        try:
            from apps import user_voices as uv
            return uv.list_user_voices(self._tts)
        except Exception:  # noqa: BLE001
            return []

    def default_voice(self) -> str:
        return getattr(self._tts, "_default_voice", None) or "mặc định"

    def model_label(self) -> str:
        return f"{self.mode} · {self.backbone_repo}"

    def ensure_loaded(self) -> None:
        if not self.loaded:
            self.load(self.mode, self.backbone_repo, self.device)

    @property
    def tts(self):
        self.ensure_loaded()
        return self._tts

    def voices(self) -> List[Dict[str, str]]:
        tts = self.tts
        if not hasattr(tts, "list_preset_voices"):
            return []
        mine = set(self.user_voice_names())
        items = [{"id": vid, "label": label, "custom": vid in mine}
                 for label, vid in tts.list_preset_voices()]
        items.sort(key=lambda v: not v["custom"])  # stable: user voices first
        return items


manager = ModelManager()

# Lịch sử + metadata "Giọng của tôi" — nằm cạnh kho giọng của apps.user_voices
# ($VIENEU_HOME, mặc định ~/.vieneu), ngoài package nên upgrade không xóa mất.
library = Library(
    Path(os.environ.get("VIENEU_HOME") or (Path.home() / ".vieneu")) / "studio",
    max_runs=int(os.environ.get("VIENEU_HISTORY_MAX", "50")),
)


# ──────────────────────────────────────────────────────────────────────────
# Audio helpers
# ──────────────────────────────────────────────────────────────────────────
def _to_pcm16(wav: np.ndarray) -> bytes:
    wav = np.asarray(wav, dtype=np.float32)
    wav = np.clip(wav, -1.0, 1.0)
    return (wav * 32767.0).astype("<i2").tobytes()


def wav_bytes(wav: np.ndarray, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes(_to_pcm16(wav))
    return buf.getvalue()


def silence(seconds: float, sample_rate: int) -> np.ndarray:
    return np.zeros(int(seconds * sample_rate), dtype=np.float32)


# ──────────────────────────────────────────────────────────────────────────
# FastAPI app
# ──────────────────────────────────────────────────────────────────────────
app = FastAPI(title="AI Audio Studio", version="1.0.0")

# Hàng đợi chống vỡ CPU: chỉ cho N request sinh audio chạy song song, dư thì xếp hàng.
INFER_SEM = asyncio.Semaphore(MAX_CONCURRENCY)


def require_api_key(x_api_key: Optional[str] = Header(None)) -> None:
    """Bắt buộc X-API-Key cho endpoint tạo giọng — nếu VIENEU_API_KEY được đặt."""
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Sai hoặc thiếu API key (header X-API-Key).")


def require_admin_key(x_admin_key: Optional[str] = Header(None)) -> None:
    """Bảo vệ endpoint nguy hiểm (load/logs). Không đặt VIENEU_ADMIN_KEY => khóa hẳn."""
    if not ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Chức năng admin đã bị khóa trên bản công khai.")
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Sai hoặc thiếu Admin key (header X-Admin-Key).")


def require_api_key_q(key: Optional[str] = None, x_api_key: Optional[str] = Header(None)) -> None:
    """Như require_api_key nhưng nhận cả ?key= — thẻ <audio> không gửi được header."""
    if API_KEY and (key or x_api_key) != API_KEY:
        raise HTTPException(status_code=401, detail="Sai hoặc thiếu API key (?key= hoặc X-API-Key).")


def require_library() -> None:
    if not LIBRARY_ENABLED:
        raise HTTPException(status_code=404, detail="Thư viện (lịch sử / giọng của tôi) đã tắt trên server này.")


async def _record(kind: str, text: str, voice: str, data: bytes,
                  extra: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Lưu một lượt vào lịch sử. Lỗi ghi đĩa chỉ log cảnh báo — không làm hỏng audio."""
    if not LIBRARY_ENABLED:
        return None
    from fastapi.concurrency import run_in_threadpool
    sr = getattr(manager._tts, "sample_rate", 48000) or 48000
    duration = max(0, len(data) - 44) / 2 / sr   # PCM16 mono, header 44 byte
    try:
        run = await run_in_threadpool(
            library.add_run, kind, text, voice, manager.model_label(), data, duration, extra)
        return run["id"]
    except Exception as e:  # noqa: BLE001
        log.warning("Không lưu được lịch sử: %s", e)
        return None


def _audio_response(data: bytes, run_id: Optional[str]) -> StreamingResponse:
    headers = {"X-History-Id": run_id} if run_id else None
    return StreamingResponse(io.BytesIO(data), media_type="audio/wav", headers=headers)


def _check_text_len(text: str) -> None:
    if len(text) > MAX_TEXT_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"Văn bản quá dài ({len(text)} ký tự). Tối đa {MAX_TEXT_CHARS} ký tự.",
        )


class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = None
    temperature: float = 0.8
    top_k: int = 25


class ConvTurn(BaseModel):
    voice: Optional[str] = None
    text: str


class ConversationRequest(BaseModel):
    turns: List[ConvTurn]
    gap_seconds: float = 0.4
    temperature: float = 0.8


class LoadRequest(BaseModel):
    mode: str = "v3turbo"
    backbone_repo: Optional[str] = None
    device: str = "auto"
    hf_token: Optional[str] = None


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "status": manager.status(), "auth_required": bool(API_KEY)}


@app.get("/api/info")
def info() -> Dict[str, Any]:
    # auth_required: cho frontend biết có cần X-API-Key không (KHÔNG lộ key thật).
    return {"branding": BRANDING, "status": manager.status(), "auth_required": bool(API_KEY),
            "library": LIBRARY_ENABLED, "history_max": library.max_runs, "hosted": HOSTED,
            "max_text_chars": MAX_TEXT_CHARS}


# ── Onboarding: cấu hình máy, tải model lần đầu, bộ cài ────────────────────
def _run(cmd: List[str]) -> str:
    import subprocess
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=3).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def _ram_bytes() -> Optional[int]:
    try:
        import psutil  # type: ignore[import-not-found]
        return int(psutil.virtual_memory().total)
    except Exception:  # noqa: BLE001
        pass
    sysname = platform.system()
    try:
        if sysname == "Darwin":
            return int(_run(["sysctl", "-n", "hw.memsize"]))
        if sysname == "Windows":
            import ctypes

            class MEMSTAT(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            st = MEMSTAT()
            st.dwLength = ctypes.sizeof(MEMSTAT)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))  # type: ignore[attr-defined]
            return int(st.ullTotalPhys)
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except Exception:  # noqa: BLE001
        return None


def system_info() -> Dict[str, Any]:
    """Thông tin thô về máy đang chạy server — frontend tự chấm đạt/không đạt."""
    import shutil
    sysname = platform.system()
    arch = platform.machine().lower()
    os_name, os_version, cpu = sysname, platform.release(), platform.processor()
    if sysname == "Darwin":
        os_name, os_version = "macOS", platform.mac_ver()[0]
        cpu = _run(["sysctl", "-n", "machdep.cpu.brand_string"]) or cpu
        # Python x86 chạy qua Rosetta trên chip Apple → vẫn là Apple Silicon.
        if _run(["sysctl", "-n", "sysctl.proc_translated"]) == "1":
            arch = "arm64"
    elif sysname == "Windows":
        build = platform.version().split(".")[-1]
        os_name = "Windows 11" if build.isdigit() and int(build) >= 22000 else f"Windows {platform.release()}"
        os_version = platform.version()
    elif sysname == "Linux":
        try:
            for line in Path("/etc/os-release").read_text().splitlines():
                if line.startswith("PRETTY_NAME="):
                    os_version = line.split("=", 1)[1].strip('"')
        except Exception:  # noqa: BLE001
            pass
        try:
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                if line.startswith("model name"):
                    cpu = line.split(":", 1)[1].strip()
                    break
        except Exception:  # noqa: BLE001
            pass
    try:
        disk_free = shutil.disk_usage(Path.home()).free
    except Exception:  # noqa: BLE001
        disk_free = None
    return {
        "platform": {"Darwin": "macos", "Windows": "windows"}.get(sysname, "linux"),
        "os": os_name, "os_version": os_version, "arch": arch, "cpu": cpu,
        "cores": os.cpu_count(), "ram_bytes": _ram_bytes(), "disk_free_bytes": disk_free,
        "python": platform.python_version(),
    }


# ── Tin tức từ xa: banner quảng cáo, thông báo, báo có bản mới ──────────────
# Chủ phần mềm sửa docs/news.json trên GitHub Pages → mọi máy đã cài tự nhận,
# không cần phát hành lại. Chỉ nhận chữ + link https (không HTML/script); mất
# mạng thì dùng bản đã lưu. Tắt hẳn: VIENEU_NEWS=off.
NEWS_URL = os.environ.get("VIENEU_NEWS_URL", "https://sonlovinbot.github.io/vieneu-audio-studio/news.json")
NEWS_ENABLED = os.environ.get("VIENEU_NEWS", "on").strip().lower() not in ("0", "off", "false", "no")
NEWS_TTL = 3 * 3600
_NEWS: Dict[str, Any] = {"at": 0.0, "data": None}
_NEWS_LOCK = threading.Lock()


def _https(url: Any) -> str:
    url = str(url or "").strip()
    return url if url.startswith("https://") and len(url) < 500 else ""


def _clean_news(raw: Any) -> Dict[str, Any]:
    """Giữ đúng các trường biết trước, cắt độ dài, bỏ link không phải https."""
    if not isinstance(raw, dict):
        return {}
    items = []
    for a in (raw.get("announcements") or [])[:10]:
        if not isinstance(a, dict) or not a.get("id"):
            continue
        items.append({
            "id": str(a["id"])[:60],
            "placement": "sidebar" if a.get("placement") == "sidebar" else "top",
            "tone": a.get("tone") if a.get("tone") in ("info", "warning", "promo") else "info",
            "title": str(a.get("title") or "")[:120],
            "text": str(a.get("text") or "")[:300],
            "image": _https(a.get("image")),
            "link": _https(a.get("link")),
            "cta": str(a.get("cta") or "")[:40],
            "start": str(a.get("start") or "")[:10],
            "end": str(a.get("end") or "")[:10],
            "min_version": str(a.get("min_version") or "")[:20],
            "max_version": str(a.get("max_version") or "")[:20],
            "dismissible": a.get("dismissible", True) is not False,
        })
    return {
        "latest_version": str(raw.get("latest_version") or "")[:20],
        "release_url": _https(raw.get("release_url")),
        "update_note": str(raw.get("update_note") or "")[:300],
        "announcements": items,
    }


def _news_cache_file() -> Path:
    return Path(os.environ.get("VIENEU_HOME") or (Path.home() / ".vieneu")) / "studio" / "news-cache.json"


def _fetch_news() -> Optional[Dict[str, Any]]:
    import urllib.request
    try:
        req = urllib.request.Request(NEWS_URL, headers={"User-Agent": f"AI-Audio-Studio/{VERSION}"})
        with urllib.request.urlopen(req, timeout=4) as r:
            data = _clean_news(json.loads(r.read(200_000).decode("utf-8")))
        try:
            f = _news_cache_file()
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        return data
    except Exception as e:  # noqa: BLE001 — offline / lỗi mạng: dùng bản đã lưu
        log.info("Không tải được tin tức (%s) — dùng bản đã lưu.", e)
        try:
            return _clean_news(json.loads(_news_cache_file().read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            return None


@app.get("/api/news")
def news() -> Dict[str, Any]:
    if not NEWS_ENABLED:
        return {"enabled": False, "version": VERSION}
    with _NEWS_LOCK:
        if _NEWS["data"] is None or time.time() - _NEWS["at"] > NEWS_TTL:
            fresh = _fetch_news()
            if fresh is not None:
                _NEWS["data"] = fresh
            _NEWS["at"] = time.time()
    return {"enabled": True, "version": VERSION, **(_NEWS["data"] or {})}


@app.get("/api/system")
def system() -> Dict[str, Any]:
    if HOSTED:  # máy server không phải máy người dùng — để trình duyệt tự đo
        return {"hosted": True}
    return {"hosted": False, **system_info()}


_WARM_LOCK = threading.Lock()


def _warm() -> None:
    try:
        manager.ensure_loaded()
        log.info("Onboarding: model đã sẵn sàng (%s)", manager.backbone_repo)
    except Exception as e:  # noqa: BLE001 — lỗi đã ghi vào manager.error
        log.error("Onboarding: tải model lỗi: %s", e)
    finally:
        _WARM_LOCK.release()


@app.post("/api/warmup")
def warmup() -> Dict[str, Any]:
    """Tải model mặc định ở nền (lần đầu sẽ download) — gọi lại an toàn."""
    if not manager.loaded and _WARM_LOCK.acquire(blocking=False):
        manager.loading = True
        manager.error = None
        threading.Thread(target=_warm, daemon=True).start()
    return {"ok": True, "status": manager.status()}


@app.get("/api/downloads")
def downloads() -> Dict[str, Any]:
    links = BRANDING.get("downloads") or {}
    out = {}
    for plat, fname in INSTALLERS.items():
        path = DOWNLOAD_DIR / fname
        if links.get(plat):
            out[plat] = {"available": True, "url": links[plat], "size": None}
        elif path.is_file():
            out[plat] = {"available": True, "url": f"/api/download/{plat}", "size": path.stat().st_size}
        else:
            out[plat] = {"available": False, "url": None, "size": None}
    return {"installers": out}


@app.get("/api/download/{plat}")
def download(plat: str) -> FileResponse:
    fname = INSTALLERS.get(plat)
    if not fname or not (DOWNLOAD_DIR / fname).is_file():
        raise HTTPException(status_code=404, detail="Chưa có bộ cài cho hệ điều hành này.")
    return FileResponse(DOWNLOAD_DIR / fname, media_type="application/zip", filename=fname)


@app.get("/api/version")
def version() -> Dict[str, Any]:
    try:
        from importlib.metadata import version as _pkgver
        vieneu_ver = _pkgver("vieneu")
    except Exception:  # noqa: BLE001
        vieneu_ver = "unknown"
    return {
        "app": BRANDING["app"]["name"],
        "edition": BRANDING["app"].get("edition", ""),
        "version": VERSION,
        "vieneu_sdk": vieneu_ver,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "status": manager.status(),
    }


@app.get("/api/changelog")
def changelog() -> Dict[str, Any]:
    path = CONFIG_DIR / "changelog.json"
    if not path.exists():
        return {"entries": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Lỗi đọc changelog: {e}") from e


@app.get("/api/logs")
def logs(lines: int = 200, level: Optional[str] = None,
         _admin: None = Depends(require_admin_key)) -> Dict[str, Any]:
    items = list(LOG_BUFFER)
    if level and level.upper() != "ALL":
        want = level.upper()
        items = [x for x in items if x["level"] == want]
    return {"lines": items[-max(1, min(lines, 1000)):], "total": len(LOG_BUFFER)}


@app.get("/api/voices")
async def list_voices() -> Dict[str, Any]:
    from fastapi.concurrency import run_in_threadpool
    try:
        voices = await run_in_threadpool(manager.voices)
        return {"voices": voices}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Lỗi tải giọng: {e}") from e


@app.post("/api/load")
async def load_model(req: LoadRequest,
                     _admin: None = Depends(require_admin_key)) -> Dict[str, Any]:
    from fastapi.concurrency import run_in_threadpool
    log.info("Tải model · mode=%s · repo=%s · device=%s",
             req.mode, req.backbone_repo or "(mặc định)", req.device)
    try:
        await run_in_threadpool(
            manager.load, req.mode, req.backbone_repo, req.device, req.hf_token
        )
        log.info("Đã tải model xong: %s", manager.backbone_repo)
        return {"ok": True, "status": manager.status()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Lỗi tải model: {e}") from e


@app.post("/api/tts")
async def tts(req: TTSRequest, _auth: None = Depends(require_api_key)) -> StreamingResponse:
    from fastapi.concurrency import run_in_threadpool
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Thiếu nội dung văn bản.")
    _check_text_len(req.text)

    log.info("TTS · voice=%s · %d ký tự",
             req.voice or "default", len(req.text))

    def _run() -> bytes:
        tts_model = manager.tts
        wav = tts_model.infer(
            req.text, voice=req.voice,
            temperature=req.temperature, top_k=req.top_k,
        )
        return wav_bytes(wav, getattr(tts_model, "sample_rate", 48000))

    try:
        async with INFER_SEM:
            data = await run_in_threadpool(_run)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Lỗi sinh audio: {e}") from e
    run_id = await _record("tts", req.text, req.voice or manager.default_voice(), data)
    return _audio_response(data, run_id)


@app.post("/api/clone")
async def clone(
    text: str = Form(...),
    ref_audio: UploadFile = File(...),
    temperature: float = Form(0.8),
    _auth: None = Depends(require_api_key),
) -> StreamingResponse:
    from fastapi.concurrency import run_in_threadpool
    import tempfile

    if not text.strip():
        raise HTTPException(status_code=400, detail="Thiếu nội dung văn bản.")
    _check_text_len(text)

    suffix = Path(ref_audio.filename or "ref.wav").suffix or ".wav"
    raw = await ref_audio.read()
    if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File mẫu quá lớn ({len(raw) // (1024 * 1024)}MB). Tối đa {MAX_UPLOAD_MB}MB.",
        )

    def _run() -> bytes:
        tts_model = manager.tts
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(raw)
            tmp_path = tmp.name
        try:
            wav = tts_model.infer(
                text, ref_audio=tmp_path, temperature=temperature
            )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return wav_bytes(wav, getattr(tts_model, "sample_rate", 48000))

    try:
        async with INFER_SEM:
            data = await run_in_threadpool(_run)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Lỗi clone giọng: {e}") from e
    run_id = await _record("clone", text, f"Clone · {ref_audio.filename or 'audio mẫu'}", data)
    return _audio_response(data, run_id)


@app.post("/api/conversation")
async def conversation(req: ConversationRequest,
                       _auth: None = Depends(require_api_key)) -> StreamingResponse:
    from fastapi.concurrency import run_in_threadpool
    if not req.turns:
        raise HTTPException(status_code=400, detail="Kịch bản hội thoại trống.")
    if len(req.turns) > MAX_TURNS:
        raise HTTPException(status_code=413, detail=f"Quá nhiều lượt thoại. Tối đa {MAX_TURNS} lượt.")
    _check_text_len("".join(t.text for t in req.turns))

    def _run() -> bytes:
        tts_model = manager.tts
        sr = getattr(tts_model, "sample_rate", 48000)
        parts: List[np.ndarray] = []
        gap = silence(req.gap_seconds, sr)
        for i, turn in enumerate(req.turns):
            if not turn.text.strip():
                continue
            wav = tts_model.infer(turn.text, voice=turn.voice, temperature=req.temperature)
            if i > 0:
                parts.append(gap)
            parts.append(np.asarray(wav, dtype=np.float32))
        final = np.concatenate(parts) if parts else np.array([], dtype=np.float32)
        return wav_bytes(final, sr)

    try:
        async with INFER_SEM:
            data = await run_in_threadpool(_run)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Lỗi sinh hội thoại: {e}") from e
    turns = [{"voice": t.voice or manager.default_voice(), "text": t.text}
             for t in req.turns if t.text.strip()]
    voices = ", ".join(dict.fromkeys(t["voice"] for t in turns))
    text = "\n".join(f"{t['voice']}: {t['text']}" for t in turns)
    run_id = await _record("conversation", text, voices, data, {"turns": turns})
    return _audio_response(data, run_id)


@app.get("/api/stream")
async def stream(text: str, voice: Optional[str] = None,
                 key: Optional[str] = None, x_api_key: Optional[str] = Header(None)):
    """Streaming WAV — first sound arrives as soon as the first chunk is ready."""
    # GET stream không gửi được header tùy ý từ thẻ <audio>, nên chấp nhận cả ?key=
    if API_KEY and (key or x_api_key) != API_KEY:
        raise HTTPException(status_code=401, detail="Sai hoặc thiếu API key (?key= hoặc X-API-Key).")
    if not text.strip():
        raise HTTPException(status_code=400, detail="Thiếu nội dung văn bản.")
    _check_text_len(text)
    tts_model = manager.tts
    sr = getattr(tts_model, "sample_rate", 48000)

    def gen():
        header = io.BytesIO()
        with wave.open(header, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.setnframes(0xFFFFFFF)
        yield header.getvalue()
        try:
            for chunk in tts_model.infer_stream(text, voice=voice):
                yield _to_pcm16(chunk)
        except Exception as e:  # noqa: BLE001
            print(f"[stream] error: {e}")

    return StreamingResponse(gen(), media_type="audio/wav")


# ──────────────────────────────────────────────────────────────────────────
# Thư viện: Giọng của tôi (voice đã clone thành công) + Lịch sử
# ──────────────────────────────────────────────────────────────────────────
VOICE_NAME_MAX = 40


def _check_voice_name(name: str) -> str:
    """Same rules as apps.user_voices.save_user_voice, reused for rename."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Hãy đặt tên cho giọng.")
    if len(name) > VOICE_NAME_MAX:
        raise ValueError(f"Tên giọng tối đa {VOICE_NAME_MAX} ký tự.")
    if "—" in name:
        raise ValueError("Tên giọng không được chứa dấu gạch dài (—).")
    return name


class RenameVoiceRequest(BaseModel):
    old: str
    new: str


@app.get("/api/voices/custom")
async def custom_voices(_lib: None = Depends(require_library),
                        _auth: None = Depends(require_api_key)) -> Dict[str, Any]:
    from fastapi.concurrency import run_in_threadpool

    def _run() -> List[Dict[str, Any]]:
        tts = manager.tts
        presets = getattr(tts, "_preset_voices", {}) or {}
        meta = library.voice_meta()
        out = []
        for n in manager.user_voice_names():
            m = meta.get(n) or {}
            out.append({
                "name": n,
                "description": (presets.get(n) or {}).get("description", ""),
                "created": m.get("created"),
                "model": m.get("model"),
                "has_clip": library.voice_clip_path(n) is not None,
            })
        out.sort(key=lambda v: -(v["created"] or 0))   # newest first; ones saved elsewhere last
        return out

    try:
        return {"voices": await run_in_threadpool(_run)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Lỗi tải giọng của tôi: {e}") from e


@app.post("/api/voices/custom")
async def save_custom_voice(
    name: str = Form(...),
    ref_audio: UploadFile = File(...),
    _lib: None = Depends(require_library),
    _auth: None = Depends(require_api_key),
) -> Dict[str, Any]:
    """Lưu audio mẫu (đã clone thành công) thành một giọng dùng lại được."""
    from fastapi.concurrency import run_in_threadpool
    import tempfile

    raw = await ref_audio.read()
    if not raw:
        raise HTTPException(status_code=400, detail="File audio mẫu trống.")
    if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File mẫu quá lớn. Tối đa {MAX_UPLOAD_MB}MB.")
    suffix = Path(ref_audio.filename or "ref.wav").suffix or ".wav"

    def _run() -> str:
        from apps import user_voices as uv
        tts = manager.tts
        if not uv.supports_saving(tts):
            raise ValueError("Model hiện tại không lưu được giọng — hãy dùng VieNeu v3 Turbo.")
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(raw)
            tmp_path = tmp.name
        try:
            saved = uv.save_user_voice(tts, name, tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        try:
            library.put_voice_meta(saved, raw, suffix, manager.model_label())
        except Exception as e:  # noqa: BLE001 — the voice itself is saved; only the preview is lost
            log.warning("Đã lưu giọng '%s' nhưng không lưu được audio mẫu: %s", saved, e)
        return saved

    try:
        async with INFER_SEM:
            saved = await run_in_threadpool(_run)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Lỗi lưu giọng: {e}") from e
    log.info("Đã lưu giọng của tôi: %s", saved)
    return {"ok": True, "name": saved}


@app.patch("/api/voices/custom")
async def rename_custom_voice(req: RenameVoiceRequest,
                              _lib: None = Depends(require_library),
                              _auth: None = Depends(require_api_key)) -> Dict[str, Any]:
    from fastapi.concurrency import run_in_threadpool

    def _run() -> str:
        from apps import user_voices as uv
        tts = manager.tts
        new = _check_voice_name(req.new)
        presets = getattr(tts, "_preset_voices", None)
        entry = presets.get(req.old) if presets is not None else None
        if entry is None or not entry.get(uv.USER_MARK):
            raise ValueError("Chỉ đổi tên được giọng do bạn lưu.")
        if new == req.old:
            return new
        if new in presets:
            raise ValueError(f"Đã có giọng tên '{new}', hãy chọn tên khác.")
        presets[new] = entry          # same embedding + codes, new key
        tts.remove_voice(req.old)
        uv._write(tts)                # persist the store (no public rename in apps.user_voices)
        library.rename_voice_meta(req.old, new)
        return new

    try:
        new = await run_in_threadpool(_run)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    log.info("Đổi tên giọng: %s → %s", req.old, new)
    return {"ok": True, "name": new}


@app.delete("/api/voices/custom")
async def delete_custom_voice(name: str,
                              _lib: None = Depends(require_library),
                              _auth: None = Depends(require_api_key)) -> Dict[str, Any]:
    from fastapi.concurrency import run_in_threadpool

    def _run() -> None:
        from apps import user_voices as uv
        uv.delete_user_voice(manager.tts, name)
        library.drop_voice_meta(name)

    try:
        await run_in_threadpool(_run)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    log.info("Đã xóa giọng của tôi: %s", name)
    return {"ok": True}


@app.get("/api/voices/custom/clip")
def custom_voice_clip(name: str,
                      _lib: None = Depends(require_library),
                      _auth: None = Depends(require_api_key_q)) -> FileResponse:
    path = library.voice_clip_path(name)
    if path is None:
        raise HTTPException(status_code=404, detail="Giọng này không có audio mẫu.")
    return FileResponse(path)


@app.get("/api/history")
def history(_lib: None = Depends(require_library),
            _auth: None = Depends(require_api_key)) -> Dict[str, Any]:
    return {"runs": library.list_runs(), "max": library.max_runs}


@app.get("/api/history/{run_id}/audio")
def history_audio(run_id: str, download: bool = False,
                  _lib: None = Depends(require_library),
                  _auth: None = Depends(require_api_key_q)) -> FileResponse:
    path = library.run_audio_path(run_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy audio.")
    return FileResponse(path, media_type="audio/wav",
                        filename=f"vieneu-{run_id}.wav" if download else None)


@app.delete("/api/history/{run_id}")
def delete_history(run_id: str,
                   _lib: None = Depends(require_library),
                   _auth: None = Depends(require_api_key)) -> Dict[str, Any]:
    if not library.delete_run(run_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy lượt này.")
    return {"ok": True}


@app.delete("/api/history")
def clear_history(_lib: None = Depends(require_library),
                  _auth: None = Depends(require_api_key)) -> Dict[str, Any]:
    return {"ok": True, "deleted": library.clear_runs()}


# ── Static frontend (mounted last so /api/* wins) ──────────────────────────
@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


def main() -> None:
    name = BRANDING["app"]["name"]
    print(f"🦜 {name} — http://{HOST}:{PORT}")
    print("   (model sẽ tải khi có yêu cầu sinh audio đầu tiên)")
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
