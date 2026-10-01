"""VieNeu Studio library: history + "Giọng của tôi", storage and HTTP endpoints (no model)."""
import io
import json
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

from webapp import server
from webapp.library import Library


def _wav(seconds: float = 0.5, sr: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sr)
        f.writeframes(b"\x00\x00" * int(seconds * sr))
    return buf.getvalue()


# ── Library (storage only) ─────────────────────────────────────────────────
@pytest.fixture
def lib(tmp_path):
    return Library(tmp_path / "studio", max_runs=3)


def test_add_run_newest_first_and_audio_saved(lib):
    a = lib.add_run("tts", "một", "Hải Đăng", "v3turbo", b"A" * 100, 1.0)
    b = lib.add_run("tts", "hai", "Trúc Ly", "v3turbo", b"B" * 100, 2.0)
    runs = lib.list_runs()
    assert [r["id"] for r in runs] == [b["id"], a["id"]]
    assert runs[0]["voice"] == "Trúc Ly" and runs[0]["duration"] == 2.0
    assert lib.run_audio_path(a["id"]).read_bytes() == b"A" * 100


def test_prune_keeps_max_runs_and_deletes_old_audio(lib):
    ids = [lib.add_run("tts", str(i), "v", "m", b"x", 0.1)["id"] for i in range(5)]
    kept = [r["id"] for r in lib.list_runs()]
    assert kept == ids[::-1][:3]
    assert lib.run_audio_path(ids[0]) is None and lib.run_audio_path(ids[1]) is None
    assert len(list((lib.root / "history").glob("*.wav"))) == 3


def test_delete_and_clear_runs(lib):
    r1 = lib.add_run("tts", "1", "v", "m", b"x", 0.1)
    lib.add_run("tts", "2", "v", "m", b"x", 0.1)
    assert lib.delete_run(r1["id"]) is True
    assert lib.delete_run(r1["id"]) is False
    assert lib.clear_runs() == 1
    assert lib.list_runs() == []


def test_rejects_path_traversal_ids(lib):
    assert lib.run_audio_path("../../etc/passwd") is None
    assert lib.delete_run("../history") is False


def test_corrupt_history_is_quarantined_not_fatal(lib):
    lib.root.mkdir(parents=True)
    (lib.root / "history.json").write_text("{not json", encoding="utf-8")
    assert lib.list_runs() == []
    assert list(lib.root.glob("history.json.corrupt-*"))
    lib.add_run("tts", "ok", "v", "m", b"x", 0.1)
    assert len(lib.list_runs()) == 1


def test_voice_meta_roundtrip_rename_drop(lib):
    lib.put_voice_meta("Giọng Sơn", b"CLIP", ".WAV", "v3turbo")
    assert lib.voice_clip_path("Giọng Sơn").read_bytes() == b"CLIP"
    lib.rename_voice_meta("Giọng Sơn", "Sơn 2")
    assert lib.voice_clip_path("Giọng Sơn") is None
    clip = lib.voice_clip_path("Sơn 2")
    assert clip is not None
    lib.drop_voice_meta("Sơn 2")
    assert lib.voice_meta() == {} and not clip.exists()


def test_voice_meta_replace_removes_old_clip(lib):
    lib.put_voice_meta("A", b"one", ".wav", "m")
    first = lib.voice_clip_path("A")
    lib.put_voice_meta("A", b"two", ".exe", "m")   # unknown ext falls back to .wav
    assert not first.exists()
    assert lib.voice_clip_path("A").suffix == ".wav"


# ── HTTP endpoints with a fake model ───────────────────────────────────────
class _FakeTurbo:
    sample_rate = 16000
    default_style = "tu_nhien"

    def __init__(self):
        self._preset_voices = {"Hải Đăng": {"description": "Nam · Bắc", "featured": 1,
                                            "speaker_emb": np.ones(192, np.float32),
                                            "codes": np.zeros(4, np.int64)}}
        self._default_voice = "Hải Đăng"
        self.calls = []

    def infer(self, text, voice=None, ref_audio=None, **kw):
        self.calls.append(("infer", text, voice))
        if voice is not None and voice not in self._preset_voices:
            raise ValueError(f"unknown voice {voice}")
        return np.zeros(self.sample_rate // 2, np.float32)

    def add_voice(self, name, ref_audio, *, denoise=True, description="", **kw):
        self._preset_voices[name] = {"description": description, "gender": "",
                                     "speaker_emb": np.full(192, 0.5, np.float32),
                                     "codes": np.arange(6, dtype=np.int64)}
        return name

    def remove_voice(self, name, save=False):
        self._preset_voices.pop(name, None)

    def list_preset_voices(self):
        return [(n, n) for n in self._preset_voices]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("VIENEU_HOME", str(tmp_path))          # apps.user_voices store
    monkeypatch.setattr(server, "library", Library(tmp_path / "studio", max_runs=50))
    monkeypatch.setattr(server, "LIBRARY_ENABLED", True)
    monkeypatch.setattr(server, "API_KEY", "")
    fake = _FakeTurbo()
    monkeypatch.setattr(server.manager, "_tts", fake)
    c = TestClient(server.app)
    c.fake = fake
    return c


def _save(client, name, clip=None):
    return client.post("/api/voices/custom", data={"name": name},
                       files={"ref_audio": ("mau.wav", clip or _wav(), "audio/wav")})


def test_tts_is_recorded_in_history(client):
    r = client.post("/api/tts", json={"text": "Xin chào", "voice": "Hải Đăng"})
    assert r.status_code == 200
    run_id = r.headers["X-History-Id"]
    runs = client.get("/api/history").json()["runs"]
    assert runs[0]["id"] == run_id and runs[0]["kind"] == "tts"
    assert runs[0]["voice"] == "Hải Đăng" and runs[0]["text"] == "Xin chào"
    assert runs[0]["duration"] == pytest.approx(0.5, abs=0.01)
    audio = client.get(f"/api/history/{run_id}/audio")
    assert audio.status_code == 200 and audio.content == r.content


def test_conversation_history_keeps_turns(client):
    turns = [{"voice": "Hải Đăng", "text": "Chào"}, {"voice": None, "text": "Hi"}]
    r = client.post("/api/conversation", json={"turns": turns})
    assert r.status_code == 200
    run = client.get("/api/history").json()["runs"][0]
    assert run["kind"] == "conversation"
    assert run["turns"] == [{"voice": "Hải Đăng", "text": "Chào"}, {"voice": "Hải Đăng", "text": "Hi"}]


def test_history_download_and_delete(client):
    run_id = client.post("/api/tts", json={"text": "a"}).headers["X-History-Id"]
    dl = client.get(f"/api/history/{run_id}/audio?download=1")
    assert "attachment" in dl.headers["content-disposition"]
    assert client.delete(f"/api/history/{run_id}").status_code == 200
    assert client.get(f"/api/history/{run_id}/audio").status_code == 404
    client.post("/api/tts", json={"text": "b"})
    assert client.delete("/api/history").json()["deleted"] == 1


def test_save_voice_then_use_it_for_tts(client):
    r = _save(client, "Giọng Của Sơn")
    assert r.status_code == 200, r.text
    voices = client.get("/api/voices").json()["voices"]
    assert voices[0] == {"id": "Giọng Của Sơn", "label": "Giọng Của Sơn", "custom": True}
    assert {"id": "Hải Đăng", "label": "Hải Đăng", "custom": False} in voices
    mine = client.get("/api/voices/custom").json()["voices"]
    assert [v["name"] for v in mine] == ["Giọng Của Sơn"] and mine[0]["has_clip"]
    assert client.post("/api/tts", json={"text": "hi", "voice": "Giọng Của Sơn"}).status_code == 200
    clip = client.get("/api/voices/custom/clip", params={"name": "Giọng Của Sơn"})
    assert clip.status_code == 200 and clip.content == _wav()


def test_saved_voice_survives_reload(client, tmp_path):
    _save(client, "Bền")
    store = json.loads((tmp_path / "user_voices_v3_turbo.json").read_text(encoding="utf-8"))
    assert "Bền" in store["presets"]
    fresh = _FakeTurbo()
    server.manager._tts = fresh
    server.manager._load_user_voices()
    assert "Bền" in fresh._preset_voices


def test_cannot_shadow_builtin_voice(client):
    r = _save(client, "Hải Đăng")
    assert r.status_code == 400 and "có sẵn" in r.json()["detail"]


def test_rename_voice(client):
    _save(client, "Cũ")
    r = client.patch("/api/voices/custom", json={"old": "Cũ", "new": "Mới"})
    assert r.status_code == 200, r.text
    names = [v["name"] for v in client.get("/api/voices/custom").json()["voices"]]
    assert names == ["Mới"]
    assert client.get("/api/voices/custom/clip", params={"name": "Mới"}).status_code == 200
    # can't rename onto a built-in, can't rename a built-in
    assert client.patch("/api/voices/custom", json={"old": "Mới", "new": "Hải Đăng"}).status_code == 400
    assert client.patch("/api/voices/custom", json={"old": "Hải Đăng", "new": "X"}).status_code == 400


def test_delete_voice(client):
    _save(client, "Tạm")
    assert client.delete("/api/voices/custom", params={"name": "Tạm"}).status_code == 200
    assert client.get("/api/voices/custom").json()["voices"] == []
    assert client.delete("/api/voices/custom", params={"name": "Hải Đăng"}).status_code == 404


def test_library_disabled(client, monkeypatch):
    monkeypatch.setattr(server, "LIBRARY_ENABLED", False)
    assert client.get("/api/history").status_code == 404
    r = client.post("/api/tts", json={"text": "vẫn sinh được"})
    assert r.status_code == 200 and "X-History-Id" not in r.headers
    assert client.get("/api/info").json()["library"] is False


def test_history_write_failure_does_not_break_tts(client, monkeypatch):
    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(server.library, "add_run", boom)
    r = client.post("/api/tts", json={"text": "vẫn ok"})
    assert r.status_code == 200 and r.content[:4] == b"RIFF"


def test_audio_endpoints_accept_query_key(client, monkeypatch):
    run_id = client.post("/api/tts", json={"text": "a"}).headers["X-History-Id"]
    monkeypatch.setattr(server, "API_KEY", "secret")
    assert client.get(f"/api/history/{run_id}/audio").status_code == 401
    assert client.get(f"/api/history/{run_id}/audio?key=secret").status_code == 200
    assert client.get("/api/history").status_code == 401
    assert client.get("/api/history", headers={"X-API-Key": "secret"}).status_code == 200
