"""Training rows -> 2-D token sequences for VieNeu-TTS v3 Turbo (one speaker).

A LoRA here teaches the model ONE voice, so the conditioning is deliberately
minimal: the clip's own speaker embedding and no in-context reference clip. At
inference the voice is called the same way — a speaker embedding enrolled from a
clip of that speaker, no reference codes (``make_voice.py``) — so training and
inference see the same prompt.

A training row is a dict with

    phones            : str            phonemes of the utterance (sea-g2p, as the SDK produces)
    codes             : list[list[int]] (T, n_vq) MOSS codec codes of the utterance
    speaker_embedding : list[float]    192-d x-vector of the clip

``prepare_dataset.py`` writes exactly this layout (parquet).

The model reads one row of ``n_vq + 1`` ids per position: column 0 is the text/slot
token, columns 1..n_vq the audio codes (``audio_pad_token_id`` where there is no audio).
A training sequence is

    [style][TPS] phones... [TPE]          text rows      (audio columns = pad)
    [SGS ] codes of the target, frame 0..T-1
    [EOS ]                                 (audio columns = pad)

which is the prompt the SDK builds at inference time for a voice without reference
codes (``build_prompt_2d(..., ref_codes=None)``) followed by the frames the model has
to produce. The base model was trained with reference dropout, so this no-reference
format is one it already knows.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import torch
from torch.utils.data import Dataset

from vieneu._v3_turbo_engine.prompt_v3_turbo import build_prompt_2d


def load_rows(path: str | Path) -> List[Dict[str, Any]]:
    """Read ``train.parquet`` / ``.jsonl`` into a list of row dicts."""
    path = Path(path)
    if path.suffix == ".parquet":
        import pyarrow.parquet as pq
        return pq.read_table(str(path)).to_pylist()
    if path.suffix == ".jsonl":
        import json
        with open(path, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]
    raise ValueError(f"Unsupported dataset file: {path} (use .parquet or .jsonl)")


class V3TurboLoraDataset(Dataset):
    """Builds one ``(T, n_vq+1)`` sequence per row.

    Args:
        rows: training rows (see module docstring).
        tokenizer: the v3 Turbo tokenizer (phoneme vocabulary).
        config: the model config (token ids, ``n_vq``, style ids).
        max_length: hard cap on sequence length; rows whose target audio cannot fit
            together with the prompt and the EOS row are dropped up front (a truncated
            sequence would lose its EOS and teach the model to never stop).
        style: speaking-style label of the data (``config.style_labels``); the SDK
            always synthesises with the default (natural) style, so keep the default
            unless you know why.
    """

    def __init__(
        self,
        rows: Sequence[Dict[str, Any]],
        tokenizer,
        config,
        max_length: int = 1024,
        style: Optional[str] = None,
    ):
        self.tok, self.cfg = tokenizer, config
        self.n_vq = int(config.n_vq)
        self.audio_pad = int(config.audio_pad_token_id)
        self.text_pad = int(config.pad_token_id)
        self.sgs = int(config.speech_generation_start_token_id)
        self.eos = int(config.speech_generation_end_token_id)
        self.max_length = int(max_length)
        labels = getattr(config, "style_labels", None) or {}
        self.style_id = int(labels.get(style, config.default_style_token_id)) if style else int(config.default_style_token_id)
        self.spk_dim = int(getattr(config, "speaker_embedding_dim", 192))

        # Validate + budget check. Text tokens are counted once here.
        self.rows: List[Dict[str, Any]] = []
        n_bad = n_long = 0
        for r in rows:
            codes, emb = r.get("codes"), r.get("speaker_embedding")
            if not r.get("phones") or not codes or emb is None or len(emb) != self.spk_dim:
                n_bad += 1
                continue
            n_text = len(self.tok.encode(r["phones"], add_special_tokens=False)) + 3   # style, TPS, TPE
            if n_text + len(codes) + 1 > self.max_length:
                n_long += 1
                continue
            self.rows.append(r)
        if n_bad or n_long:
            print(f"[dataset] kept {len(self.rows)} rows; dropped {n_bad} invalid, "
                  f"{n_long} too long for max_length={self.max_length}")
        if not self.rows:
            raise ValueError("No usable training rows.")

    def __len__(self) -> int:
        return len(self.rows)

    def _codes_tensor(self, codes) -> torch.LongTensor:
        t = torch.as_tensor(np.asarray(codes, dtype=np.int64))
        if t.ndim != 2 or t.shape[1] != self.n_vq:
            raise ValueError(f"codes must be (T, {self.n_vq}), got {tuple(t.shape)}")
        return t

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        r = self.rows[idx]
        target = self._codes_tensor(r["codes"])
        prompt = build_prompt_2d(r["phones"], None, self.tok, self.cfg, style_token_id=self.style_id)
        gen = torch.full((target.shape[0], self.n_vq + 1), self.audio_pad, dtype=torch.long)
        gen[:, 0] = self.sgs
        gen[:, 1:] = target
        eos = torch.full((1, self.n_vq + 1), self.audio_pad, dtype=torch.long)
        eos[0, 0] = self.eos
        seq = torch.cat([prompt, gen, eos], dim=0)
        if seq.shape[0] > self.max_length:            # cannot happen after the init budget check
            raise RuntimeError(f"row {idx}: sequence {seq.shape[0]} > max_length {self.max_length}")
        return {
            "input_ids": seq,
            "prompt_len": torch.tensor(int(prompt.shape[0])),
            "speaker_emb": torch.as_tensor(np.asarray(r["speaker_embedding"], dtype=np.float32)),
        }

    def collate(self, items: List[Dict[str, torch.Tensor]]) -> Dict[str, torch.Tensor]:
        return collate_batch(items, text_pad=self.text_pad, audio_pad=self.audio_pad)


def collate_batch(items: List[Dict[str, torch.Tensor]], *, text_pad: int, audio_pad: int) -> Dict[str, torch.Tensor]:
    """Right-pad the sequences of a batch to the longest one."""
    T = max(int(it["input_ids"].shape[0]) for it in items)
    B, W = len(items), int(items[0]["input_ids"].shape[1])
    ids = torch.full((B, T, W), audio_pad, dtype=torch.long)
    ids[:, :, 0] = text_pad
    mask = torch.zeros((B, T), dtype=torch.bool)
    for b, it in enumerate(items):
        n = int(it["input_ids"].shape[0])
        ids[b, :n] = it["input_ids"]
        mask[b, :n] = True
    return {
        "input_ids": ids,
        "attention_mask": mask,
        "prompt_len": torch.stack([it["prompt_len"] for it in items]),
        "speaker_emb": torch.stack([it["speaker_emb"] for it in items]),
    }
