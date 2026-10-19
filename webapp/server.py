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
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
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
    from webapp import multilang
except ImportError:  # chạy trực tiếp như script (python webapp/server.py)
    sys.path.insert(0, str(HERE))
    from library import Library  # type: ignore[no-redef]
    import multilang  # type: ignore[no-redef]

HOST = os.environ.get("VIENEU_HOST", "127.0.0.1")
PORT = int(os.environ.get("VIENEU_PORT", BRANDING["app"].get("default_port", 8001)))
VERSION = BRANDING["app"].get("version", "1.0.0")
# Kênh phát hành: "" = bản thường; "global" = bản đa ngôn ngữ phát hành riêng (thông báo cập nhật đọc mục "global" trong news.json)
CHANNEL = (os.environ.get("VIENEU_CHANNEL") or str(BRANDING["app"].get("channel") or "")).strip().lower()
# Bản Free (mặc định) chỉ đọc tiếng Việt; Đa ngôn ngữ (OmniVoice) là tính năng của bản Global (bản đầy đủ).
GLOBAL = CHANNEL == "global"
GLOBAL_ONLY = "Đa ngôn ngữ chỉ có ở bản Global (bản đầy đủ). Bản đang dùng là bản Free — đọc tiếng Việt."
BRANDING["app"]["channel"] = CHANNEL                     # VIENEU_CHANNEL=global (chạy thử) → giao diện theo đúng bản
if GLOBAL and not BRANDING["app"].get("edition"):
    BRANDING["app"]["edition"] = "Global"
if GLOBAL and isinstance(BRANDING.get("global"), dict):   # chữ giới thiệu / ghi nhận model của bản Global
    _g = BRANDING["global"]
    BRANDING["about_note"] = _g.get("about_note") or BRANDING.get("about_note")
    BRANDING["credits"] = _g.get("credits") or BRANDING.get("credits")
    if _g.get("developer_intro"):
        BRANDING["developer"]["intro"] = _g["developer_intro"]

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
    # Đa ngôn ngữ: đặt language (vd "English", "Korean") → lượt này đọc bằng OmniVoice.
    # voice khi đó: nu-tre / nam-tre / … / vn:<giọng VieNeu> (hoặc tên giọng VieNeu như "Trúc Ly").
    language: Optional[str] = None
    accent: Optional[str] = None


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
NEWS_URL = os.environ.get("VIENEU_NEWS_URL", "https://app.danghuuson.com/vieneu-audio-studio/news.json")
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
            "label": str(a.get("label") or "")[:30],
            "campaign": str(a.get("campaign") or "")[:60],
            "apps": [str(x)[:40] for x in (a.get("apps") or [])][:20] if isinstance(a.get("apps"), list) else [],
            "start": str(a.get("start") or "")[:10],
            "end": str(a.get("end") or "")[:10],
            "min_version": str(a.get("min_version") or "")[:20],
            "max_version": str(a.get("max_version") or "")[:20],
            "dismissible": a.get("dismissible", True) is not False,
        })
    # Bản Global chỉ so phiên bản với mục "global" của news.json — không bị nhắc "cập nhật" về bản thường.
    upd = raw.get(CHANNEL) if CHANNEL and isinstance(raw.get(CHANNEL), dict) else ({} if CHANNEL else raw)
    return {
        "latest_version": str(upd.get("latest_version") or "")[:20],
        "release_url": _https(upd.get("release_url")),
        "update_note": str(upd.get("update_note") or "")[:300],
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


def user_changelog(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Bản nhật ký cho người dùng: bỏ mục "app": false, dùng app_title / app_changes nếu có."""
    out = []
    for e in entries:
        ch = e.get("channel")
        if e.get("app") is False or (ch and (ch.replace("free", "") != CHANNEL)):
            continue
        out.append({
            "version": e.get("version", ""),
            "date": e.get("date", ""),
            "title": e.get("app_title") or e.get("title", ""),
            "changes": e.get("app_changes") or e.get("changes", []),
        })
    return out


@app.get("/api/changelog")
def changelog(all: bool = False) -> Dict[str, Any]:
    path = CONFIG_DIR / "changelog.json"
    if not path.exists():
        return {"entries": []}
    try:
        entries = json.loads(path.read_text(encoding="utf-8")).get("entries", [])
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Lỗi đọc changelog: {e}") from e
    return {"entries": entries if all else user_changelog(entries)}


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

    def is_multi(t: ConvTurn) -> bool:
        lang = (t.language or "").strip()
        if lang and lang.lower() not in ("vietnamese", "vi", "tiếng việt"):
            return True
        return multilang.is_multi_voice(t.voice)          # giọng đa ngôn ngữ đọc tiếng Việt (thử nghiệm)

    multi_turns = [t for t in req.turns if t.text.strip() and is_multi(t)]
    if multi_turns and not GLOBAL:
        raise HTTPException(status_code=409, detail="Có lượt thoại đa ngôn ngữ — " + GLOBAL_ONLY)
    if multi_turns and (HOSTED or not multilang.installer.installed()):
        raise HTTPException(status_code=409, detail="Có lượt thoại đa ngôn ngữ nhưng máy chưa cài gói Đa ngôn ngữ "
                            "(trang 🌏 Đa ngôn ngữ → Cài đặt).")
    for t in multi_turns:
        try:
            multilang.build_request(t.text, (t.language or "Vietnamese").strip() or "Vietnamese",
                                    multilang.map_voice(t.voice), t.accent or "")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Lượt \"{t.text[:30]}…\": {e}") from e

    def _run() -> bytes:
        need_vieneu = any(t.text.strip() and not is_multi(t) for t in req.turns)
        tts_model = manager.tts if need_vieneu else None
        sr = getattr(tts_model, "sample_rate", 48000) if tts_model else 24000
        parts: List[np.ndarray] = []
        gap = silence(req.gap_seconds, sr)
        for i, turn in enumerate(req.turns):
            if not turn.text.strip():
                continue
            if is_multi(turn):
                r = multilang.build_request(turn.text, (turn.language or "Vietnamese").strip() or "Vietnamese",
                                            multilang.map_voice(turn.voice), turn.accent or "")
                res = multilang.engine.generate(r)
                wav = multilang.pcm16_to_float(res["wav"])
                src = int(res.get("sample_rate") or 24000)
                if src != sr and len(wav):                # 24 kHz → 48 kHz cho khớp giọng VieNeu
                    n = int(round(len(wav) * sr / src))
                    wav = np.interp(np.linspace(0, len(wav) - 1, n), np.arange(len(wav)), wav).astype(np.float32)
            else:
                wav = tts_model.infer(turn.text, voice=turn.voice, temperature=req.temperature)  # type: ignore[union-attr]
            if parts:
                parts.append(gap)
            parts.append(np.asarray(wav, dtype=np.float32))
        final = np.concatenate(parts) if parts else np.array([], dtype=np.float32)
        return wav_bytes(final, sr)

    try:
        async with INFER_SEM:
            data = await run_in_threadpool(_run)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Lỗi sinh hội thoại: {e}") from e
    turns = []
    for t in req.turns:
        if not t.text.strip():
            continue
        if is_multi(t):
            turns.append({"voice": multilang.map_voice(t.voice), "text": t.text,
                          "language": (t.language or "Vietnamese").strip() or "Vietnamese", "accent": t.accent or ""})
        else:
            turns.append({"voice": t.voice or manager.default_voice(), "text": t.text})
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


# ── Đa ngôn ngữ (OmniVoice, cài thêm khi người dùng bật) ─────────────────
MULTI_MAX_CHARS = int(os.environ.get("VIENEU_MULTI_MAX_CHARS", "2000"))


class MultiTTSRequest(BaseModel):
    text: str
    language: str = "English"
    voice: str = "nu-tre"
    accent: str = ""
    fast: bool = False
    speed: Optional[float] = None


def _no_hosted() -> None:
    if not GLOBAL:
        raise HTTPException(status_code=404, detail=GLOBAL_ONLY)
    if HOSTED:
        raise HTTPException(status_code=403, detail="Chế độ Đa ngôn ngữ chỉ dùng trên bản cài máy tính.")


@app.get("/api/multi/status")
def multi_status(_auth: None = Depends(require_api_key)) -> Dict[str, Any]:
    if not GLOBAL:
        raise HTTPException(status_code=404, detail=GLOBAL_ONLY)
    st = multilang.status()
    st["max_chars"] = MULTI_MAX_CHARS
    st["hosted"] = HOSTED
    return st


@app.post("/api/multi/install")
def multi_install(_auth: None = Depends(require_api_key)) -> Dict[str, Any]:
    _no_hosted()
    hw = multilang.hardware()
    if not hw["supported"]:
        raise HTTPException(status_code=400, detail=hw["reason"])
    multilang.installer.start()
    return multilang.installer.status()


@app.post("/api/multi/uninstall")
def multi_uninstall(_auth: None = Depends(require_api_key)) -> Dict[str, Any]:
    _no_hosted()
    try:
        return multilang.installer.uninstall(remove_model=True)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@app.post("/api/multi/unload")
def multi_unload(_auth: None = Depends(require_api_key)) -> Dict[str, Any]:
    multilang.engine.stop()
    return {"ok": True}


@app.post("/api/multi/clone")
async def multi_clone(
    text: str = Form(...),
    ref_text: str = Form(...),
    ref_audio: UploadFile = File(...),
    language: str = Form("English"),
    fast: bool = Form(False),
    speed: float = Form(1.0),
    _auth: None = Depends(require_api_key),
) -> StreamingResponse:
    """Nhân bản giọng từ file mẫu (3–15 giây) + đúng câu nói trong file mẫu → đọc ngôn ngữ bất kỳ."""
    from fastapi.concurrency import run_in_threadpool
    import tempfile
    _no_hosted()
    if not text.strip():
        raise HTTPException(status_code=400, detail="Thiếu nội dung văn bản.")
    if len(text) > MULTI_MAX_CHARS:
        raise HTTPException(status_code=413, detail=f"Văn bản quá dài. Tối đa {MULTI_MAX_CHARS} ký tự/lần.")
    if not multilang.installer.installed():
        raise HTTPException(status_code=409, detail="Chưa cài gói Đa ngôn ngữ — bấm Cài đặt trước.")
    raw = await ref_audio.read()
    if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File mẫu quá lớn. Tối đa {MAX_UPLOAD_MB}MB.")
    suffix = Path(ref_audio.filename or "ref.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(raw)
        tmp_path = tmp.name
    try:
        try:
            r = multilang.build_request(text, language, "nu-tre", "", fast, speed, ref_audio=tmp_path, ref_text=ref_text)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        log.info("Đa ngôn ngữ · clone · %s · %d ký tự", language, len(text))
        try:
            res = await run_in_threadpool(multilang.engine.generate, r)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Lỗi clone đa ngôn ngữ: {e}") from e
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    data = res["wav"]
    run_id = None
    if LIBRARY_ENABLED:
        label = next((l["label"] for l in multilang.LANGUAGES if l["id"] == language), language)
        try:
            run = await run_in_threadpool(
                library.add_run, "multi", text, f"Clone · {ref_audio.filename or 'audio mẫu'} · {label}",
                "OmniVoice (đa ngôn ngữ)", data, float(res.get("duration") or 0), {"language": language})
            run_id = run["id"]
        except Exception as e:  # noqa: BLE001
            log.warning("Không lưu được lịch sử: %s", e)
    return _audio_response(data, run_id)


@app.post("/api/multi/tts")
async def multi_tts(req: MultiTTSRequest, _auth: None = Depends(require_api_key)) -> StreamingResponse:
    from fastapi.concurrency import run_in_threadpool
    _no_hosted()
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Thiếu nội dung văn bản.")
    if len(req.text) > MULTI_MAX_CHARS:
        raise HTTPException(status_code=413, detail=f"Văn bản quá dài ({len(req.text)} ký tự). "
                            f"Chế độ Đa ngôn ngữ tối đa {MULTI_MAX_CHARS} ký tự/lần.")
    if not multilang.installer.installed():
        raise HTTPException(status_code=409, detail="Chưa cài gói Đa ngôn ngữ — bấm Cài đặt trước.")
    try:
        r = multilang.build_request(req.text, req.language, req.voice, req.accent, req.fast, req.speed)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    log.info("Đa ngôn ngữ · %s · voice=%s · %d ký tự%s", req.language, req.voice, len(req.text), " · nhanh" if req.fast else "")
    try:
        res = await run_in_threadpool(multilang.engine.generate, r)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Lỗi sinh audio đa ngôn ngữ: {e}") from e
    data = res["wav"]
    run_id = None
    if LIBRARY_ENABLED:
        label = next((l["label"] for l in multilang.LANGUAGES if l["id"] == req.language), req.language)
        voice_label = req.voice[3:] if req.voice.startswith("vn:") else \
            next((d["label"] for d in multilang.DESIGNED if d["id"] == req.voice), req.voice)
        try:
            run = await run_in_threadpool(
                library.add_run, "multi", req.text, f"{voice_label} · {label}", "OmniVoice (đa ngôn ngữ)",
                data, float(res.get("duration") or 0), {"language": req.language})
            run_id = run["id"]
        except Exception as e:  # noqa: BLE001
            log.warning("Không lưu được lịch sử: %s", e)
    return _audio_response(data, run_id)


# ── MCP: cho Claude Desktop / ChatGPT Codex gọi tạo giọng (webapp/mcp_server.py) ──
# Trang "MCP & API" sinh cấu hình đúng đường dẫn Python của bản cài này và (khi người dùng bấm)
# tự ghi vào file cấu hình của Claude Desktop / Codex — có sao lưu file cũ trước khi sửa.
MCP_NAME = "ai-audio-studio"


def _local_only(request: Request) -> None:
    """Chỉ trang app trên chính máy này được gọi (chặn trang web lạ gửi lệnh ghi file cấu hình)."""
    if HOSTED:
        raise HTTPException(status_code=404, detail="MCP chỉ có trên bản cài máy tính.")
    host = request.client.host if request.client else ""
    origin = request.headers.get("origin") or ""
    ok_origins = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}
    if host not in ("127.0.0.1", "::1", "localhost") or (origin and origin not in ok_origins):
        raise HTTPException(status_code=403, detail="Chỉ dùng được từ app trên chính máy này.")


def _mcp_spec() -> Dict[str, Any]:
    env: Dict[str, str] = {}
    if PORT != int(BRANDING["app"].get("default_port", 8001)):
        env["VIENEU_URL"] = f"http://127.0.0.1:{PORT}"
    if API_KEY:
        env["VIENEU_API_KEY"] = API_KEY
    return {"command": sys.executable, "args": ["-m", "webapp.mcp_server"], "env": env}


def _claude_cfg() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
    if os.name == "nt":
        return Path(os.environ.get("APPDATA") or (Path.home() / "AppData/Roaming")) / "Claude/claude_desktop_config.json"
    return Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")) / "Claude/claude_desktop_config.json"


def _codex_cfg() -> Path:
    return Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex")) / "config.toml"


def _claude_bin() -> Optional[str]:
    """Đường dẫn lệnh `claude` (Claude Code) — app chạy nền nên PATH có thể thiếu, dò thêm chỗ cài thường gặp."""
    import shutil
    found = shutil.which("claude")
    if found:
        return found
    home = Path.home()
    for c in (home / ".local/bin/claude", home / ".claude/local/claude", Path("/opt/homebrew/bin/claude"),
              Path("/usr/local/bin/claude"), home / "AppData/Roaming/npm/claude.cmd", home / ".npm-global/bin/claude"):
        if c.is_file():
            return str(c)
    return None


def _claude_code_cfg() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home()) / ".claude.json"


def _claude_code_connected(spec: Dict[str, Any]) -> bool:
    try:
        cur = json.loads(_claude_code_cfg().read_text(encoding="utf-8")).get("mcpServers", {}).get(MCP_NAME) or {}
        return cur.get("command") == spec["command"]
    except (OSError, ValueError, AttributeError):
        return False


def _claude_code_run(args: List[str]) -> Any:
    import subprocess
    exe = _claude_bin()
    if not exe:
        raise HTTPException(status_code=409, detail="Chưa thấy Claude Code trên máy (lệnh claude). Cài Claude Code rồi bấm lại.")
    return subprocess.run([exe, *args], capture_output=True, text=True, timeout=60, encoding="utf-8")


def _toml_str(v: str) -> str:
    return json.dumps(v, ensure_ascii=False)      # chuỗi JSON cũng là chuỗi TOML hợp lệ (\\ \" \n)


def _codex_block(spec: Dict[str, Any]) -> str:
    lines = [f"[mcp_servers.{MCP_NAME}]",
             f"command = {_toml_str(spec['command'])}",
             "args = [" + ", ".join(_toml_str(a) for a in spec["args"]) + "]",
             "startup_timeout_sec = 30",
             "tool_timeout_sec = 900          # đọc văn bản dài / lần đầu nạp model có thể lâu"]
    if spec["env"]:
        lines.append("env = { " + ", ".join(f"{k} = {_toml_str(v)}" for k, v in spec["env"].items()) + " }")
    return "\n".join(lines) + "\n"


def _codex_strip(text: str) -> str:
    """Bỏ mục [mcp_servers.ai-audio-studio] (cả bảng con) khỏi config.toml, giữ nguyên phần khác."""
    import re as _re
    head = _re.compile(r"^\s*\[\s*mcp_servers\.(\"?)" + _re.escape(MCP_NAME) + r"\1(\s*\]|\.)")
    out, skip = [], False
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("["):
            skip = bool(head.match(line))
        if not skip:
            out.append(line)
    return "".join(out).rstrip() + ("\n" if out else "")


def _mcp_state() -> Dict[str, Any]:
    spec = _mcp_spec()
    claude_p, codex_p = _claude_cfg(), _codex_cfg()
    claude_on = codex_on = False
    try:
        cur = json.loads(claude_p.read_text(encoding="utf-8")).get("mcpServers", {}).get(MCP_NAME) or {}
        claude_on = cur.get("command") == spec["command"]
    except (OSError, ValueError, AttributeError):
        pass
    try:
        txt = codex_p.read_text(encoding="utf-8")
        codex_on = f"[mcp_servers.{MCP_NAME}]" in txt and _toml_str(spec["command"]) in txt
    except OSError:
        pass
    q = (lambda x: f'"{x}"' if " " in x else x)
    cli_tail = f"-- {q(spec['command'])} " + " ".join(spec["args"])
    env_flags = "".join(f" --env {k}={v}" for k, v in spec["env"].items())
    return {
        "name": MCP_NAME,
        "spec": spec,
        "out_dir": str(Path(os.environ.get("VIENEU_MCP_OUT") or (Path.home() / "Downloads" / "AI-Audio-Studio"))),
        "os": "macos" if sys.platform == "darwin" else "windows" if os.name == "nt" else "linux",
        "claude": {"path": str(claude_p), "installed": claude_p.parent.is_dir(), "connected": claude_on,
                   "snippet": json.dumps({"mcpServers": {MCP_NAME: {k: v for k, v in spec.items() if v != {}}}},
                                         ensure_ascii=False, indent=2)},
        "codex": {"path": str(codex_p), "installed": codex_p.parent.is_dir(), "connected": codex_on,
                  "snippet": _codex_block(spec),
                  "cli": f"codex mcp add {MCP_NAME}{env_flags} {cli_tail}"},
        "claude_code": {"path": str(_claude_code_cfg()), "installed": bool(_claude_bin()),
                        "connected": _claude_code_connected(spec),
                        "cli": f"claude mcp add --scope user {MCP_NAME}{''.join(f' -e {k}={v}' for k, v in spec['env'].items())} {cli_tail}"},
    }


@app.get("/api/mcp")
def mcp_info(request: Request) -> Dict[str, Any]:
    _local_only(request)
    return _mcp_state()


class MCPTarget(BaseModel):
    target: str          # "claude" | "codex"


def _backup(p: Path) -> None:
    if p.is_file():
        p.with_name(p.name + f".bak-{time.strftime('%Y%m%d-%H%M%S')}").write_bytes(p.read_bytes())


@app.post("/api/mcp/connect")
def mcp_connect(req: MCPTarget, request: Request) -> Dict[str, Any]:
    _local_only(request)
    spec = _mcp_spec()
    if req.target == "claude":
        p = _claude_cfg()
        data: Dict[str, Any] = {}
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8") or "{}")
            except ValueError as e:
                raise HTTPException(status_code=409, detail=f"File cấu hình Claude đang lỗi định dạng, không dám sửa: {p}") from e
        _backup(p)
        data.setdefault("mcpServers", {})[MCP_NAME] = {k: v for k, v in spec.items() if v != {}}
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif req.target == "claude_code":
        # Dùng chính lệnh của Claude Code (không tự sửa ~/.claude.json khi Claude Code có thể đang ghi file đó).
        p = _claude_code_cfg()
        _claude_code_run(["mcp", "remove", "--scope", "user", MCP_NAME])
        envs = [x for k, v in spec["env"].items() for x in ("-e", f"{k}={v}")]
        r = _claude_code_run(["mcp", "add", "--scope", "user", *envs, MCP_NAME, "--", spec["command"], *spec["args"]])
        if r.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Lệnh claude mcp add lỗi: {(r.stderr or r.stdout).strip()[-300:]}")
    elif req.target == "codex":
        p = _codex_cfg()
        old = p.read_text(encoding="utf-8") if p.is_file() else ""
        _backup(p)
        body = _codex_strip(old)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text((body + "\n" if body.strip() else "") + _codex_block(spec), encoding="utf-8")
    else:
        raise HTTPException(status_code=400, detail="target phải là claude, claude_code hoặc codex")
    log.info("MCP · đã kết nối %s (%s)", req.target, p)
    return _mcp_state()


@app.post("/api/mcp/disconnect")
def mcp_disconnect(req: MCPTarget, request: Request) -> Dict[str, Any]:
    _local_only(request)
    if req.target == "claude":
        p = _claude_cfg()
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8") or "{}")
            except ValueError as e:
                raise HTTPException(status_code=409, detail=f"File cấu hình Claude đang lỗi định dạng: {p}") from e
            if MCP_NAME in data.get("mcpServers", {}):
                _backup(p)
                del data["mcpServers"][MCP_NAME]
                p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif req.target == "claude_code":
        _claude_code_run(["mcp", "remove", "--scope", "user", MCP_NAME])
    elif req.target == "codex":
        p = _codex_cfg()
        if p.is_file():
            old = p.read_text(encoding="utf-8")
            new = _codex_strip(old)
            if new != old:
                _backup(p)
                p.write_text(new, encoding="utf-8")
    else:
        raise HTTPException(status_code=400, detail="target phải là claude, claude_code hoặc codex")
    return _mcp_state()


@app.post("/api/mcp/test")
def mcp_test(request: Request) -> Dict[str, Any]:
    """Chạy thử đúng lệnh MCP mà Claude/Codex sẽ chạy: bắt tay + lấy danh sách công cụ + kiểm tra app."""
    import subprocess
    _local_only(request)
    spec = _mcp_spec()
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "app-test", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "app_status", "arguments": {}}},
    ]
    try:
        r = subprocess.run([spec["command"], *spec["args"]], input="\n".join(json.dumps(m) for m in msgs) + "\n",
                           capture_output=True, text=True, timeout=60, env={**os.environ, **spec["env"]},
                           encoding="utf-8")
        res = {}
        for line in r.stdout.splitlines():
            try:
                d = json.loads(line)
                res[d.get("id")] = d.get("result") or {}
            except ValueError:
                pass
        tools = [t["name"] for t in res.get(2, {}).get("tools", [])]
        status = (res.get(3, {}).get("content") or [{}])[0].get("text", "")
        if not tools:
            return {"ok": False, "error": (r.stderr or "MCP không trả lời")[-600:]}
        return {"ok": True, "tools": tools, "status": status}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


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
