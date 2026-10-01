"""Teacher-forcing forward pass and loss for VieNeu-TTS v3 Turbo.

The SDK ships the network for inference only (``VieNeuV3TurboForTTS``); this module adds
the training-time path on top of its public sub-modules:

    backbone  (``semantic_backbone``)  reads the whole 2-D sequence,
    acoustic decoder                    turns each backbone state into the next frame's
                                        text token + n_vq audio codes, one codebook at a time.

Position ``t`` of the backbone predicts row ``t+1``: the acoustic decoder is fed row
``t+1``'s own tokens as teacher input (text token, then codebooks 0..n_vq-2) and its
outputs are scored against that same row (codebooks 0..n_vq-1 and the text token,
which is where the model learns to emit EOS).
"""
from __future__ import annotations

from typing import Dict, Tuple

import torch
import torch.nn.functional as F

IGNORE = -100


def forward_train(
    model,
    input_ids: torch.LongTensor,          # (B, T, n_vq+1) rows 0..T-1
    attention_mask: torch.Tensor,         # (B, T) bool
    text_labels: torch.LongTensor,        # (B, T) text token of row t+1  (IGNORE where masked)
    audio_labels: torch.LongTensor,       # (B, T, n_vq) audio codes of row t+1 (IGNORE where masked)
    speaker_emb: torch.Tensor,            # (B, 192)
) -> Tuple[torch.Tensor, list]:
    """Return ``(text_logits (B*T, V_text), [audio_logits_ch (B*T, V_audio)] * n_vq)``."""
    cfg = model.config
    n_vq, H = int(cfg.n_vq), int(cfg.hidden_size)

    embeds = model._build_inputs_embeds(input_ids, speaker_emb=speaker_emb)
    hidden = model.semantic_backbone(inputs_embeds=embeds, attention_mask=attention_mask,
                                     use_cache=False, return_dict=True).last_hidden_state
    B, T, _ = hidden.shape
    N = B * T
    ldtype = next(model.acoustic_decoder.parameters()).dtype

    # Acoustic decoder input: slot 0 = backbone state, slot 1 = next row's text token,
    # slots 2.. = next row's codebooks 0..n_vq-2 (teacher forcing).
    local_in = torch.zeros(N, n_vq + 1, H, dtype=ldtype, device=hidden.device)
    local_in[:, 0] = hidden.reshape(N, H).to(ldtype)
    txt = text_labels.reshape(N)
    local_in[:, 1] = model.text_embeddings(txt.masked_fill(txt < 0, int(cfg.pad_token_id))).to(ldtype)
    for ch in range(n_vq - 1):
        ids = audio_labels[:, :, ch].reshape(N)
        ok = (ids >= 0) & (ids < int(cfg.audio_vocab_size))
        emb = model.audio_embeddings[ch](ids.masked_fill(~ok, 0)).to(ldtype)
        local_in[:, ch + 2] = emb * ok.unsqueeze(-1)

    out = model.acoustic_decoder(local_in)                     # (N, n_vq+1, H)
    text_logits = model.text_lm_head(out[:, 0])
    audio_logits = [model.audio_lm_heads[ch](out[:, ch + 1]) for ch in range(n_vq)]
    return text_logits, audio_logits


def make_labels(batch: Dict[str, torch.Tensor], cfg) -> Tuple[torch.LongTensor, torch.LongTensor]:
    """Shift the sequence by one row and mask prompt / padding / non-audio rows."""
    ids, mask, plen = batch["input_ids"], batch["attention_mask"], batch["prompt_len"]
    text_labels = ids[:, 1:, 0].clone()
    audio_labels = ids[:, 1:, 1:].clone()
    for b in range(ids.shape[0]):
        keep_from = max(0, int(plen[b]) - 1)                 # first supervised row = first gen row
        text_labels[b, :keep_from] = IGNORE
        audio_labels[b, :keep_from] = IGNORE
    m = mask[:, 1:]
    text_labels = text_labels.masked_fill(~m, IGNORE)
    audio_labels = audio_labels.masked_fill(~m.unsqueeze(-1), IGNORE)
    audio_labels = audio_labels.masked_fill(audio_labels >= int(cfg.audio_vocab_size), IGNORE)  # EOS/pad rows
    return text_labels, audio_labels


def compute_loss(
    model,
    batch: Dict[str, torch.Tensor],
    text_loss_weight: float = 1.0,
    audio_loss_weight: float = 8.0,
) -> Tuple[torch.Tensor, Dict[str, float]]:
    """Weighted cross-entropy over the text channel and the n_vq audio codebooks.

    Returns ``(loss, metrics)`` where metrics holds the un-weighted text / audio losses
    and the top-1 accuracy of codebook 0 (a quick sanity signal: it should be well
    above chance from the very first step on a correct pipeline).
    """
    cfg = model.config
    text_labels, audio_labels = make_labels(batch, cfg)
    text_logits, audio_logits = forward_train(
        model, batch["input_ids"][:, :-1], batch["attention_mask"][:, :-1],
        text_labels, audio_labels, batch["speaker_emb"],
    )
    N = text_labels.numel()
    text_loss = F.cross_entropy(text_logits.float(), text_labels.reshape(N), ignore_index=IGNORE)
    audio_losses = []
    for ch, logits in enumerate(audio_logits):
        audio_losses.append(F.cross_entropy(logits.float(), audio_labels[:, :, ch].reshape(N), ignore_index=IGNORE))
    audio_loss = torch.stack(audio_losses).mean()
    loss = (text_loss_weight * text_loss + audio_loss_weight * audio_loss) / (text_loss_weight + audio_loss_weight)

    with torch.no_grad():
        lab0 = audio_labels[:, :, 0].reshape(N)
        ok = lab0 != IGNORE
        acc0 = (audio_logits[0].argmax(-1)[ok] == lab0[ok]).float().mean().item() if ok.any() else 0.0
    return loss, {"text_loss": text_loss.item(), "audio_loss": audio_loss.item(), "acc_cb0": acc0}
