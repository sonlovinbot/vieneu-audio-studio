"""apps.user_voices: save / load / delete the user's cloned voices without a model."""
import numpy as np
import pytest

from apps import user_voices as uv


class _FakeTurbo:
    """Just enough of V3TurboVieNeuTTS for the store: add_voice/remove_voice + the preset dict."""
    default_style = "tu_nhien"

    def __init__(self):
        self._preset_voices = {"Minh Quân": {"description": "nam", "speaker_emb": np.ones(192, np.float32), "codes": np.zeros(10, np.int64)}}
        self._default_voice = "Minh Quân"

    def add_voice(self, name, ref_audio, *, denoise=True, description="", **kw):
        self._preset_voices[name] = {"description": description, "gender": "", "style": self.default_style,
                                     "speaker_emb": np.full(192, 0.5, np.float32), "codes": np.arange(6, dtype=np.int64)}
        return name

    def remove_voice(self, name, save=False):
        self._preset_voices.pop(name, None)

    def list_preset_voices(self):
        return [(n, n) for n in self._preset_voices]


class _FakeV3NanoTTS(_FakeTurbo):
    def add_voice(self, name, ref_audio, *, denoise=True, description="", **kw):
        style = np.full((50, 256), 0.25, np.float32)
        self._preset_voices[name] = {"description": description, "gender": "", "style": style, "codes": style,
                                     "speaker_emb": np.full(192, 0.5, np.float32), "podcast": True}
        return name


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("VIENEU_HOME", str(tmp_path))
    return tmp_path


def test_turbo_roundtrip(home, tmp_path):
    tts = _FakeTurbo()
    wav = tmp_path / "ref.wav"; wav.write_bytes(b"x")
    assert uv.save_user_voice(tts, " Anh Tuấn ", str(wav), description="trầm") == "Anh Tuấn"
    assert uv.list_user_voices(tts) == ["Anh Tuấn"]
    assert (home / "user_voices_v3_turbo.json").is_file()

    fresh = _FakeTurbo()
    assert uv.load_user_voices(fresh) == ["Anh Tuấn"]
    e = fresh._preset_voices["Anh Tuấn"]
    assert e["description"] == "trầm" and e[uv.USER_MARK] and e["podcast"] is True
    assert e["speaker_emb"].dtype == np.float32 and e["speaker_emb"].shape == (192,)
    assert e["codes"].dtype == np.int64 and e["codes"].tolist() == [0, 1, 2, 3, 4, 5]
    assert "Minh Quân" in fresh._preset_voices           # built-ins untouched

    uv.delete_user_voice(fresh, "Anh Tuấn")
    assert uv.list_user_voices(fresh) == []
    assert uv.load_user_voices(_FakeTurbo()) == []


def test_nano_roundtrip(home, tmp_path):
    tts = _FakeV3NanoTTS()
    wav = tmp_path / "ref.wav"; wav.write_bytes(b"x")
    uv.save_user_voice(tts, "Bé Na", str(wav))
    assert (home / "user_voices_v3_nano.json").is_file()
    fresh = _FakeV3NanoTTS()
    assert uv.load_user_voices(fresh) == ["Bé Na"]
    e = fresh._preset_voices["Bé Na"]
    assert e["style"].shape == (50, 256) and e["codes"] is e["style"]
    assert e["description"] == uv.DEFAULT_DESC


def test_validation(home, tmp_path):
    tts = _FakeTurbo()
    wav = tmp_path / "ref.wav"; wav.write_bytes(b"x")
    with pytest.raises(ValueError):
        uv.save_user_voice(tts, "", str(wav))
    with pytest.raises(ValueError):                     # built-in name is protected
        uv.save_user_voice(tts, "Minh Quân", str(wav))
    with pytest.raises(ValueError):
        uv.save_user_voice(tts, "X", None)
    with pytest.raises(ValueError):                     # cannot delete a built-in
        uv.delete_user_voice(tts, "Minh Quân")
    uv.save_user_voice(tts, "X", str(wav))
    uv.save_user_voice(tts, "X", str(wav), description="v2")   # re-save own voice = replace
    assert tts._preset_voices["X"]["description"] == "v2"


def test_broken_file_is_ignored(home):
    (home / "user_voices_v3_turbo.json").write_text("{not json", encoding="utf-8")
    assert uv.load_user_voices(_FakeTurbo()) == []


def test_unsupported_model(home):
    class Old:  # v2: no add_voice
        _preset_voices = {}
    assert uv.load_user_voices(Old()) == []
    with pytest.raises(ValueError):
        uv.save_user_voice(Old(), "A", "x.wav")


def test_voice_aliases_resolve_to_renamed_preset():
    """Renamed presets ("Minh Quân" → "Minh Quân Pro" → "Hải Đăng", "Anh Khôi" →
    "Thiện Minh", "Mạnh Dũng" → "Quốc Tuấn"): old names must keep working
    everywhere a voice name is accepted, without showing up as a second voice."""
    from vieneu.v3turbo import V3TurboVieNeuTTS
    import numpy as np

    tts = V3TurboVieNeuTTS.__new__(V3TurboVieNeuTTS)
    tts._preset_voices, tts._voice_aliases, tts.default_style = {}, {}, "tu_nhien"
    tts._load_v3_voices()
    assert tts._default_voice == "Hải Đăng"
    renames = {"Minh Quân": "Hải Đăng", "Minh Quân Pro": "Hải Đăng",
               "Anh Khôi": "Thiện Minh", "Mạnh Dũng": "Quốc Tuấn"}
    ids = [v for _, v in tts.list_preset_voices()]
    for old, new in renames.items():
        assert tts.resolve_voice_name(old) == new
        assert tts.resolve_voice_name(new) == new
        assert tts.get_preset_voice(old) is tts.get_preset_voice(new)
        assert new in ids and old not in ids
    assert tts.resolve_voice_name("Không Có") is None
    assert np.array_equal(tts._resolve_ref("Minh Quân Pro", None, True, True)[0],
                          tts._resolve_ref(None, None, True, True)[0])
