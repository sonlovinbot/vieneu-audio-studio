"""Chế độ Đa ngôn ngữ — model OmniVoice (k2-fsa/OmniVoice) chạy trong môi trường riêng.

App chính không cần PyTorch. Gói đa ngôn ngữ (~4 GB: PyTorch + OmniVoice + model) chỉ cài khi
người dùng bật, nằm ở $VIENEU_HOME/engines/omnivoice/ (mặc định ~/.vieneu), gỡ được bất cứ lúc nào.
Model chạy ở một tiến trình con (webapp/engines/omnivoice_worker.py), tự tắt khi lâu không dùng.

Tiếng Việt có ở chế độ này dưới dạng THỬ NGHIỆM (cùng model, không tốn thêm dung lượng) — VieNeu-TTS vẫn là
mặc định cho tiếng Việt vì nhanh hơn ~4 lần và đọc số / ngày tháng đúng hơn.
"""
from __future__ import annotations

import atexit
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("vieneu-studio")

HERE = Path(__file__).resolve().parent
WORKER = HERE / "engines" / "omnivoice_worker.py"
HOME = Path(os.environ.get("VIENEU_HOME") or (Path.home() / ".vieneu"))
ENGINE_DIR = HOME / "engines" / "omnivoice"
VENV = ENGINE_DIR / ".venv"
MARKER = ENGINE_DIR / "installed.json"
MODEL_REPO = os.environ.get("VIENEU_MULTI_MODEL", "k2-fsa/OmniVoice")
MODEL_BYTES = 3_000_000_000            # dung lượng tải model (đo thật 03/10/2026)
TORCH_VER = "2.8.0"
OMNIVOICE_VER = "0.2.1"
IDLE_UNLOAD_S = int(os.environ.get("VIENEU_MULTI_IDLE", "600"))
ATTRIBUTION = ("Chế độ Đa ngôn ngữ dùng model OmniVoice (k2-fsa, Apache-2.0). Built with Higgs Materials licensed "
               "from Boson AI USA, Inc., Copyright Boson AI USA, Inc., All Rights Reserved and Meta Llama 3 licensed "
               "under the Meta Llama 3 Community License, Copyright Meta Platforms, Inc., All Rights Reserved.")

# Ngôn ngữ đưa lên giao diện (tên model hiểu → nhãn). Model hỗ trợ 600+ thứ tiếng; đây là nhóm
# có nhiều dữ liệu huấn luyện nhất + các nước gần Việt Nam. Tiếng Việt cố ý không có (dùng VieNeu).
LANGUAGES: List[Dict[str, str]] = [
    {"id": "English", "label": "🇺🇸 Tiếng Anh · English"},
    {"id": "Korean", "label": "🇰🇷 Tiếng Hàn · 한국어"},
    {"id": "Japanese", "label": "🇯🇵 Tiếng Nhật · 日本語"},
    {"id": "Chinese", "label": "🇨🇳 Tiếng Trung · 中文"},
    {"id": "Cantonese", "label": "🇭🇰 Tiếng Quảng Đông · 粵語"},
    {"id": "Filipino", "label": "🇵🇭 Filipino · Tagalog (ít dữ liệu)"},
    {"id": "Thai", "label": "🇹🇭 Tiếng Thái · ไทย"},
    {"id": "Indonesian", "label": "🇮🇩 Tiếng Indonesia"},
    {"id": "Malay", "label": "🇲🇾 Tiếng Mã Lai · Melayu"},
    {"id": "French", "label": "🇫🇷 Tiếng Pháp · Français"},
    {"id": "Spanish", "label": "🇪🇸 Tiếng Tây Ban Nha · Español"},
    {"id": "German", "label": "🇩🇪 Tiếng Đức · Deutsch"},
    {"id": "Russian", "label": "🇷🇺 Tiếng Nga · Русский"},
    {"id": "Portuguese", "label": "🇵🇹 Tiếng Bồ Đào Nha · Português"},
    {"id": "Italian", "label": "🇮🇹 Tiếng Ý · Italiano"},
    {"id": "Hindi", "label": "🇮🇳 Tiếng Hindi · हिन्दी"},
    {"id": "Standard Arabic", "label": "🇸🇦 Tiếng Ả Rập · العربية"},
    {"id": "Vietnamese", "label": "🇻🇳 Tiếng Việt · thử nghiệm (chậm hơn VieNeu)", "experimental": True},
]
LANG_IDS = {x["id"] for x in LANGUAGES}

# Giọng có sẵn (mô tả bằng thuộc tính — model không có giọng đặt tên). Seed cố định → mỗi lần
# sinh cùng một giọng.
DESIGNED: List[Dict[str, Any]] = [
    {"id": "nu-tre", "label": "Nữ · trẻ", "instruct": "female, young adult", "seed": 11},
    {"id": "nu-trung-nien", "label": "Nữ · trung niên, trầm", "instruct": "female, middle-aged, low pitch", "seed": 23},
    {"id": "nu-teen", "label": "Nữ · thiếu niên, giọng cao", "instruct": "female, teenager, high pitch", "seed": 31},
    {"id": "nam-tre", "label": "Nam · trẻ", "instruct": "male, young adult", "seed": 41},
    {"id": "nam-trung-nien", "label": "Nam · trung niên, trầm", "instruct": "male, middle-aged, low pitch", "seed": 53},
    {"id": "nam-lon-tuoi", "label": "Nam · lớn tuổi", "instruct": "male, elderly", "seed": 67},
]
ACCENTS = [  # chỉ dùng được với tiếng Anh
    {"id": "", "label": "Tự động"},
    {"id": "american accent", "label": "Mỹ"},
    {"id": "british accent", "label": "Anh"},
    {"id": "australian accent", "label": "Úc"},
    {"id": "canadian accent", "label": "Canada"},
    {"id": "indian accent", "label": "Ấn Độ"},
]
ACCENT_IDS = {a["id"] for a in ACCENTS}


def _vieneu_voices() -> List[Dict[str, Any]]:
    """25 giọng VieNeu có file nghe thử + câu đọc chính xác → nhân bản sang ngôn ngữ khác."""
    path = HERE / "static" / "previews" / "voices.json"
    try:
        data = json.loads(path.read_text("utf-8"))
    except Exception:  # noqa: BLE001
        return []
    out = []
    for name, v in (data.get("voices") or {}).items():
        f = HERE / "static" / "previews" / v.get("file", "")
        if f.is_file():
            out.append({"id": "vn:" + name, "label": f"{name} ({v.get('gender', '')}, {v.get('region', '')})",
                        "file": str(f), "ref_text": data.get("text", "").replace("{name}", name)})
    return out


def voices() -> Dict[str, Any]:
    return {
        "designed": [{k: d[k] for k in ("id", "label")} for d in DESIGNED],
        "vieneu": [{k: v[k] for k in ("id", "label")} for v in _vieneu_voices()],
        "accents": ACCENTS,
    }


# ──────────────────────────────────────────────────────────────────────────
# Phần cứng
# ──────────────────────────────────────────────────────────────────────────
def _has_nvidia() -> bool:
    if not shutil.which("nvidia-smi"):
        return False
    try:
        return subprocess.run(["nvidia-smi", "-L"], capture_output=True, timeout=10).returncode == 0
    except Exception:  # noqa: BLE001
        return False


def hardware() -> Dict[str, Any]:
    sysname, mach = platform.system(), platform.machine().lower()
    apple = sysname == "Darwin" and mach in ("arm64", "aarch64")
    nvidia = sysname != "Darwin" and _has_nvidia()
    if apple:
        accel, speed = "mps", "Mac chip Apple: ~1 giây máy chạy cho 1 giây audio (giọng có sẵn)."
    elif nvidia:
        accel, speed = "cuda", "Card NVIDIA: nhanh, thường nhanh hơn đọc thật."
    else:
        accel, speed = "cpu", ("Máy không có card đồ hoạ rời: chạy bằng CPU, CHẬM (~3 giây máy chạy cho 1 giây audio, "
                               "nhân bản giọng ~8–10 giây). Vẫn dùng được cho đoạn ngắn.")
    supported = not (sysname == "Darwin" and not apple)   # Mac Intel: PyTorch 2.8 không còn bản cho x86 Mac
    return {"accel": accel, "speed_note": speed, "supported": supported,
            "reason": "" if supported else "Mac chip Intel chưa chạy được gói đa ngôn ngữ (PyTorch không còn bản cho Mac Intel)."}


# ──────────────────────────────────────────────────────────────────────────
# Cài đặt / gỡ
# ──────────────────────────────────────────────────────────────────────────
def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _hf_cache() -> Path:
    if os.environ.get("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    return Path(os.environ.get("HF_HOME") or (Path.home() / ".cache" / "huggingface")) / "hub"


def _model_dir() -> Path:
    return _hf_cache() / ("models--" + MODEL_REPO.replace("/", "--"))


def _real_files(p: Path) -> Dict[str, int]:
    """File thật trong thư mục, đi theo symlink (Hugging Face bản mới để file lớn ở kho dùng chung
    hub/blobs/xx/… và chỉ đặt symlink trong thư mục model) — đếm mỗi file một lần."""
    out: Dict[str, int] = {}
    if p.exists():
        for f in p.rglob("*"):
            try:
                if f.is_file():
                    rp = os.path.realpath(f)
                    out.setdefault(rp, os.path.getsize(rp))
            except OSError:
                pass
    return out


def _dir_bytes(p: Path) -> int:
    return sum(_real_files(p).values())


def _find_uv() -> Optional[str]:
    cands = [shutil.which("uv"), str(Path.home() / ".local" / "bin" / ("uv.exe" if os.name == "nt" else "uv")),
             str(Path.home() / ".cargo" / "bin" / ("uv.exe" if os.name == "nt" else "uv"))]
    return next((c for c in cands if c and Path(c).is_file()), None)


class Installer:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.state = "idle"          # idle | running | error | done
        self.step = ""
        self.progress = 0.0          # 0..1 cho cả quá trình
        self.error = ""
        self.lines: List[str] = []
        self.thread: Optional[threading.Thread] = None

    def installed(self) -> bool:
        return MARKER.exists() and venv_python().exists()

    def status(self) -> Dict[str, Any]:
        return {"state": self.state, "step": self.step, "progress": round(self.progress, 3),
                "error": self.error, "log": self.lines[-8:]}

    def _run(self, cmd: List[str], step: str, p0: float, p1: float, env: Optional[dict] = None) -> None:
        self.step, self.progress = step, p0
        log.info("Đa ngôn ngữ · %s: %s", step, " ".join(cmd))
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace", env={**os.environ, **(env or {})})
        assert proc.stdout
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                self.lines = (self.lines + [line[-200:]])[-40:]
        if proc.wait() != 0:
            raise RuntimeError(f"{step} thất bại (mã {proc.returncode}): " + " | ".join(self.lines[-3:]))
        self.progress = p1

    def _job(self) -> None:
        try:
            ENGINE_DIR.mkdir(parents=True, exist_ok=True)
            uv = _find_uv()
            py = str(venv_python())
            if not venv_python().exists():
                if uv:
                    self._run([uv, "venv", "--python", sys.executable, str(VENV)], "Tạo môi trường riêng", 0.0, 0.03)
                else:
                    self._run([sys.executable, "-m", "venv", str(VENV)], "Tạo môi trường riêng", 0.0, 0.03)
            pip = ([uv, "pip", "install", "--python", py] if uv else [py, "-m", "pip", "install"])
            idx: List[str] = []
            if platform.system() != "Darwin":
                idx = ["--index-url", "https://download.pytorch.org/whl/" + ("cu128" if _has_nvidia() else "cpu"),
                       "--extra-index-url", "https://pypi.org/simple"]
            self._run(pip + [f"torch=={TORCH_VER}", f"torchaudio=={TORCH_VER}", *idx],
                      "Cài PyTorch (~0,3–3 GB tuỳ máy)", 0.03, 0.25)
            self._run(pip + [f"omnivoice=={OMNIVOICE_VER}", "soundfile"], "Cài thư viện OmniVoice", 0.25, 0.32)

            # Tải model (~3 GB) — tiến độ đo bằng dung lượng thư mục cache
            self.step = "Tải model OmniVoice (~3 GB)"
            done = threading.Event()

            base = _dir_bytes(_hf_cache())   # đo phần tăng thêm của cả cache (file đang tải nằm ở kho dùng chung)

            def watch() -> None:
                while not done.is_set():
                    grown = max(0, _dir_bytes(_hf_cache()) - base)
                    self.progress = 0.32 + 0.66 * min(1.0, max(grown, _dir_bytes(_model_dir())) / MODEL_BYTES)
                    done.wait(3)
            threading.Thread(target=watch, daemon=True).start()
            try:
                self._run([py, "-c", f"from huggingface_hub import snapshot_download; snapshot_download('{MODEL_REPO}')"],
                          self.step, self.progress, 0.98)
            finally:
                done.set()
            MARKER.write_text(json.dumps({"installed": time.time(), "torch": TORCH_VER, "omnivoice": OMNIVOICE_VER,
                                          "model": MODEL_REPO}, indent=2), "utf-8")
            self.step, self.progress, self.state = "Đã cài xong", 1.0, "done"
            log.info("Đa ngôn ngữ · cài xong")
        except Exception as e:  # noqa: BLE001
            self.state, self.error = "error", str(e)
            log.error("Đa ngôn ngữ · lỗi cài: %s", e)

    def start(self) -> None:
        with self.lock:
            if self.state == "running":
                return
            self.state, self.error, self.lines, self.progress = "running", "", [], 0.0
            self.thread = threading.Thread(target=self._job, daemon=True)
            self.thread.start()

    def uninstall(self, remove_model: bool = True) -> Dict[str, Any]:
        if self.state == "running":
            raise RuntimeError("Đang cài, chờ xong rồi gỡ.")
        engine.stop()
        model_files = _real_files(_model_dir()) if remove_model else {}
        freed = _dir_bytes(ENGINE_DIR) + sum(model_files.values())
        shutil.rmtree(ENGINE_DIR, ignore_errors=True)
        if remove_model:
            md = str(_model_dir().resolve())
            for rp in model_files:              # xoá cả file thật ở kho dùng chung mà model trỏ tới
                if not rp.startswith(md):
                    try:
                        os.remove(rp)
                    except OSError:
                        pass
            shutil.rmtree(_model_dir(), ignore_errors=True)
        self.state, self.step, self.progress = "idle", "", 0.0
        return {"freed_bytes": freed}


installer = Installer()


# ──────────────────────────────────────────────────────────────────────────
# Tiến trình model
# ──────────────────────────────────────────────────────────────────────────
class Engine:
    def __init__(self) -> None:
        self.proc: Optional[subprocess.Popen] = None
        self.lock = threading.Lock()
        self.device = ""
        self.sample_rate = 24000
        self.last_used = 0.0
        self.loading = False
        threading.Thread(target=self._idle_loop, daemon=True).start()

    def loaded(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def _idle_loop(self) -> None:
        while True:
            time.sleep(30)
            if self.loaded() and time.time() - self.last_used > IDLE_UNLOAD_S and not self.lock.locked():
                log.info("Đa ngôn ngữ · lâu không dùng, tắt model để trả RAM")
                self.stop()

    def _drain_stderr(self, proc: subprocess.Popen) -> None:
        assert proc.stderr
        for line in proc.stderr:
            line = line.rstrip()
            if line and ("Error" in line or "Traceback" in line or "error" in line.lower()[:40]):
                log.warning("Đa ngôn ngữ · %s", line[-300:])

    def _start(self) -> None:
        if not installer.installed():
            raise RuntimeError("Chưa cài gói Đa ngôn ngữ.")
        self.loading = True
        try:
            env = {**os.environ, "PYTHONUNBUFFERED": "1", "HF_HUB_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false",
                   "PYTORCH_ENABLE_MPS_FALLBACK": "1"}
            self.proc = subprocess.Popen([str(venv_python()), "-W", "ignore", str(WORKER)],
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         text=True, encoding="utf-8", errors="replace", env=env, bufsize=1)
            threading.Thread(target=self._drain_stderr, args=(self.proc,), daemon=True).start()
            first = self._read(timeout=600)
            if not first.get("ready"):
                raise RuntimeError(first.get("error") or "Không nạp được model đa ngôn ngữ.")
            self.device = first.get("device", "")
            self.sample_rate = int(first.get("sample_rate") or 24000)
            log.info("Đa ngôn ngữ · nạp model trên %s (%ss)", self.device, first.get("load_seconds"))
        except Exception:
            self.stop()
            raise
        finally:
            self.loading = False

    def _read(self, timeout: float) -> Dict[str, Any]:
        assert self.proc and self.proc.stdout
        box: Dict[str, Any] = {}

        def rd() -> None:
            box["line"] = self.proc.stdout.readline() if self.proc and self.proc.stdout else ""
        th = threading.Thread(target=rd, daemon=True)
        th.start()
        th.join(timeout)
        if th.is_alive():
            self.stop()
            raise RuntimeError("Model đa ngôn ngữ không phản hồi (quá thời gian). Thử đoạn ngắn hơn.")
        line = box.get("line") or ""
        if not line:
            code = self.proc.poll() if self.proc else None
            self.stop()
            raise RuntimeError(f"Tiến trình đa ngôn ngữ đã dừng (mã {code}). Xem Phiên bản & Logs.")
        return json.loads(line)

    def stop(self) -> None:
        p, self.proc = self.proc, None
        if p and p.poll() is None:
            try:
                p.terminate()
                p.wait(10)
            except Exception:  # noqa: BLE001
                p.kill()

    def generate(self, req: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            if not self.loaded():
                self._start()
            out = Path(tempfile.gettempdir()) / f"vieneu-multi-{uuid.uuid4().hex}.wav"
            req = {**req, "id": uuid.uuid4().hex, "out": str(out)}
            assert self.proc and self.proc.stdin
            self.proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
            # CPU chậm: cho tối đa 15 phút một đoạn
            res = self._read(timeout=900)
            self.last_used = time.time()
            if not res.get("ok"):
                raise RuntimeError(res.get("error") or "Lỗi sinh audio đa ngôn ngữ.")
            if res.get("retries"):
                log.info("Đa ngôn ngữ · audio bị lặp, đã tự tạo lại %s lần (loop_score cuối %.2f)",
                         res["retries"], float(res.get("loop_score") or 0))
            try:
                res["wav"] = out.read_bytes()
            finally:
                try:
                    out.unlink()
                except OSError:
                    pass
            return res


engine = Engine()
atexit.register(engine.stop)   # tắt tiến trình model khi app tắt


DESIGNED_IDS = {d["id"] for d in DESIGNED}


def is_multi_voice(voice: Optional[str]) -> bool:
    return bool(voice) and (voice in DESIGNED_IDS or voice.startswith("vn:"))


def map_voice(voice: Optional[str]) -> str:
    """Giọng cho chế độ đa ngôn ngữ: id có sẵn, vn:<tên>, hoặc tên giọng VieNeu (Trúc Ly…) → vn:<tên>."""
    if is_multi_voice(voice):
        return voice  # type: ignore[return-value]
    if voice and any(v["id"] == "vn:" + voice for v in _vieneu_voices()):
        return "vn:" + voice
    return "nu-tre"


def build_request(text: str, language: str, voice: str, accent: str = "", fast: bool = False,
                  speed: Optional[float] = None, ref_audio: Optional[str] = None,
                  ref_text: Optional[str] = None) -> Dict[str, Any]:
    if language not in LANG_IDS:
        raise ValueError(f"Ngôn ngữ '{language}' chưa có trong chế độ Đa ngôn ngữ. Xem danh sách ở GET /api/multi/status.")
    req: Dict[str, Any] = {"text": text, "language": language, "num_step": 16 if fast else 32}
    if speed and abs(speed - 1.0) > 0.01:
        req["speed"] = max(0.5, min(2.0, float(speed)))
    if ref_audio:                                       # clone từ file mẫu của người dùng
        if not (ref_text or "").strip():
            raise ValueError("Cần nhập đúng câu nói trong file mẫu (model dùng nó để học giọng).")
        req.update(ref_audio=ref_audio, ref_text=ref_text.strip(), seed=7)
        return req
    if voice.startswith("vn:"):
        v = next((x for x in _vieneu_voices() if x["id"] == voice), None)
        if not v:
            raise ValueError("Không thấy giọng VieNeu này.")
        req.update(ref_audio=v["file"], ref_text=v["ref_text"], seed=7)
    else:
        d = next((x for x in DESIGNED if x["id"] == voice), None)
        if not d:
            raise ValueError("Không thấy giọng này.")
        ins = d["instruct"]
        if accent and language == "English" and accent in ACCENT_IDS:
            ins += ", " + accent
        # Giọng thiết kế hay hỏng ở đoạn dài ("so we're so we're…"), nhất là khi có giọng vùng (thử 48 mẫu:
        # 13/30 hỏng). Chia khúc ngắn rồi ghép liền: có giọng vùng 5 giây, không có 8 giây → đọc đúng.
        req.update(instruct=ins, seed=d["seed"], chunk_seconds=5.0 if ins != d["instruct"] else 8.0)
    return req


def pcm16_to_float(data: bytes) -> "Any":
    """WAV PCM16 mono → numpy float32 (đọc header bằng module wave, không giả định 44 byte)."""
    import io
    import wave
    import numpy as np
    with wave.open(io.BytesIO(data)) as w:
        frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0


def status() -> Dict[str, Any]:
    hw = hardware()
    return {
        "installed": installer.installed(),
        "install": installer.status(),
        "loaded": engine.loaded(),
        "loading": engine.loading,
        "device": engine.device,
        "hardware": hw,
        "disk": {"engine_bytes": _dir_bytes(ENGINE_DIR), "model_bytes": _dir_bytes(_model_dir()),
                 "download_estimate": "≈ 4 GB (PyTorch + OmniVoice + model 3 GB)"},
        "languages": LANGUAGES,
        "voices": voices(),
        "attribution": ATTRIBUTION,
    }
