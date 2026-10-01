import numpy as np
from vieneu_utils.core_utils import syllable_count, count_speech_bursts, babble_suspect, babble_prefer, max_expected_frames, is_cue_only


def _tone(sr, dur, f=180.0, amp=0.3):
    t = np.arange(int(sr * dur)) / sr
    return (amp * np.sin(2 * np.pi * f * t)).astype(np.float32)


def _silence(sr, dur):
    return np.zeros(int(sr * dur), dtype=np.float32)


def test_syllable_count_vietnamese_and_english():
    assert syllable_count("tʃˈaː2w.") == 1                      # Chào.
    assert syllable_count("ɗˌyə6c xˌoŋ.") == 2                  # Được không?
    assert syllable_count("kˈə4n tˈə6n.") == 2                  # Cẩn thận.
    assert syllable_count("sˈækaɪ, ɲˈə6t̪ bˈaː4n.") == 4         # Sakai (2) Nhật Bản
    assert syllable_count("ŋˈɛ hˈaj kwˈaːɜ <|emotion_1|>.") == 3  # markup ignored
    assert syllable_count("") == 0


def test_count_speech_bursts():
    sr = 16000
    one = np.concatenate([_silence(sr, 0.05), _tone(sr, 0.25), _silence(sr, 0.3)])
    assert count_speech_bursts(one, sr) == 1
    two = np.concatenate([_silence(sr, 0.05), _tone(sr, 0.25), _silence(sr, 0.15), _tone(sr, 0.2), _silence(sr, 0.2)])
    assert count_speech_bursts(two, sr) == 2
    # a 30 ms dip inside a syllable (aspirated onset) must not split the burst
    joined = np.concatenate([_tone(sr, 0.08), _silence(sr, 0.03), _tone(sr, 0.2)])
    assert count_speech_bursts(joined, sr) == 1
    # a quiet breath (-30 dB) after the word is not a burst
    breath = np.concatenate([_tone(sr, 0.25), _silence(sr, 0.1), _tone(sr, 0.15, amp=0.3 * 10 ** (-30 / 20))])
    assert count_speech_bursts(breath, sr) == 1
    assert count_speech_bursts(_silence(sr, 0.5), sr) == 0


def test_babble_suspect_rules():
    sr = 48000
    word = np.concatenate([_silence(sr, 0.05), _tone(sr, 0.25), _silence(sr, 0.2)])
    assert babble_suspect(word, sr, "tʃˈaː2w.", 13, 6)[0] is False        # 1 syllable, 1 burst, EOS early
    assert babble_suspect(word, sr, "tʃˈaː2w.", 13, 13)[0] is True        # same audio but ran to the cap
    two = np.concatenate([_tone(sr, 0.2), _silence(sr, 0.15), _tone(sr, 0.2)])
    assert babble_suspect(two, sr, "tʃˈaː2w.", 13, 7)[0] is True          # 1 syllable, 2 bursts
    assert babble_suspect(two, sr, "a b c d e", 40, 39)[0] is False       # long chunks never checked
    assert babble_suspect(two, sr, "tʃˈaː2w <|emotion_1|>", 13, 13)[0] is False
    assert babble_prefer((False, 1, 1, 7), (True, 1, 2, 13))
    assert not babble_prefer((True, 1, 2, 9), (False, 1, 1, 7))
    assert babble_prefer((False, 1, 1, 6), (False, 1, 1, 8))


def test_frame_cap_by_syllables_not_words():
    assert max_expected_frames("tʃˈaː2w.") == 13                   # Chào. (1 syllable)
    assert max_expected_frames("ˌoʊkˈeɪ.") == 18                  # OK. (1 word, 2 syllables)
    assert max_expected_frames("kˈə4n tˈə6n.") == 18              # Cẩn thận. (2 words, 2 syllables)
    assert max_expected_frames("nˌoʊɾɪfɪkˈeɪʃən.") > 13           # notification. (5 syllables): phoneme formula
    assert max_expected_frames("nˌoʊɾɪfɪkˈeɪʃən.") == 24 + 2 * len("nˌoʊɾɪfɪkˈeɪʃən.")
    assert max_expected_frames("tʃˈaː2w <|emotion_1|>") > 13     # emotion cue: no syllable cap


def test_standalone_cue_capped_like_one_syllable():
    sr = 48000
    assert is_cue_only("<|emotion_1|>.")
    assert not is_cue_only("tʃˈaː2w <|emotion_1|>.")
    assert max_expected_frames("<|emotion_1|>.") == 13           # [cười] alone: ~1 s cap
    assert max_expected_frames("<|emotion_2|>") == 13            # [thở dài] alone
    assert max_expected_frames("tʃˈaː2w <|emotion_1|>.") > 13    # word + cue: phoneme formula
    laugh = _tone(sr, 0.6)
    assert babble_suspect(laugh, sr, "<|emotion_1|>.", 13, 8)[0] is False   # natural laugh, EOS early
    assert babble_suspect(laugh, sr, "<|emotion_1|>.", 13, 13)[0] is True   # ran to the cap: regenerate
    assert babble_suspect(laugh, sr, "tʃˈaː2w <|emotion_1|>.", 42, 42)[0] is False  # mixed: not checked
