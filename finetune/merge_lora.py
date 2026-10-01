"""Merge a LoRA adapter into the base weights and export a ready-to-use model folder.

    uv run python finetune/merge_lora.py --adapter finetune/output/my_voice/adapter --out finetune/output/my_voice/merged
    # optional: --push-to-hub your-name/VieNeu-TTS-v3-Turbo-my-voice [--private]

The output folder mirrors the official repo layout, so it works as
``Vieneu(mode="v3turbo", backbone_repo="finetune/output/my_voice/merged")`` on the
PyTorch/GPU backend, or as ``backbone_repo="your-name/…"`` after pushing it to the Hub.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "finetune"))

from vieneu_lora.lora import export_merged, load_adapter, merge_lora_into   # noqa: E402
from vieneu_lora.utils import safe_path                                     # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--adapter", required=True, help="adapter folder written by train_lora.py")
    ap.add_argument("--out", required=True, help="output folder for the merged model")
    ap.add_argument("--base", default="pnnbao-ump/VieNeu-TTS-v3-Turbo")
    ap.add_argument("--subfolder", default="update")
    ap.add_argument("--push-to-hub", default=None, help="HF repo id to upload the merged folder to")
    ap.add_argument("--private", action="store_true")
    args = ap.parse_args()

    from transformers import AutoTokenizer
    from vieneu._v3_turbo_engine.hub_load_v3_turbo import load_v3_turbo_checkpoint
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"loading base {args.base}/{args.subfolder} on {device} ...")
    tokenizer = AutoTokenizer.from_pretrained(args.base, subfolder=args.subfolder or "", trust_remote_code=True)
    model = load_v3_turbo_checkpoint(args.base, subfolder=args.subfolder or None, device=device, dtype=torch.float32)
    peft_model = load_adapter(model, safe_path(args.adapter))
    merged = merge_lora_into(peft_model)
    out = export_merged(merged, tokenizer, args.base, safe_path(args.out), subfolder=args.subfolder)
    print(f"merged model written to {out}")

    if args.push_to_hub:
        from huggingface_hub import HfApi
        api = HfApi()
        api.create_repo(args.push_to_hub, repo_type="model", private=args.private, exist_ok=True)
        api.upload_folder(repo_id=args.push_to_hub, folder_path=str(out), repo_type="model",
                          commit_message="VieNeu-TTS v3 Turbo LoRA fine-tune (merged)")
        print(f"pushed to https://huggingface.co/{args.push_to_hub}")


if __name__ == "__main__":
    main()
