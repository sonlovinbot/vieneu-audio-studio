"""MCP server của AI Audio Studio — cho Claude Desktop, Claude Code, ChatGPT Codex… gọi tạo giọng.

Chạy trên CÙNG MÁY với app (giao tiếp stdio, mỗi dòng một JSON-RPC theo chuẩn Model Context Protocol).
Không mở cổng mạng nào: server này chỉ gọi lại API của app tại http://127.0.0.1:8001.

    python -m webapp.mcp_server          (app tự sinh cấu hình đúng đường dẫn ở trang MCP & API)

Biến môi trường (tuỳ chọn):
  VIENEU_URL            địa chỉ app (mặc định http://127.0.0.1:<cổng trong branding.json>)
  VIENEU_API_KEY        khoá API nếu app có bật khoá
  VIENEU_MCP_OUT        thư mục lưu file audio (mặc định ~/Downloads/AI-Audio-Studio)
  VIENEU_MCP_AUTOSTART  "0" = không tự mở app khi app đang tắt
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
_BRAND = json.loads((HERE / "config" / "branding.json").read_text(encoding="utf-8"))
APP = _BRAND["app"]
BASE = (os.environ.get("VIENEU_URL") or f"http://127.0.0.1:{APP.get('default_port', 8001)}").rstrip("/")
API_KEY = os.environ.get("VIENEU_API_KEY", "").strip()
OUT_DIR = Path(os.environ.get("VIENEU_MCP_OUT") or (Path.home() / "Downloads" / "AI-Audio-Studio"))
AUTOSTART = os.environ.get("VIENEU_MCP_AUTOSTART", "1").strip() not in ("0", "off", "false", "no")
PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
VIETNAMESE = ("", "vietnamese", "vi", "vi-vn", "tiếng việt", "tieng viet", "việt", "viet")

# AI hay gửi "en", "English (US)", "Tiếng Anh", "American"… → đổi về đúng id app nhận.
_LANG_ALIASES = {
    "en": "English", "eng": "English", "en-us": "English", "en-gb": "English", "english (us)": "English",
    "tiếng anh": "English", "anh": "English", "ko": "Korean", "kr": "Korean", "tiếng hàn": "Korean", "hàn": "Korean",
    "ja": "Japanese", "jp": "Japanese", "tiếng nhật": "Japanese", "nhật": "Japanese",
    "zh": "Chinese", "zh-cn": "Chinese", "mandarin": "Chinese", "tiếng trung": "Chinese", "trung": "Chinese",
    "yue": "Cantonese", "quảng đông": "Cantonese", "tl": "Filipino", "tagalog": "Filipino", "fil": "Filipino",
    "th": "Thai", "thái": "Thai", "id": "Indonesian", "ms": "Malay", "fr": "French", "pháp": "French",
    "es": "Spanish", "tây ban nha": "Spanish", "de": "German", "đức": "German", "ru": "Russian", "nga": "Russian",
    "pt": "Portuguese", "it": "Italian", "ý": "Italian", "hi": "Hindi", "ar": "Standard Arabic", "arabic": "Standard Arabic",
}
_ACCENT_ALIASES = {
    "american": "american accent", "us": "american accent", "usa": "american accent", "mỹ": "american accent", "my": "american accent",
    "british": "british accent", "uk": "british accent", "england": "british accent", "anh": "british accent",
    "australian": "australian accent", "au": "australian accent", "úc": "australian accent",
    "canadian": "canadian accent", "ca": "canadian accent", "canada": "canadian accent",
    "indian": "indian accent", "in": "indian accent", "ấn độ": "indian accent", "an do": "indian accent",
}
ACCENT_IDS = ("american accent", "british accent", "australian accent", "canadian accent", "indian accent")


def norm_language(lang: Any) -> str:
    l = str(lang or "").strip()
    k = l.lower()
    if k in VIETNAMESE:
        return "" if not k else "Vietnamese"
    return _LANG_ALIASES.get(k) or (l[:1].upper() + l[1:] if l else "")


def norm_accent(acc: Any) -> str:
    k = str(acc or "").strip().lower()
    if not k or k in ("auto", "none", "default", "tự động"):
        return ""
    if k in ACCENT_IDS:
        return k
    return _ACCENT_ALIASES.get(k.replace(" accent", "").strip(), "")

INSTRUCTIONS = (
    "AI Audio Studio chạy trên máy người dùng: đọc văn bản tiếng Việt (25 giọng có sẵn + giọng đã clone) "
    "và — ở bản Global đã cài gói Đa ngôn ngữ — 17 thứ tiếng khác. Gọi list_voices trước khi chọn giọng. "
    "File audio được lưu trên máy người dùng; báo lại đường dẫn file cho họ."
)

_out = sys.stdout
sys.stdout = sys.stderr          # mọi print() lạc → stderr, stdout chỉ còn JSON-RPC


# ──────────────────────────────────────────────────────────────────────────
# Gọi API của app
# ──────────────────────────────────────────────────────────────────────────
class AppError(Exception):
    pass


def _request(method: str, path: str, body: Optional[dict] = None, timeout: float = 900) -> tuple:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if API_KEY:
        req.add_header("X-API-Key", API_KEY)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8")).get("detail")
        except Exception:  # noqa: BLE001
            detail = None
        if e.code == 401:
            detail = "App đang bật khoá API — thêm VIENEU_API_KEY vào cấu hình MCP (trang MCP & API của app)."
        raise AppError(f"{detail or e.reason} (HTTP {e.code})") from e

def _multipart(fields: Dict[str, str], file_field: str, file_path: Path) -> tuple:
    import uuid
    b = "----vieneu" + uuid.uuid4().hex
    out = bytearray()
    for k, v in fields.items():
        out += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8")
    out += (f'--{b}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n").encode("utf-8")
    out += file_path.read_bytes() + f"\r\n--{b}--\r\n".encode("utf-8")
    return bytes(out), f"multipart/form-data; boundary={b}"


def _request_form(path: str, fields: Dict[str, str], file_field: str, file_path: Path, timeout: float = 900) -> tuple:
    if not file_path.is_file():
        raise AppError(f"Không thấy file: {file_path}")
    body, ctype = _multipart(fields, file_field, file_path)
    req = urllib.request.Request(BASE + path, data=body, method="POST")
    req.add_header("Content-Type", ctype)
    if API_KEY:
        req.add_header("X-API-Key", API_KEY)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8")).get("detail")
        except Exception:  # noqa: BLE001
            detail = None
        raise AppError(f"{detail or e.reason} (HTTP {e.code})") from e


def _split_text(text: str, limit: int) -> List[str]:
    """Chia văn bản dài thành các đoạn <= limit ký tự, ưu tiên ngắt ở cuối câu / xuống dòng."""
    text = text.strip()
    if len(text) <= limit:
        return [text]
    parts = re.split(r"(?<=[.!?。！？…\n])\s*", text)
    chunks: List[str] = []
    cur = ""
    for p in parts:
        if not p:
            continue
        while len(p) > limit:                       # câu quá dài: cắt ở dấu phẩy / khoảng trắng
            cut = max(p.rfind(",", 0, limit), p.rfind(" ", 0, limit))
            cut = cut if cut > limit // 2 else limit
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(p[:cut + 1].strip())
            p = p[cut + 1:].strip()
        if len(cur) + len(p) + 1 > limit and cur:
            chunks.append(cur)
            cur = p
        else:
            cur = (cur + " " + p).strip()
    if cur:
        chunks.append(cur)
    return [c for c in chunks if c]


def _join_wavs(parts: List[bytes], gap: float = 0.35) -> bytes:
    import io
    import wave
    if len(parts) == 1:
        return parts[0]
    frames, params = [], None
    for b in parts:
        with wave.open(io.BytesIO(b)) as w:
            if params is None:
                params = w.getparams()
            elif (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (params.framerate, params.nchannels, params.sampwidth):
                raise AppError("Các đoạn audio khác định dạng, không ghép được.")
            frames.append(w.readframes(w.getnframes()))
    silence = b"\x00" * (int(params.framerate * gap) * params.nchannels * params.sampwidth)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setparams(params)
        w.writeframes(silence.join(frames))
    return out.getvalue()


def _get_json(path: str, timeout: float = 15) -> Any:
    return json.loads(_request("GET", path, timeout=timeout)[0].decode("utf-8"))


def _running() -> bool:
    try:
        _get_json("/api/health", timeout=3)
        return True
    except (AppError, OSError, ValueError):
        return False


def ensure_app() -> None:
    """App tắt → tự mở (chạy ẩn, không mở trình duyệt) rồi đợi tối đa ~90 giây."""
    if _running():
        return
    if not AUTOSTART or not BASE.startswith("http://127.0.0.1"):
        raise AppError("AI Audio Studio chưa chạy. Mở icon AI Audio Studio trên Desktop rồi thử lại.")
    log_dir = Path(os.environ.get("VIENEU_HOME") or (Path.home() / ".vieneu")) / "studio"
    log_dir.mkdir(parents=True, exist_ok=True)
    flags: Dict[str, Any] = {}
    if os.name == "nt":
        flags["creationflags"] = 0x00000008 | 0x00000200      # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        flags["start_new_session"] = True
    with open(log_dir / "mcp-autostart.log", "ab") as log:
        subprocess.Popen([sys.executable, "-m", "webapp.server"], cwd=str(HERE.parent),
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, **flags)
    for _ in range(90):
        time.sleep(1)
        if _running():
            return
    raise AppError("Đã thử mở AI Audio Studio nhưng app chưa lên sau 90 giây. Mở icon trên Desktop rồi thử lại.")


def _app_info() -> Dict[str, Any]:
    try:
        return (_get_json("/api/info").get("branding") or {}).get("app") or {}
    except (AppError, OSError, ValueError):
        return {}


def _multi() -> Dict[str, Any]:
    try:
        return _get_json("/api/multi/status")
    except AppError as e:
        return {"installed": False, "missing": "HTTP 404" in str(e) or "HTTP 405" in str(e)}


def _need_multi() -> None:
    """Gọi đa ngôn ngữ mà app đang chạy là bản cũ (chưa có) hoặc chưa cài gói → báo rõ cách sửa."""
    m = _multi()
    if m.get("missing"):
        info = _app_info()
        if info.get("channel") != "global" and info.get("version", "0") >= "2.0.1":
            raise AppError("Đọc tiếng nước ngoài (Đa ngôn ngữ) chỉ có ở bản Global — bản đầy đủ. Bản đang dùng là bản Free: "
                           "đọc tiếng Việt với 25 giọng có sẵn và giọng đã clone.")
        raise AppError(f"App đang chạy ở {BASE} là bản {info.get('version', '?')} — chưa có Đa ngôn ngữ (tính năng của bản Global).")
    if not m.get("installed"):
        raise AppError("Chưa cài gói Đa ngôn ngữ. Mở app → trang 🌏 Đa ngôn ngữ → Cài gói (~4 GB), "
                       "hoặc gọi multilang_package với action=install nếu người dùng đồng ý.")


def _slug(s: str) -> str:
    s = re.sub(r"[^\w\- ]+", "", s, flags=re.UNICODE).strip().replace(" ", "-")
    return s[:60] or "audio"


def _save(data: bytes, name: Optional[str], hint: str, open_after: bool) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = _slug(name) if name else f"{datetime.now():%Y%m%d-%H%M%S}-{_slug(hint[:30])}"
    path = OUT_DIR / f"{stem}.wav"
    i = 2
    while path.exists():
        path = OUT_DIR / f"{stem}-{i}.wav"
        i += 1
    path.write_bytes(data)
    if open_after:
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            elif os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError:
            pass
    return path


def _duration(data: bytes) -> float:
    try:
        sr = int.from_bytes(data[24:28], "little") or 48000
        return round(max(0, len(data) - 44) / 2 / sr, 1)
    except Exception:  # noqa: BLE001
        return 0.0


def _done(path: Path, data: bytes, headers: Dict[str, str], what: str) -> str:
    lines = [f"✅ {what} — {_duration(data)} giây.", f"File: {path}"]
    if headers.get("X-History-Id") or headers.get("x-history-id"):
        lines.append(f"Cũng đã lưu vào Lịch sử của app: {BASE}/  (menu Lịch sử)")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────
# Công cụ
# ──────────────────────────────────────────────────────────────────────────
def tool_app_status(_: Dict[str, Any]) -> str:
    ensure_app()
    h = _get_json("/api/health")
    m = _multi()
    st = h.get("status", {})
    info = _app_info()
    old = m.get("missing")
    return "\n".join([
        f"AI Audio Studio {info.get('version', '?')} {info.get('edition') or ''} đang chạy tại {BASE}".replace("  ", " "),
        f"Model tiếng Việt: {'đã nạp' if st.get('loaded') else 'chưa nạp (tự nạp ở lần đọc đầu, có thể mất 1–2 phút)'}",
        ("Đa ngôn ngữ: không có ở bản này (chỉ bản Global) — đọc tiếng Việt" if old else
         f"Gói Đa ngôn ngữ: {'đã cài' if m.get('installed') else 'chưa cài (chỉ đọc được tiếng Việt)'}"),
        f"Khoá API: {'đang bật' if h.get('auth_required') else 'không bật'}",
        f"File audio lưu tại: {OUT_DIR}",
    ])


def tool_list_voices(_: Dict[str, Any]) -> str:
    ensure_app()
    voices = _get_json("/api/voices").get("voices", [])
    out = ["TIẾNG VIỆT (language = \"Vietnamese\") — dùng đúng id trong ngoặc kép:"]
    for v in voices:
        out.append(f"- \"{v['id']}\" — {re.sub(r'^⭐ ', '', v.get('label', '')).split(' — ', 1)[-1]}"
                   + ("  [giọng người dùng đã clone]" if v.get("custom") else ""))
    m = _multi()
    if m.get("installed"):
        langs = ", ".join(f"\"{l['id']}\"" for l in m.get("languages", []) if l["id"].lower() != "vietnamese")
        vs = m.get("voices", {})
        out += ["", f"ĐA NGÔN NGỮ — language là một trong: {langs}",
                "voice dùng được cho mọi ngôn ngữ trên:"]
        out += [f"- \"{d['id']}\" — {d['label']}" for d in vs.get("designed", [])]
        out.append("- \"vn:<tên giọng Việt>\" — giọng Việt ở trên nói tiếng nước ngoài, vd \"vn:Trúc Ly\"")
        acc = [f"\"{a['id']}\" ({a['label']})" for a in vs.get("accents", []) if a.get("id")]
        if acc:
            out.append("accent (chỉ tiếng Anh): " + ", ".join(acc))
    else:
        out += ["", "Đa ngôn ngữ: " + ("không có ở bản này (chỉ bản Global) — chỉ đọc tiếng Việt." if m.get("missing") else
                                     "CHƯA CÀI — chỉ đọc được tiếng Việt. Người dùng cài ở trang 🌏 Đa ngôn ngữ của app.")]
    return "\n".join(out)


def _tts_once(text: str, lang: str, voice: Optional[str], a: Dict[str, Any]) -> tuple:
    if lang.lower() in VIETNAMESE and not (voice or "").startswith("vn:") and voice not in _designed_ids():
        data, headers = _request("POST", "/api/tts", {"text": text, "voice": voice})
        return data, headers, f"Đã đọc tiếng Việt bằng giọng {voice or 'mặc định'}"
    body = {"text": text, "language": lang or "Vietnamese", "voice": voice or "nu-tre",
            "accent": norm_accent(a.get("accent")) if (lang or "") == "English" else "", "fast": bool(a.get("fast"))}
    if a.get("speed"):
        body["speed"] = float(a["speed"])
    data, headers = _request("POST", "/api/multi/tts", body)
    return data, headers, f"Đã đọc {body['language']} bằng giọng {body['voice']}"


def tool_text_to_speech(a: Dict[str, Any]) -> str:
    text = str(a.get("text") or "").strip()
    if not text:
        raise AppError("Thiếu text.")
    ensure_app()
    lang = norm_language(a.get("language"))
    voice = (a.get("voice") or "").strip() or None
    vi = lang.lower() in VIETNAMESE and not (voice or "").startswith("vn:") and voice not in _designed_ids()
    if not vi:
        _need_multi()
    limit = 4500 if vi else 1900                      # app giới hạn 5.000 / 2.000 ký tự mỗi lần
    chunks = _split_text(text, limit)
    results = [_tts_once(c, lang, voice, a) for c in chunks]
    data = _join_wavs([r[0] for r in results])
    what = results[0][2] + (f" ({len(chunks)} đoạn, đã ghép liền)" if len(chunks) > 1 else "")
    path = _save(data, a.get("file_name"), text, bool(a.get("open_after")))
    return _done(path, data, results[-1][1], what)


def _designed_ids() -> List[str]:
    return ["nu-tre", "nu-trung-nien", "nu-teen", "nam-tre", "nam-trung-nien", "nam-lon-tuoi"]


def tool_conversation(a: Dict[str, Any]) -> str:
    turns = a.get("turns") or []
    if not isinstance(turns, list) or not turns:
        raise AppError("Thiếu turns (danh sách lượt thoại).")
    ensure_app()
    clean = []
    for t in turns:
        x = {k: t.get(k) for k in ("voice", "text") if t.get(k)}
        lang = norm_language(t.get("language"))
        if lang and lang != "Vietnamese":
            x["language"] = lang
            if lang == "English" and norm_accent(t.get("accent")):
                x["accent"] = norm_accent(t.get("accent"))
        clean.append(x)
    if any(x.get("language") or (x.get("voice") or "").startswith("vn:") or x.get("voice") in _designed_ids() for x in clean):
        _need_multi()
    body = {"turns": clean,
            "gap_seconds": float(a.get("gap_seconds") or 0.4)}
    data, headers = _request("POST", "/api/conversation", body)
    first = next((t.get("text", "") for t in turns if t.get("text")), "hoi-thoai")
    path = _save(data, a.get("file_name"), "hoi-thoai-" + first, bool(a.get("open_after")))
    return _done(path, data, headers, f"Đã tạo hội thoại {len(body['turns'])} lượt")


def _path_arg(v: Any, what: str) -> Path:
    if not v:
        raise AppError(f"Thiếu {what}.")
    return Path(str(v)).expanduser()


def tool_clone_voice(a: Dict[str, Any]) -> str:
    text = str(a.get("text") or "").strip()
    if not text:
        raise AppError("Thiếu text cần đọc.")
    ref = _path_arg(a.get("ref_audio"), "ref_audio (đường dẫn file audio mẫu 3–15 giây)")
    ensure_app()
    lang = norm_language(a.get("language"))
    if lang.lower() in VIETNAMESE:
        data, headers = _request_form("/api/clone", {"text": text}, "ref_audio", ref)
        what = "Đã clone giọng từ file mẫu và đọc tiếng Việt"
    else:
        _need_multi()
        ref_text = str(a.get("ref_text") or "").strip()
        if not ref_text:
            raise AppError("Clone sang ngôn ngữ khác cần ref_text: gõ ĐÚNG từng chữ câu nói trong file mẫu.")
        data, headers = _request_form("/api/multi/clone", {"text": text, "ref_text": ref_text, "language": lang,
                                                           "fast": "true" if a.get("fast") else "false",
                                                           "speed": str(a.get("speed") or 1.0)}, "ref_audio", ref)
        what = f"Đã clone giọng từ file mẫu và đọc {lang}"
    path = _save(data, a.get("file_name"), text, bool(a.get("open_after")))
    return _done(path, data, headers, what)


def tool_save_voice(a: Dict[str, Any]) -> str:
    name = str(a.get("name") or "").strip()
    if not name:
        raise AppError("Thiếu name (tên giọng).")
    ref = _path_arg(a.get("ref_audio"), "ref_audio")
    ensure_app()
    res = json.loads(_request_form("/api/voices/custom", {"name": name}, "ref_audio", ref, timeout=300)[0].decode("utf-8"))
    return f"✅ Đã lưu giọng \"{res.get('name', name)}\" vào Giọng của tôi. Dùng ngay: text_to_speech với voice = \"{res.get('name', name)}\"."


def tool_delete_voice(a: Dict[str, Any]) -> str:
    name = str(a.get("name") or "").strip()
    if not name:
        raise AppError("Thiếu name.")
    ensure_app()
    import urllib.parse
    _request("DELETE", "/api/voices/custom?name=" + urllib.parse.quote(name), timeout=60)
    return f"✅ Đã xóa giọng \"{name}\" khỏi Giọng của tôi."


def tool_list_history(a: Dict[str, Any]) -> str:
    ensure_app()
    runs = _get_json("/api/history").get("runs", [])[: max(1, min(int(a.get("limit") or 10), 50))]
    if not runs:
        return "Lịch sử trống."
    out = []
    for r in runs:
        when = datetime.fromtimestamp(r.get("created", 0)).strftime("%d/%m %H:%M")
        txt = re.sub(r"\s+", " ", r.get("text", ""))
        out.append(f"- id {r['id']} · {when} · {r.get('kind')} · {r.get('voice')} · {r.get('duration')}s · {txt[:70]}")
    return "\n".join(out) + "\n\nLấy file audio: get_history_audio với id."


def tool_get_history_audio(a: Dict[str, Any]) -> str:
    rid = str(a.get("id") or "").strip()
    if not rid:
        raise AppError("Thiếu id (lấy từ list_history).")
    ensure_app()
    data, headers = _request("GET", f"/api/history/{rid}/audio", timeout=60)
    path = _save(data, a.get("file_name"), "lich-su-" + rid, bool(a.get("open_after")))
    return _done(path, data, {}, "Đã lấy lại audio từ Lịch sử")


def tool_multilang_package(a: Dict[str, Any]) -> str:
    ensure_app()
    action = str(a.get("action") or "status").lower()
    if action == "install":
        try:
            st = json.loads(_request("POST", "/api/multi/install", {}, timeout=30)[0].decode("utf-8"))
        except AppError as e:
            return f"❌ {e}"
        return "⬇ Đã bắt đầu cài gói Đa ngôn ngữ (~4 GB, 5–20 phút). Gọi lại action=status để xem tiến độ.\n" + _install_line(st)
    m = _multi()
    if m.get("installed"):
        hw = m.get("hardware", {})
        return ("✅ Gói Đa ngôn ngữ đã cài. " + str(hw.get("speed_note", "")) +
                "\nNgôn ngữ: " + ", ".join(l["id"] for l in m.get("languages", [])))
    return "Gói Đa ngôn ngữ CHƯA cài. " + _install_line(m.get("install") or {}) + "\nCài: multilang_package với action=install."


def _install_line(st: Dict[str, Any]) -> str:
    st = st.get("install", st) if isinstance(st, dict) else {}
    if st.get("running") or st.get("state") == "running":
        return f"Đang cài: {st.get('step', '')} {int(float(st.get('progress', 0)) * 100)}%"
    if st.get("error"):
        return f"Lỗi cài: {st['error']}"
    return ""


_COMMON = {
    "file_name": {"type": "string", "description": "Tên file (không cần đuôi). Bỏ trống = tự đặt theo giờ."},
    "open_after": {"type": "boolean", "description": "true = mở file để nghe ngay sau khi tạo.", "default": False},
}
TOOLS = [
    {"name": "app_status", "title": "Kiểm tra AI Audio Studio",
     "description": "Kiểm tra app có đang chạy, model đã nạp chưa, đã cài gói Đa ngôn ngữ chưa, file audio lưu ở đâu.",
     "inputSchema": {"type": "object", "properties": {}},
     "annotations": {"readOnlyHint": True}, "fn": tool_app_status},
    {"name": "list_voices", "title": "Danh sách giọng & ngôn ngữ",
     "description": "Liệt kê giọng tiếng Việt (có sẵn + giọng người dùng đã clone), các ngôn ngữ và giọng đa ngôn ngữ. Gọi trước khi chọn voice.",
     "inputSchema": {"type": "object", "properties": {}},
     "annotations": {"readOnlyHint": True}, "fn": tool_list_voices},
    {"name": "text_to_speech", "title": "Đọc văn bản thành giọng nói",
     "description": "Đọc văn bản thành file audio trên máy người dùng. Tiếng Việt: tối đa 5.000 ký tự/lần, chèn được [cười] [thở dài]. "
                    "Ngôn ngữ khác (cần gói Đa ngôn ngữ): tối đa 2.000 ký tự/lần. Văn bản dài hơn hãy chia thành nhiều lần gọi.",
     "inputSchema": {"type": "object", "required": ["text"], "properties": {
         "text": {"type": "string", "description": "Nội dung cần đọc."},
         "voice": {"type": "string", "description": "id giọng lấy từ list_voices. Bỏ trống = giọng mặc định."},
         "language": {"type": "string", "description": "\"Vietnamese\" (mặc định) hoặc một ngôn ngữ trong list_voices, vd \"English\", \"Korean\", \"Japanese\"."},
         "accent": {"type": "string", "enum": ["", *ACCENT_IDS],
                    "description": "Chỉ tiếng Anh: giọng vùng. Bỏ trống = tự nhiên (khuyên dùng)."},
         "speed": {"type": "number", "description": "Chỉ đa ngôn ngữ: tốc độ 0.7–1.3 (1 = bình thường)."},
         "fast": {"type": "boolean", "description": "Chỉ đa ngôn ngữ: chế độ nhanh (nhanh ~2 lần, đôi khi sót chữ)."},
         **_COMMON}},
     "fn": tool_text_to_speech},
    {"name": "conversation", "title": "Tạo hội thoại nhiều giọng",
     "description": "Ghép nhiều lượt thoại (mỗi lượt một giọng, có thể khác ngôn ngữ) thành một file audio — podcast, kịch bản, bài giảng.",
     "inputSchema": {"type": "object", "required": ["turns"], "properties": {
         "turns": {"type": "array", "description": "Các lượt thoại theo thứ tự.", "items": {
             "type": "object", "required": ["text"], "properties": {
                 "voice": {"type": "string", "description": "id giọng từ list_voices."},
                 "text": {"type": "string"},
                 "language": {"type": "string", "description": "Bỏ trống = tiếng Việt; vd \"English\" (cần gói Đa ngôn ngữ)."},
                 "accent": {"type": "string", "enum": ["", *ACCENT_IDS]}}}},
         "gap_seconds": {"type": "number", "description": "Khoảng lặng giữa các lượt (giây), mặc định 0.4."},
         **_COMMON}},
     "fn": tool_conversation},
    {"name": "clone_voice", "title": "Clone giọng từ file mẫu",
     "description": "Đọc văn bản bằng giọng được clone từ một file audio mẫu 3–15 giây trên máy (không nhạc nền). "
                    "Đọc tiếng Việt: chỉ cần ref_audio. Đọc ngôn ngữ khác: bắt buộc thêm ref_text = đúng từng chữ câu nói trong file mẫu.",
     "inputSchema": {"type": "object", "required": ["text", "ref_audio"], "properties": {
         "text": {"type": "string", "description": "Nội dung cần đọc."},
         "ref_audio": {"type": "string", "description": "Đường dẫn file audio mẫu trên máy (wav/mp3/m4a)."},
         "ref_text": {"type": "string", "description": "Chỉ khi language khác tiếng Việt: lời nói chính xác trong file mẫu."},
         "language": {"type": "string", "description": "Mặc định Vietnamese; hoặc English, Korean, Japanese…"},
         "speed": {"type": "number", "description": "Chỉ đa ngôn ngữ: 0.7–1.3."},
         "fast": {"type": "boolean"}, **_COMMON}},
     "fn": tool_clone_voice},
    {"name": "save_voice", "title": "Lưu giọng vào Giọng của tôi",
     "description": "Lưu file audio mẫu thành một giọng đặt tên, dùng lại sau này bằng text_to_speech (voice = tên đó).",
     "inputSchema": {"type": "object", "required": ["name", "ref_audio"], "properties": {
         "name": {"type": "string", "description": "Tên giọng."},
         "ref_audio": {"type": "string", "description": "Đường dẫn file audio mẫu trên máy."}}},
     "fn": tool_save_voice},
    {"name": "delete_voice", "title": "Xóa giọng đã lưu",
     "description": "Xóa một giọng trong Giọng của tôi (không xóa được 25 giọng có sẵn). Chỉ gọi khi người dùng yêu cầu rõ.",
     "inputSchema": {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}},
     "annotations": {"destructiveHint": True}, "fn": tool_delete_voice},
    {"name": "list_history", "title": "Lịch sử các lần tạo audio",
     "description": "Liệt kê các lượt tạo audio gần nhất của app (id, giọng, thời lượng, nội dung).",
     "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "description": "Số lượt, mặc định 10, tối đa 50."}}},
     "annotations": {"readOnlyHint": True}, "fn": tool_list_history},
    {"name": "get_history_audio", "title": "Lấy lại audio từ Lịch sử",
     "description": "Chép audio của một lượt trong Lịch sử ra thư mục lưu file.",
     "inputSchema": {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}, **_COMMON}},
     "fn": tool_get_history_audio},
    {"name": "multilang_package", "title": "Gói Đa ngôn ngữ",
     "description": "Xem trạng thái hoặc bắt đầu cài gói Đa ngôn ngữ (~4 GB; bản Global). Cài chỉ khi người dùng đồng ý.",
     "inputSchema": {"type": "object", "properties": {"action": {"type": "string", "enum": ["status", "install"], "default": "status"}}},
     "fn": tool_multilang_package},
]
_BY_NAME = {t["name"]: t for t in TOOLS}


# ──────────────────────────────────────────────────────────────────────────
# JSON-RPC qua stdio
# ──────────────────────────────────────────────────────────────────────────
_LOCK = threading.Lock()


def _send(obj: Dict[str, Any]) -> None:
    with _LOCK:
        _out.write(json.dumps(obj, ensure_ascii=False) + "\n")
        _out.flush()


def _with_progress(fn, args: Dict[str, Any], token: Any) -> str:
    """Việc lâu (nạp model, văn bản dài): cứ 5 giây báo tiến độ để Claude/Codex không ngắt vì chờ quá lâu."""
    if token is None:
        return fn(args)
    box: Dict[str, Any] = {}

    def run() -> None:
        try:
            box["ok"] = fn(args)
        except BaseException as e:  # noqa: BLE001
            box["err"] = e

    th = threading.Thread(target=run, daemon=True)
    th.start()
    n = 0
    while th.is_alive():
        th.join(5)
        if th.is_alive():
            n += 1
            _send({"jsonrpc": "2.0", "method": "notifications/progress",
                   "params": {"progressToken": token, "progress": n, "message": f"Đang tạo audio… {n * 5} giây"}})
    if "err" in box:
        raise box["err"]
    return box["ok"]


def handle(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    method, mid, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
    if mid is None:                      # thông báo (notifications/initialized…) — không trả lời
        return None
    if method == "initialize":
        want = params.get("protocolVersion")
        return {"protocolVersion": want if want in PROTOCOLS else PROTOCOLS[0],
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "ai-audio-studio", "title": "AI Audio Studio", "version": APP.get("version", "")},
                "instructions": INSTRUCTIONS}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [{k: v for k, v in t.items() if k != "fn"} for t in TOOLS]}
    if method == "tools/call":
        tool = _BY_NAME.get(params.get("name"))
        if not tool:
            raise LookupError(f"Không có công cụ {params.get('name')}")
        try:
            token = (params.get("_meta") or {}).get("progressToken")
            text, err = _with_progress(tool["fn"], params.get("arguments") or {}, token), False
        except AppError as e:
            text, err = f"❌ {e}", True
        except (OSError, ValueError) as e:
            text, err = f"❌ Lỗi khi gọi AI Audio Studio: {e}", True
        return {"content": [{"type": "text", "text": text}], "isError": err}
    raise LookupError(f"Method not found: {method}")


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            _send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            continue
        try:
            res = handle(msg)
            if res is not None:
                _send({"jsonrpc": "2.0", "id": msg.get("id"), "result": res})
        except LookupError as e:
            _send({"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32601, "message": str(e)}})
        except Exception as e:  # noqa: BLE001
            _send({"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32603, "message": f"{type(e).__name__}: {e}"}})


if __name__ == "__main__":
    main()
