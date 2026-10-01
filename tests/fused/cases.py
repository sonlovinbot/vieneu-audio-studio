"""Tests cho đường CUDA-graph của v3 Turbo (``vieneu.v3_turbo_serve.fused``).

Chạy trong tiến trình riêng bởi ``tests/test_fused_frame.py`` (tên tệp cố ý không khớp ``test_*`` để pytest không tự gom vào tiến trình chính) — vài module
test cùng thư mục thay ``torch`` trong ``sys.modules`` bằng stub lúc import,
mà phần này cần torch thật. Lịch sử phạt lặp và sampler chạy được trên CPU
nên không cần GPU; phần backbone/graph chỉ chạy khi có CUDA (skip nếu không).
"""
import math
import random

import pytest

torch = pytest.importorskip("torch")

from vieneu._v3_turbo_engine.rep_history import RepetitionHistory
from vieneu.v3_turbo_serve.batched_acoustic import _sample_batched
from vieneu.v3_turbo_serve.fused import GpuRepHistory, batch_bucket, cache_len_bucket, sample_gpu


def _seen(h: GpuRepHistory, b: int, ch: int) -> set:
    return set(torch.nonzero(h.counts[b, ch] > 0).flatten().tolist())


@pytest.mark.parametrize("window", [0, 3, 8, 64])
def test_gpu_history_matches_deque_history(window):
    B, n_vq = 3, 4
    gpu = GpuRepHistory(B, n_vq, 1024, window, torch.device("cpu"))
    ref = [RepetitionHistory(n_vq, window) for _ in range(B)]
    rng = random.Random(7)
    for _ in range(50):
        for ch in range(n_vq):
            codes = torch.tensor([rng.randrange(12) for _ in range(B)])
            gpu.add(ch, codes)
            for b in range(B):
                ref[b][ch].add(int(codes[b]))
        gpu.advance()
        for ch in range(n_vq):
            for b in range(B):
                assert _seen(gpu, b, ch) == set(ref[b][ch])


def test_gpu_history_penalises_like_the_host_sampler():
    """Cùng logits, cùng lịch sử → cùng logits sau phạt (greedy để so được)."""
    B, n_vq, V = 2, 2, 32
    gpu = GpuRepHistory(B, n_vq, V, 4, torch.device("cpu"))
    ref = [RepetitionHistory(n_vq, 4) for _ in range(B)]
    for code in [(3, 5), (3, 9), (7, 5)]:
        c = torch.tensor(code)
        gpu.add(0, c)
        for b in range(B):
            ref[b][0].add(int(c[b]))
        gpu.advance()
    logits = torch.randn(B, V) * 3
    want = _sample_batched(logits.clone(), 0.0, 0, 1.0, 1.2, [ref[b][0] for b in range(B)])
    got = sample_gpu(gpu.penalise(logits.clone(), 0, 1.2), 0.0, 0, 1.0)
    assert torch.equal(want, got)


def test_reset_clears_everything():
    gpu = GpuRepHistory(1, 1, 16, 2, torch.device("cpu"))
    gpu.add(0, torch.tensor([5]))
    gpu.advance()
    gpu.reset()
    assert _seen(gpu, 0, 0) == set()
    assert int(gpu.frame) == 0


def test_sampler_respects_top_k_and_top_p():
    torch.manual_seed(0)
    logits = torch.tensor([[10.0, 9.0, -5.0, -6.0, -7.0]])
    for _ in range(50):
        assert int(sample_gpu(logits, 0.8, 2, 0.95)) in (0, 1)
    assert int(sample_gpu(logits, 0.0, 2, 0.95)) == 0


def test_buckets():
    assert [batch_bucket(n) for n in (1, 2, 3, 5, 8, 9, 16, 17)] == [1, 2, 4, 8, 8, 16, 16, 32]
    assert cache_len_bucket(700, 2048) == 1024
    assert cache_len_bucket(1025, 2048) == 1536
    assert cache_len_bucket(5000, 2048) == 2048


@pytest.mark.skipif(not torch.cuda.is_available(), reason="needs CUDA")
def test_static_backbone_matches_hf_in_fp32():
    """Bước giải mã trên cache tĩnh phải khớp HF DynamicCache (fp32: ~1e-6)."""
    from vieneu import Vieneu
    from vieneu.v3_turbo_serve.fused import StaticBackbone

    tts = Vieneu(mode="v3turbo", device="cuda", backend="pytorch", dtype="float32")
    eng = tts._get_batch_engine()
    voice = tts.get_preset_voice()
    reqs = [{"text": t, "speaker_emb": voice["speaker_emb"], "ref_codes": voice["codes"]}
            for t in ["Xin chào các bạn.", "Hôm nay trời đẹp quá."]]
    embeds = [eng._prompt_embeds(r) for r in reqs]
    h, cache, mask, pos = eng.bb.prefill(embeds)
    sb = StaticBackbone(eng.model, len(embeds), 1024)
    sb.load(cache, mask, pos)
    H = eng.model.config.hidden_size
    for _ in range(4):
        x = torch.randn(len(embeds), 1, H, device=h.device, dtype=h.dtype) * 0.5
        h_ref, cache, mask, pos = eng.bb.decode_step(x, cache, mask, pos)
        h_new = sb.step(x)
        assert torch.allclose(h_ref, h_new, atol=1e-4, rtol=1e-4)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="needs CUDA")
def test_frame_hook_stops_a_running_batch_within_frames():
    """Một server dừng giữa chừng bằng cách raise từ ``frame_hook`` — phải ăn
    sau vài khung, không phải sau cả batch."""
    from vieneu import Vieneu

    tts = Vieneu(mode="v3turbo", device="cuda", backend="pytorch")
    eng = tts._get_batch_engine()
    calls = []

    def hook():
        calls.append(1)
        if len(calls) == 3:
            raise RuntimeError("cancelled")

    eng.frame_hook = hook
    with pytest.raises(RuntimeError, match="cancelled"):
        tts.infer_batch(["Xin chào các bạn, hôm nay trời đẹp quá."])  # giọng mặc định
    assert len(calls) == 3


# ── continuous batching (stream.py) ──────────────────────────────────────────

def test_gpu_history_rows_start_late_do_not_evict_unwritten_slots():
    """Row vào giữa chừng (``reset_rows``) chỉ được đuổi mã do chính nó ghi."""
    B, n_vq, window = 2, 1, 3
    gpu = GpuRepHistory(B, n_vq, 16, window, torch.device("cpu"))
    ref = [RepetitionHistory(n_vq, window) for _ in range(B)]
    for code in (1, 2, 3, 4):        # row 0 chạy trước 4 khung
        gpu.add(0, torch.tensor([code, 9]))
        gpu.advance()
        ref[0][0].add(code)
    gpu.reset_rows(torch.tensor([1]))   # row 1 bắt đầu tại khung 4
    assert _seen(gpu, 1, 0) == set()
    for code in (5, 6, 7, 8):
        gpu.add(0, torch.tensor([code, code]))
        gpu.advance()
        ref[0][0].add(code)
        ref[1][0].add(code)
        assert _seen(gpu, 0, 0) == set(ref[0][0])
        assert _seen(gpu, 1, 0) == set(ref[1][0])


def test_sample_gpu_rows_matches_scalar_sampler_per_row():
    """Mỗi row một bộ tham số: greedy row, top-k row, và row tắt top-k."""
    from vieneu.v3_turbo_serve.fused import sample_gpu_rows

    torch.manual_seed(0)
    logits = torch.tensor([[10.0, 9.0, -5.0, -6.0, -7.0]]).repeat(3, 1)
    temperature = torch.tensor([[0.0], [0.8], [0.8]])
    top_k = torch.tensor([[2], [2], [0]])
    top_p = torch.tensor([[0.95], [0.95], [1.0]])
    for _ in range(50):
        got = sample_gpu_rows(logits, temperature, top_k, top_p)
        assert int(got[0]) == 0
        assert int(got[1]) in (0, 1)
        assert int(got[2]) in range(5)
    # Row tắt top-k/top-p vẫn đúng phân phối: mã 2..4 gần như không bao giờ được chọn
    # với logits cách nhau 15 đơn vị, nhưng cấu trúc không cấm (không -inf).
    nan_logits = torch.full((1, 5), float("nan"))
    assert int(sample_gpu_rows(nan_logits, torch.tensor([[0.8]]), torch.tensor([[0]]), torch.tensor([[1.0]]))) in range(5)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="needs CUDA")
def test_load_row_matches_load_even_across_the_ring_boundary():
    """Nạp từng row vào cache ring (``load_row``) phải cho cùng bước giải mã
    như nạp cả batch (``load``), kể cả khi chỉ số ghi sắp quay vòng."""
    from vieneu import Vieneu
    from vieneu.v3_turbo_serve.fused import StaticBackbone

    tts = Vieneu(mode="v3turbo", device="cuda", backend="pytorch", dtype="float32")
    eng = tts._get_batch_engine()
    voice = tts.get_preset_voice()
    reqs = [{"text": t, "speaker_emb": voice["speaker_emb"], "ref_codes": voice["codes"]}
            for t in ["Xin chào các bạn.", "Hôm nay trời đẹp quá."]]
    embeds = [eng._prompt_embeds(r) for r in reqs]
    h, cache, mask, pos = eng.bb.prefill(embeds)
    T = mask.shape[1]
    H = eng.model.config.hidden_size
    for start in (0, 1024 - 7, 500):
        ref = StaticBackbone(eng.model, 2, 1024)
        ref.load(cache, mask, pos)
        sb = StaticBackbone(eng.model, 2, 1024)
        sb.cur.fill_(start)
        for i in range(2):
            Ti = embeds[i].shape[0]
            keys = [(cache.layers[l].keys if hasattr(cache, "layers") else cache.key_cache[l])[i, :, T - Ti:T]
                    for l in range(len(sb.layers))]
            vals = [(cache.layers[l].values if hasattr(cache, "layers") else cache.value_cache[l])[i, :, T - Ti:T]
                    for l in range(len(sb.layers))]
            sb.load_row(i, keys, vals)
        for _ in range(12):
            x = torch.randn(2, 1, H, device="cuda") * 0.5
            assert torch.allclose(ref.step(x), sb.step(x), atol=1e-4, rtol=1e-4)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="needs CUDA")
def test_infer_stream_serves_concurrent_callers_and_matches_full_decode():
    """Nhiều thread gọi ``infer_stream`` cùng lúc: mỗi luồng nhận audio đúng
    độ dài mã của mình, audio stream khớp decode đầy đủ cùng mã, huỷ giữa
    chừng giải phóng slot."""
    import threading
    import numpy as np
    from vieneu import Vieneu

    tts = Vieneu(mode="v3turbo", device="cuda", backend="pytorch", max_streams=4)
    sched = tts._get_stream_scheduler()
    assert sched is not None
    texts = ["Xin chào các bạn.", "Hôm nay trời đẹp quá, mình đi dạo nhé.", "Một hai ba bốn năm."]
    out = [None] * len(texts)

    def run(i):
        out[i] = np.concatenate(list(tts.infer_stream(texts[i], apply_watermark=False)))

    ths = [threading.Thread(target=run, args=(i,)) for i in range(len(texts))]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    for a in out:
        assert a.ndim == 1 and len(a) % 3840 == 0 and 0.5 <= len(a) / 48000 <= 6.0
        assert np.abs(a).max() > 0.05
    assert sched.n_active == 0

    # Audio stream == decode đầy đủ của cùng mã (codec streaming không lookahead).
    spk, codes = tts._resolve_ref(None, None, True, True)
    from vieneu_utils.phonemize_text import phonemize_text_with_emotions
    h = sched.submit(phonemes=phonemize_text_with_emotions(texts[1]), speaker_emb=spk,
                     ref_codes=codes, max_new_frames=80)
    streamed = np.concatenate(list(h))
    idx = torch.remainder(torch.arange(h.f0, h.f0 + h.frames, device="cuda"), sched.frame.ring)
    row_codes = sched.frame.codes.index_select(0, idx)[:, h.slot].cpu()
    full = tts.engine._decode_codes(row_codes)
    assert len(streamed) == len(full) == h.frames * 3840
    assert np.abs(streamed - full).max() < 1e-3

    g = tts.infer_stream(texts[1], apply_watermark=False)
    next(g)
    g.close()
    import time
    time.sleep(0.5)
    assert sched.n_active == 0
    tts.close()


# ── issue #198: reference encoder must not append the audible pad frame ──────

@pytest.mark.skipif(not torch.cuda.is_available(), reason="needs CUDA")
def test_pytorch_reference_encoder_has_no_pad_frame():
    """Clip lẻ mẫu → đúng ceil(n/3840) frame, frame cuối là mã thật (im lặng = 482),
    không phải mã đệm 455 nghe được."""
    import numpy as np
    from vieneu import Vieneu
    from vieneu_utils.core_utils import CODEC_SAMPLES_PER_FRAME as F, ENCODER_PAD_CODE

    tts = Vieneu(mode="v3turbo", device="cuda", backend="pytorch")
    enc = lambda w: tts.engine._encode_ref_wav(torch.from_numpy(w).unsqueeze(0), 48_000)
    for n, extra in [(10, 0), (50, 1), (50, F - 1)]:
        codes = enc(np.zeros(n * F + extra, np.float32))
        assert codes.shape[0] == n + (1 if extra else 0)
        assert int(codes[-1, 0]) != ENCODER_PAD_CODE and int(codes[-1, 0]) == 482
    for v in tts._preset_voices.values():
        if v["codes"] is not None:
            assert int(v["codes"][-1, 0]) != ENCODER_PAD_CODE


def test_onnx_reference_encoder_has_no_pad_frame():
    """Đường ONNX từng LUÔN trả n+1 frame với frame cuối 455, kể cả clip tròn frame."""
    import numpy as np
    from vieneu_utils.core_utils import CODEC_SAMPLES_PER_FRAME as F, ENCODER_PAD_CODE
    try:
        from vieneu import Vieneu
        tts = Vieneu(mode="v3turbo", device="cpu", backend="onnx")
    except Exception as e:   # noqa: BLE001 — no model cache / no onnxruntime here
        pytest.skip(f"ONNX engine unavailable: {e}")
    for n, extra in [(10, 0), (50, 1), (50, F - 1)]:
        codes = tts.engine._encode_ref_wav(np.zeros(n * F + extra, np.float32), 48_000)
        assert codes.shape[0] == n + (1 if extra else 0)
        assert int(codes[-1, 0]) != ENCODER_PAD_CODE and int(codes[-1, 0]) == 482
