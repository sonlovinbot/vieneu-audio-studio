"""LoRA adapters for VieNeu-TTS v3 Turbo (PEFT).

By default the adapters go on the attention and MLP projections of the backbone; the
acoustic decoder, embeddings and the speaker projection stay frozen (``target="all"``
also adapts the acoustic decoder). ``unfreeze`` lets you fully train a few named
sub-modules on top (e.g. ``["xvec_proj"]``) — those weights are then saved next to the
adapter and applied again by :func:`load_adapter`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional, Sequence

import torch

_BACKBONE = r"semantic_backbone\.layers\.\d+\.(self_attn\.(q_proj|k_proj|v_proj|o_proj)|mlp\.(gate_proj|up_proj|down_proj))"
_ACOUSTIC = r"acoustic_decoder\.layers\.\d+\.(attn\.(qkv|o_proj)|ff_gate|ff_up|ff_down)"
TARGETS = {"backbone": _BACKBONE, "all": f"({_BACKBONE}|{_ACOUSTIC})"}
_EXTRA_FILE = "extra_trainable.safetensors"


def attach_lora(model, *, r: int = 16, alpha: int = 32, dropout: float = 0.05,
                target: str = "backbone", unfreeze: Sequence[str] = ()):
    """Wrap ``model`` in a PEFT model with LoRA layers injected in place.

    The returned PeftModel owns saving/merging; the original ``model`` object keeps
    working for the custom training forward (its Linear layers are now LoRA layers).
    """
    from peft import LoraConfig, get_peft_model
    pattern = TARGETS.get(target, target)           # a custom regex is accepted too
    cfg = LoraConfig(r=r, lora_alpha=alpha, lora_dropout=dropout, bias="none",
                     target_modules=pattern, task_type=None)
    peft_model = get_peft_model(model, cfg)
    for name in unfreeze:
        mod = model.get_submodule(name)
        for p in mod.parameters():
            p.requires_grad_(True)
    peft_model._vieneu_unfreeze = list(unfreeze)
    return peft_model


def trainable_parameters(model) -> Iterable[torch.nn.Parameter]:
    return (p for p in model.parameters() if p.requires_grad)


def lora_state_dict(peft_model) -> dict:
    from peft import get_peft_model_state_dict
    return get_peft_model_state_dict(peft_model)


def save_adapter(peft_model, out_dir: str | Path, tokenizer=None) -> Path:
    """Write ``adapter_config.json`` + ``adapter_model.safetensors`` (+ unfrozen extras)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    peft_model.save_pretrained(str(out))
    extras = getattr(peft_model, "_vieneu_unfreeze", []) or []
    if extras:
        from safetensors.torch import save_file
        base = peft_model.base_model.model
        sd = {}
        for name in extras:
            for k, v in base.get_submodule(name).state_dict().items():
                sd[f"{name}.{k}"] = v.detach().to("cpu").contiguous()
        save_file(sd, str(out / _EXTRA_FILE))
        (out / "extra_trainable.json").write_text(json.dumps(extras), encoding="utf-8")
    if tokenizer is not None:
        tokenizer.save_pretrained(str(out))
    return out


def load_adapter(model, adapter_dir: str | Path):
    """Attach a saved adapter (and unfrozen extras) to a freshly loaded base model."""
    from peft import PeftModel
    adapter_dir = Path(adapter_dir)
    peft_model = PeftModel.from_pretrained(model, str(adapter_dir))
    extra_json = adapter_dir / "extra_trainable.json"
    if extra_json.is_file():
        from safetensors.torch import load_file
        sd = load_file(str(adapter_dir / _EXTRA_FILE))
        missing, unexpected = model.load_state_dict(sd, strict=False)
        if unexpected:
            raise RuntimeError(f"extra_trainable has unknown keys: {unexpected[:5]}")
    return peft_model


def merge_lora_into(peft_model):
    """Fold the adapters into the base weights and return the plain model."""
    return peft_model.merge_and_unload()


# Weights that alias another tensor (tied embeddings/heads) — not stored, re-tied on load.
_TIED = ("text_lm_head.weight", "semantic_backbone.embed_tokens.weight")


def export_merged(model, tokenizer, base_repo: str, out_dir: str | Path, *, subfolder: str = "update",
                  dtype: torch.dtype = torch.bfloat16) -> Path:
    """Write a merged model in the same layout as the official repo, loadable with
    ``Vieneu(mode="v3turbo", backbone_repo=<out_dir>)`` (PyTorch/GPU backend)::

        out_dir/
          config.json, speaker_encoder.onnx, denoiser.onnx     (copied from the base repo)
          <subfolder>/config.json, model.safetensors, tokenizer files
    """
    from safetensors.torch import save_file
    out = Path(out_dir)
    sub = out / subfolder if subfolder else out
    sub.mkdir(parents=True, exist_ok=True)
    sd = {}
    for k, v in model.state_dict().items():
        if k in _TIED or k.startswith("audio_lm_heads."):
            continue
        sd[k] = v.detach().to("cpu", dtype if v.is_floating_point() else v.dtype).contiguous()
    save_file(sd, str(sub / "model.safetensors"), metadata={"format": "pt"})
    model.config.save_pretrained(str(sub))
    if tokenizer is not None:
        tokenizer.save_pretrained(str(sub))
    # Root files the SDK reads next to the weights (voice cloning + download counter).
    base = Path(base_repo)
    for fn in ("config.json", "speaker_encoder.onnx", "denoiser.onnx"):
        try:
            if base.is_dir():
                src = base / fn
                if not src.is_file():
                    continue
            else:
                from huggingface_hub import hf_hub_download
                src = Path(hf_hub_download(base_repo, fn))
            import shutil
            shutil.copyfile(src, out / fn)
        except Exception as e:                       # optional extras; cloning may just lack them
            print(f"  (skip {fn}: {e})")
    return out
