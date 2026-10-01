"""finetune/vieneu_lora — sequence + label construction. Run by tests/test_finetune_lora.py
in a fresh interpreter (the main test suite stubs `torch`, which these tests need for real)."""
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

torch = pytest.importorskip("torch")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vieneu_lora.data import V3TurboLoraDataset, collate_batch   # noqa: E402
from vieneu_lora.model import IGNORE, make_labels                # noqa: E402

N_VQ, V_AUDIO = 4, 50
CFG = SimpleNamespace(
    n_vq=N_VQ, audio_vocab_size=V_AUDIO, audio_pad_token_id=V_AUDIO, pad_token_id=0,
    text_prompt_start_token_id=3, text_prompt_end_token_id=4,
    speech_generation_start_token_id=5, speech_generation_end_token_id=6,
    audio_ref_slot_token_id=7, default_style_token_id=16, style_labels={"tu_nhien": 16, "tin_tuc": 17},
    speaker_embedding_dim=8,
)


class _Tok:
    def encode(self, s, add_special_tokens=False):
        return [20 + (ord(c) % 50) for c in s]


def _row(n_frames, phones="ab c"):
    rng = np.random.default_rng(n_frames)
    return {"phones": phones,
            "codes": rng.integers(0, V_AUDIO, size=(n_frames, N_VQ)).tolist(),
            "speaker_embedding": [0.1] * 8}


def test_sequence_layout():
    ds = V3TurboLoraDataset([_row(5)], _Tok(), CFG, max_length=64)
    it = ds[0]
    ids = it["input_ids"]
    n_text = len(_Tok().encode("ab c")) + 3
    assert int(it["prompt_len"]) == n_text
    assert ids[0, 0] == 16 and ids[1, 0] == 3 and ids[n_text - 1, 0] == 4     # style, TPS, ..., TPE
    assert (ids[:n_text, 1:] == V_AUDIO).all()                               # text rows carry no audio
    assert (ids[n_text:n_text + 5, 0] == 5).all()                             # gen rows = SGS
    assert (ids[n_text:n_text + 5, 1:] < V_AUDIO).all()
    assert ids[-1, 0] == 6 and (ids[-1, 1:] == V_AUDIO).all()                 # EOS row
    assert ids.shape == (n_text + 5 + 1, N_VQ + 1)


def test_no_reference_rows_ever():
    """One-speaker LoRA: the prompt is text only, never an in-context reference."""
    rows = [_row(5), _row(40), _row(6)]
    ds = V3TurboLoraDataset(rows, _Tok(), CFG, max_length=128)
    for i in range(len(ds)):
        it = ds[i]
        assert (it["input_ids"][:, 0] == 7).sum() == 0                         # no REF slot rows
        assert int(it["prompt_len"]) == len(_Tok().encode("ab c")) + 3


def test_too_long_rows_are_dropped_not_truncated():
    ds = V3TurboLoraDataset([_row(5), _row(200)], _Tok(), CFG, max_length=64)
    assert len(ds) == 1


def test_labels_supervise_only_target_frames_and_eos():
    ds = V3TurboLoraDataset([_row(5), _row(3)], _Tok(), CFG, max_length=64)
    batch = collate_batch([ds[0], ds[1]], text_pad=0, audio_pad=V_AUDIO)
    text_labels, audio_labels = make_labels(batch, CFG)
    ids = batch["input_ids"]
    for b in range(2):
        p = int(batch["prompt_len"][b])
        n_gen = 5 if b == 0 else 3
        assert (text_labels[b, :p - 1] == IGNORE).all()                       # prompt not supervised
        assert (text_labels[b, p - 1:p - 1 + n_gen] == 5).all()              # predicts SGS rows ...
        assert text_labels[b, p - 1 + n_gen] == 6                             # ... then EOS
        assert (text_labels[b, p + n_gen:] == IGNORE).all()                   # padding masked
        assert (audio_labels[b, p - 1:p - 1 + n_gen] == ids[b, p:p + n_gen, 1:]).all()
        assert (audio_labels[b, p - 1 + n_gen] == IGNORE).all()               # EOS row has no audio target
    assert batch["attention_mask"].shape == ids.shape[:2]
    assert batch["attention_mask"][1].sum() == ids.shape[1] - (5 - 3)
