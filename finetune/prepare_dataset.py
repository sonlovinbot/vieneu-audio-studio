"""Turn a folder of clips + transcripts of ONE speaker into a training file for LoRA fine-tuning.

Input layout (default ``finetune/dataset/``)::

    dataset/
      metadata.csv        one line per clip:  file_name|text
      raw_audio/          the clips referenced by metadata.csv (wav/flac/mp3, any sample rate)

All clips must be the same speaker: a LoRA teaches the model one voice, conditioned on
the speaker embedding of each clip and nothing else (no in-context reference clip).

Output: ``dataset/train.parquet`` with columns
``phones, codes, speaker_embedding, duration, text, file_name``.

Everything runs torch-free on the CPU through the ``vieneu`` SDK: the text is normalised and
phonemised exactly like at inference time, the audio is encoded with the MOSS codec (ONNX)
and the 192-d speaker embedding comes from the same speaker encoder used for cloning.

    uv run python finetune/prepare_dataset.py --dataset-dir finetune/dataset
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "finetune"))

from vieneu_lora.utils import safe_path   # noqa: E402


def read_metadata(path: Path):
    rows, extra = [], 0
    with open(path, encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line or (ln == 1 and line.lower().startswith("file_name|")):
                continue
            parts = line.split("|")
            if len(parts) < 2:
                print(f"  skip line {ln}: expected file_name|text")
                continue
            if len(parts) > 2 and parts[2].strip():
                extra += 1
            rows.append({"file_name": parts[0].strip(), "text": parts[1].strip()})
    if extra:
        print(f"  note: {extra} line(s) carry a 3rd column — ignored. A LoRA is one speaker; "
              f"every clip in this folder must be the same voice.")
    return rows


def phonemize(text: str) -> str:
    from vieneu_utils.phonemize_text import normalize_to_chunks_v3_with_gaps, phonemize_text_with_emotions
    chunks, _ = normalize_to_chunks_v3_with_gaps(text, max_chars=1_000_000)
    return " ".join(phonemize_text_with_emotions(c) for c in chunks).strip()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset-dir", default=str(ROOT / "finetune" / "dataset"))
    ap.add_argument("--metadata", default=None, help="default: <dataset-dir>/metadata.csv")
    ap.add_argument("--audio-dir", default=None, help="default: <dataset-dir>/raw_audio")
    ap.add_argument("--out", default=None, help="default: <dataset-dir>/train.parquet")
    ap.add_argument("--min-sec", type=float, default=1.0)
    ap.add_argument("--max-sec", type=float, default=20.0, help="longer clips are skipped (split them first)")
    ap.add_argument("--base", default="pnnbao-ump/VieNeu-TTS-v3-Turbo", help="model repo (codec + speaker encoder)")
    args = ap.parse_args()

    ds_dir = safe_path(args.dataset_dir)
    meta = safe_path(args.metadata) if args.metadata else ds_dir / "metadata.csv"
    audio_dir = safe_path(args.audio_dir) if args.audio_dir else ds_dir / "raw_audio"
    out = safe_path(args.out) if args.out else ds_dir / "train.parquet"
    rows = read_metadata(meta)
    print(f"{len(rows)} clips listed in {meta}")

    import soundfile as sf
    from vieneu import Vieneu
    tts = Vieneu(mode="v3turbo", backend="onnx", precision="fp32", backbone_repo=args.base)
    eng = tts.engine
    spk_enc = eng._ensure_speaker_encoder()

    recs, skipped, t0 = [], 0, time.perf_counter()
    for i, r in enumerate(rows, 1):
        p = safe_path(r["file_name"], base=audio_dir)
        if not p.is_file():
            print(f"  missing audio: {p}"); skipped += 1; continue
        wav, sr = sf.read(str(p), dtype="float32", always_2d=True)
        wav = wav.mean(axis=1)
        dur = len(wav) / sr
        if not (args.min_sec <= dur <= args.max_sec):
            print(f"  skip {r['file_name']}: {dur:.1f}s outside [{args.min_sec}, {args.max_sec}]"); skipped += 1; continue
        phones = phonemize(r["text"])
        if not phones:
            print(f"  skip {r['file_name']}: empty phonemes"); skipped += 1; continue
        codes = eng._encode_ref_wav(wav, sr)                        # (T, 16) int64 @ 12.5 frames/s
        emb = np.asarray(spk_enc.embed(wav, sr), dtype=np.float32)  # (192,)
        recs.append({"file_name": r["file_name"], "text": r["text"],
                     "phones": phones, "codes": codes.astype(np.int64).tolist(),
                     "speaker_embedding": emb.tolist(), "duration": float(dur)})
        if i % 20 == 0 or i == len(rows):
            print(f"  {i}/{len(rows)}  ({time.perf_counter() - t0:.0f}s)")

    if not recs:
        raise SystemExit("No usable clips.")
    # Issue #198: a bug in the encoder used to end EVERY row with the same
    # codebook-0 value (455, the pad-frame artifact) and the model learnt to
    # emit it after each sentence. Clean data never agrees on a last code.
    from collections import Counter
    last = Counter(x["codes"][-1][0] for x in recs)
    code, n_same = last.most_common(1)[0]
    if len(recs) >= 20 and n_same / len(recs) > 0.5:
        raise SystemExit(f"{n_same}/{len(recs)} rows end with codebook-0 = {code}: the encoder is appending a "
                         f"pad frame (issue #198). Update vieneu and rebuild — training on this teaches the "
                         f"model to say that frame after every sentence.")
    import pyarrow as pa, pyarrow.parquet as pq
    pq.write_table(pa.Table.from_pylist(recs), str(out))
    total = sum(x["duration"] for x in recs)
    print(f"\nwrote {out}: {len(recs)} rows, {total/60:.1f} min of audio, skipped={skipped}")


if __name__ == "__main__":
    main()
