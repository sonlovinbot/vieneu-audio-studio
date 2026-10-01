"""LoRA fine-tuning of VieNeu-TTS v3 Turbo on ONE voice.

The dataset is one speaker (see prepare_dataset.py); the model is conditioned on the
speaker embedding only, with no in-context reference clip, so the merged model speaks
the voice from `voice="<name>"` enrolled with make_voice.py (embedding, no reference codes).

    uv run python finetune/train_lora.py --data finetune/dataset/train.parquet --run my_voice

Needs a CUDA GPU (≈6 GB for the defaults) and the ``finetune`` extra:
``uv sync --extra finetune`` (torch, transformers, peft, datasets, accelerate).

Outputs (under ``--output-dir/<run>``):
    adapter/            LoRA adapter (PEFT layout) — small, load it with merge_lora.py
    checkpoint-*/       intermediate adapters
    merged/             full model ready for ``Vieneu(mode="v3turbo", backbone_repo="…/merged")``
                        (written when --merge is set)
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "finetune"))

from vieneu_lora import (V3TurboLoraDataset, attach_lora, compute_loss, load_rows, save_adapter)   # noqa: E402
from vieneu_lora.lora import export_merged, merge_lora_into, trainable_parameters               # noqa: E402
from vieneu_lora.utils import safe_path                                                          # noqa: E402


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="train.parquet from prepare_dataset.py (or .jsonl)")
    ap.add_argument("--run", default="lora_run", help="run name (sub-folder of --output-dir)")
    ap.add_argument("--output-dir", default=str(ROOT / "finetune" / "output"))
    ap.add_argument("--base", default="pnnbao-ump/VieNeu-TTS-v3-Turbo")
    ap.add_argument("--subfolder", default="update", help="weights sub-folder inside --base")
    # LoRA
    ap.add_argument("--r", type=int, default=16)
    ap.add_argument("--alpha", type=int, default=32)
    ap.add_argument("--dropout", type=float, default=0.05)
    ap.add_argument("--target", default="backbone", help="'backbone' (default), 'all' (+acoustic decoder) or a regex")
    ap.add_argument("--unfreeze", default="", help="comma-separated sub-modules to train fully, e.g. xvec_proj")
    # data
    ap.add_argument("--max-length", type=int, default=1024)
    ap.add_argument("--eval-ratio", type=float, default=0.03)
    # optimisation
    ap.add_argument("--batch-size", type=int, default=4)
    ap.add_argument("--grad-accum", type=int, default=4)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--weight-decay", type=float, default=0.01)
    ap.add_argument("--epochs", type=float, default=3.0)
    ap.add_argument("--max-steps", type=int, default=0, help="stop after this many optimizer steps (0 = use --epochs)")
    ap.add_argument("--warmup-ratio", type=float, default=0.05)
    ap.add_argument("--max-grad-norm", type=float, default=1.0)
    ap.add_argument("--text-loss-weight", type=float, default=1.0)
    ap.add_argument("--audio-loss-weight", type=float, default=8.0)
    ap.add_argument("--grad-checkpoint", action="store_true", help="backbone gradient checkpointing (less VRAM)")
    ap.add_argument("--no-bf16", action="store_true", help="disable bf16 autocast")
    # bookkeeping
    ap.add_argument("--log-every", type=int, default=10)
    ap.add_argument("--eval-every", type=int, default=100)
    ap.add_argument("--save-every", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--merge", action="store_true", help="also write the merged full model at the end")
    ap.add_argument("--num-workers", type=int, default=2)
    return ap.parse_args()


@torch.no_grad()
def evaluate(model, loader, device, autocast, args):
    model.eval()
    tot, n, acc = 0.0, 0, 0.0
    for batch in loader:
        batch = {k: v.to(device) for k, v in batch.items()}
        with autocast():
            loss, m = compute_loss(model, batch, args.text_loss_weight, args.audio_loss_weight)
        tot += loss.item(); acc += m["acc_cb0"]; n += 1
    model.train()
    return (tot / max(n, 1), acc / max(n, 1))


def main() -> None:
    args = parse_args()
    rng = np.random.default_rng(args.seed); torch.manual_seed(args.seed)
    if not torch.cuda.is_available():
        raise SystemExit("LoRA training needs a CUDA GPU.")
    device = torch.device("cuda")
    out_dir = safe_path(Path(args.output_dir) / args.run)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "train_args.json").write_text(json.dumps(vars(args), indent=1), encoding="utf-8")

    # ── model + tokenizer (fp32 master weights, bf16 autocast for compute) ──
    from transformers import AutoTokenizer, get_scheduler
    from vieneu._v3_turbo_engine.hub_load_v3_turbo import load_v3_turbo_checkpoint
    print(f"loading {args.base}/{args.subfolder} ...")
    tokenizer = AutoTokenizer.from_pretrained(args.base, subfolder=args.subfolder or "", trust_remote_code=True)
    model = load_v3_turbo_checkpoint(args.base, subfolder=args.subfolder or None, device=device, dtype=torch.float32)
    model.config.use_cache = False
    for p in model.parameters():
        p.requires_grad_(False)
    if args.grad_checkpoint:
        model.semantic_backbone.gradient_checkpointing_enable()
    unfreeze = [s.strip() for s in args.unfreeze.split(",") if s.strip()]
    peft_model = attach_lora(model, r=args.r, alpha=args.alpha, dropout=args.dropout,
                             target=args.target, unfreeze=unfreeze)
    n_train = sum(p.numel() for p in trainable_parameters(model))
    n_all = sum(p.numel() for p in model.parameters())
    print(f"trainable params: {n_train/1e6:.2f}M / {n_all/1e6:.1f}M ({100*n_train/n_all:.2f}%)  target={args.target} unfreeze={unfreeze}")

    # ── data ──
    rows = load_rows(safe_path(args.data))
    rng.shuffle(rows)
    n_eval = max(1, int(len(rows) * args.eval_ratio)) if len(rows) >= 20 else 0
    eval_rows, train_rows = rows[:n_eval], rows[n_eval:]
    mk = lambda rs: V3TurboLoraDataset(rs, tokenizer, model.config, max_length=args.max_length)
    train_ds = mk(train_rows)
    eval_ds = mk(eval_rows) if eval_rows else None
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, drop_last=False,
                              num_workers=args.num_workers, collate_fn=train_ds.collate, pin_memory=True)
    eval_loader = (DataLoader(eval_ds, batch_size=args.batch_size, shuffle=False, collate_fn=eval_ds.collate)
                   if eval_ds else None)
    steps_per_epoch = math.ceil(len(train_loader) / args.grad_accum)
    total_steps = args.max_steps or math.ceil(args.epochs * steps_per_epoch)
    print(f"train rows {len(train_ds)} | eval rows {len(eval_ds) if eval_ds else 0} | "
          f"{steps_per_epoch} steps/epoch | {total_steps} total steps | effective batch {args.batch_size * args.grad_accum}")

    # ── optimiser ──
    optim = torch.optim.AdamW(list(trainable_parameters(model)), lr=args.lr, weight_decay=args.weight_decay, betas=(0.9, 0.95))
    sched = get_scheduler("cosine", optim, num_warmup_steps=math.ceil(total_steps * args.warmup_ratio), num_training_steps=total_steps)
    use_bf16 = not args.no_bf16
    autocast = lambda: torch.autocast("cuda", dtype=torch.bfloat16, enabled=use_bf16)

    if eval_loader:
        l0, a0 = evaluate(model, eval_loader, device, autocast, args)
        print(f"[eval] step 0  loss {l0:.4f}  acc_cb0 {a0:.3f}")

    # ── loop ──
    model.train()
    step, micro, t0, done = 0, 0, time.perf_counter(), False
    run_loss, run_m = 0.0, {"text_loss": 0.0, "audio_loss": 0.0, "acc_cb0": 0.0}
    log = open(out_dir / "train_log.jsonl", "a", encoding="utf-8")
    while not done:
        for batch in train_loader:
            batch = {k: v.to(device, non_blocking=True) for k, v in batch.items()}
            with autocast():
                loss, m = compute_loss(model, batch, args.text_loss_weight, args.audio_loss_weight)
            (loss / args.grad_accum).backward()
            run_loss += loss.item() / args.grad_accum
            for k in run_m:
                run_m[k] += m[k] / args.grad_accum
            micro += 1
            if micro % args.grad_accum:
                continue
            if args.max_grad_norm > 0:
                torch.nn.utils.clip_grad_norm_(list(trainable_parameters(model)), args.max_grad_norm)
            optim.step(); sched.step(); optim.zero_grad(set_to_none=True)
            step += 1
            if step % args.log_every == 0 or step == 1:
                rec = {"step": step, "loss": round(run_loss / min(step, 1) if step == 1 else run_loss / args.log_every, 4),
                       "lr": sched.get_last_lr()[0], "elapsed_s": round(time.perf_counter() - t0)}
                rec.update({k: round(v / (1 if step == 1 else args.log_every), 4) for k, v in run_m.items()})
                print(f"step {step}/{total_steps}  loss {rec['loss']:.4f}  text {rec['text_loss']:.3f}  "
                      f"audio {rec['audio_loss']:.3f}  acc_cb0 {rec['acc_cb0']:.3f}  lr {rec['lr']:.2e}  {rec['elapsed_s']}s")
                log.write(json.dumps(rec) + "\n"); log.flush()
                run_loss, run_m = 0.0, {k: 0.0 for k in run_m}
            if eval_loader and step % args.eval_every == 0:
                le, ae = evaluate(model, eval_loader, device, autocast, args)
                print(f"[eval] step {step}  loss {le:.4f}  acc_cb0 {ae:.3f}")
                log.write(json.dumps({"step": step, "eval_loss": round(le, 4), "eval_acc_cb0": round(ae, 4)}) + "\n"); log.flush()
            if step % args.save_every == 0 and step < total_steps:
                save_adapter(peft_model, out_dir / f"checkpoint-{step}", tokenizer)
            if step >= total_steps:
                done = True
                break

    save_adapter(peft_model, out_dir / "adapter", tokenizer)
    if eval_loader:
        le, ae = evaluate(model, eval_loader, device, autocast, args)
        print(f"[eval] final  loss {le:.4f}  acc_cb0 {ae:.3f}")
    print(f"adapter saved to {out_dir / 'adapter'}")
    if args.merge:
        merged = merge_lora_into(peft_model)
        export_merged(merged, tokenizer, args.base, out_dir / "merged", subfolder=args.subfolder)
        print(f"merged model written to {out_dir / 'merged'}")


if __name__ == "__main__":
    main()
