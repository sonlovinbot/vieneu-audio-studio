"""Failure handling of the GPU serving path, driven on the CPU with stand-ins.

The real ``V3TurboStreamScheduler`` / ``V3TurboBatchEngine`` code runs; only the
parts that need CUDA (the captured frames, the model) are replaced. Run through
tests/test_serve_guards.py in a fresh interpreter: other test files set
``sys.modules["torch"]`` to a MagicMock, which would turn the
``@torch.no_grad()`` methods under test into mocks.
"""
import math
import threading
import time
from types import SimpleNamespace

import pytest
import torch

from vieneu.v3_turbo_serve import engine as engine_mod
from vieneu.v3_turbo_serve import fused as fused_mod
from vieneu.v3_turbo_serve import stream as stream_mod


class _Any:
    """A tensor that is only sliced and passed along."""
    shape = (4, 8)

    def __getitem__(self, _):
        return self


# ── stream scheduler ─────────────────────────────────────────────────────────

class FakeFrame:
    """``StreamFrame`` without CUDA: takes rows, never finishes them."""

    def __init__(self, model, B, max_len, *, repetition_window):
        self.B = B
        self.bb = SimpleNamespace(layers=[0, 1])
        self.replay_error = None

    def admit(self, b, keys, values, h_last, spk, cap, **sampling):
        if spk == "bad-row":
            raise RuntimeError("row does not fit the frame")
        return 0

    def replay(self):
        if self.replay_error is not None:
            raise self.replay_error

    def status(self):
        return [0] * (2 * self.B)


class FakeBatchEngine:
    def __init__(self):
        self.config = SimpleNamespace(max_position_embeddings=1024)
        self.model = object()
        self.tts = SimpleNamespace(audio_tokenizer=SimpleNamespace(),
                                   _resolve_speaker_emb=lambda s: s)
        self.bb = SimpleNamespace(prefill=self.prefill)
        self.cache = SimpleNamespace(layers=[SimpleNamespace(keys=_Any(), values=_Any())] * 2)

    def _prompt_embeds(self, req):
        if req["phonemes"] == "bad-prompt":
            raise ValueError("ref_codes has the wrong shape")
        return _Any()

    def prefill(self, embeds):
        return [None] * len(embeds), self.cache, _Any(), None


class _NoThread:
    """The worker thread, never started: each test runs ``_admit``/``_run``
    itself, so nothing races the assertions."""

    def __init__(self, target=None, name=None, daemon=None):
        pass

    def start(self):
        pass

    def join(self, timeout=None):
        pass


@pytest.fixture
def make_sched(monkeypatch):
    monkeypatch.setattr(stream_mod, "StreamFrame", FakeFrame)
    monkeypatch.setattr(stream_mod, "threading", SimpleNamespace(
        Thread=_NoThread, Event=threading.Event, Condition=threading.Condition))

    def make(max_streams=2):
        return stream_mod.V3TurboStreamScheduler(FakeBatchEngine(), max_streams=max_streams)

    return make


def _req(**over):
    r = dict(phonemes="xin chào", speaker_emb="spk", ref_codes=None, use_ref_codes=True,
             temperature=0.8, top_k=25, top_p=0.95, repetition_penalty=1.2, max_new_frames=10)
    r.update(over)
    return r


def _queue(sched, **over):
    h = stream_mod.StreamHandle(sched, _req(**over))
    sched._pending.put(h)
    return h


def _answer(h):
    return h.q.get_nowait()


def test_bad_request_fails_alone(make_sched):
    sched = make_sched(max_streams=4)
    bad_prompt = _queue(sched, phonemes="bad-prompt")
    bad_row = _queue(sched, speaker_emb="bad-row")
    good = _queue(sched)
    sched._admit()
    assert isinstance(_answer(bad_prompt), ValueError)
    assert isinstance(_answer(bad_row), RuntimeError)
    assert good.slot is not None and sched._slots[good.slot] is good
    assert good.q.empty() and sched.error is None


def test_more_requests_than_free_slots_wait_their_turn(make_sched):
    # Used to take up to max_admit (8) requests and pop an empty free list:
    # IndexError, and the worker died for everyone.
    sched = make_sched(max_streams=1)
    first, second = _queue(sched), _queue(sched)
    sched._admit()
    assert sched._slots == [first]
    assert sched._pending.qsize() == 1 and second.slot is None
    assert sched.error is None


def test_close_tells_running_and_queued_requests(make_sched):
    # These used to wait forever on a queue no worker would fill again.
    sched = make_sched(max_streams=1)
    running, queued = _queue(sched), _queue(sched)
    sched._admit()
    sched.close()
    sched._run()                          # the worker's exit after close()
    for h in (running, queued):
        err = _answer(h)
        assert isinstance(err, RuntimeError) and "closed" in str(err)
    assert sched.error is None
    with pytest.raises(RuntimeError, match="closed"):
        sched.submit(**_req())


def test_worker_crash_reaches_every_waiter_and_blocks_new_work(make_sched):
    sched = make_sched(max_streams=2)
    sched.frame.replay_error = RuntimeError("CUDA error: an illegal memory access")
    h = sched.submit(**_req())
    sched._run()                          # admits h, then the first frame fails
    with pytest.raises(RuntimeError, match="illegal memory access"):
        list(h)
    assert isinstance(sched.error, RuntimeError)
    with pytest.raises(RuntimeError, match="down"):
        sched.submit(**_req())


def test_crash_while_admitting_reaches_requests_off_the_queue(make_sched):
    # Requests taken off the queue but not yet in a slot are known only to _admit.
    sched = make_sched(max_streams=2)

    class Broken:
        def __getitem__(self, _):
            raise RuntimeError("KV cache layout changed")

    sched.be.cache = SimpleNamespace(layers=[SimpleNamespace(keys=Broken(), values=Broken())] * 2)
    a, b = _queue(sched), _queue(sched)
    sched._run()
    for h in (a, b):
        assert "layout changed" in str(_answer(h))
    assert sched.error is not None


@pytest.mark.parametrize("bad", [
    dict(temperature=float("nan")), dict(temperature=-1.0), dict(top_p=float("inf")),
    dict(repetition_penalty=0.0), dict(top_k="many"),
])
def test_submit_rejects_bad_sampling_in_the_callers_thread(make_sched, bad):
    sched = make_sched()
    with pytest.raises(ValueError):
        sched.submit(**_req(**bad))
    assert sched._pending.empty() and sched.error is None


def test_int64_slot_overflow_is_not_a_value_error():
    # Why the old ``except ValueError`` around admit() could not contain it.
    t = torch.zeros(1, 1, dtype=torch.long)
    with pytest.raises((RuntimeError, OverflowError)):
        t[0] = 10 ** 30


def test_stream_frame_clamps_top_k_into_its_tensor():
    B = 2
    sf = stream_mod.StreamFrame.__new__(stream_mod.StreamFrame)
    sf.max_len, sf.vocab, sf.spk = 64, 1024, None
    sf.bb = SimpleNamespace(load_row=lambda b, k, v: None)
    sf.rep = SimpleNamespace(reset_rows=lambda rows: None)
    sf.h = torch.zeros(B, 4)
    sf.temperature, sf.top_p, sf.penalty = torch.ones(B, 1), torch.ones(B, 1), torch.ones(B, 1)
    sf.top_k = torch.full((B, 1), 25, dtype=torch.long)
    sf.frame = torch.zeros((), dtype=torch.long)
    sf.caps, sf.length = torch.zeros(B, dtype=torch.long), torch.zeros(B, dtype=torch.long)
    sf.finished = torch.ones(B, dtype=torch.bool)
    kv = [torch.zeros(1, 3, 2)]
    for b, k in ((0, 10 ** 30), (1, -5)):
        sf.admit(b, kv, kv, torch.zeros(4), None, 10, temperature=0.8, top_k=k,
                 top_p=0.95, repetition_penalty=1.2)
    assert sf.top_k.view(-1).tolist() == [1024, 0]


# ── batch engine ─────────────────────────────────────────────────────────────

class FakeFused:
    """``FusedFrame`` without CUDA; ``run`` reports how many runs overlap."""
    active = peak = 0
    guard = threading.Lock()

    def __init__(self, model, B, max_len, max_frames, **sampling):
        self.B = B

    def run(self, h, cache, mask, pos, caps, spk, max_new_frames, on_frame=None):
        with FakeFused.guard:
            FakeFused.active += 1
            FakeFused.peak = max(FakeFused.peak, FakeFused.active)
        time.sleep(0.02)
        with FakeFused.guard:
            FakeFused.active -= 1
        return [f"codes-{b}" for b in range(self.B)]


def _engine(monkeypatch):
    monkeypatch.setattr(fused_mod, "FusedFrame", FakeFused)
    FakeFused.active = FakeFused.peak = 0
    tts = SimpleNamespace(
        model=SimpleNamespace(semantic_backbone=None, config=SimpleNamespace(hidden_size=8)),
        config=SimpleNamespace(max_position_embeddings=4096),
    )
    eng = engine_mod.V3TurboBatchEngine(tts)
    eng.bb = SimpleNamespace(prefill=lambda embeds: (None, None, None, None))
    return eng


def _gen(eng, temperature=0.8, rows=1):
    return eng._generate_codes_fused(
        [_Any()] * rows, None, None, temperature=temperature, top_k=25, top_p=0.95,
        repetition_penalty=1.2, repetition_window=16, max_new_frames=10)


def test_fused_runs_do_not_overlap(monkeypatch):
    eng = _engine(monkeypatch)
    threads = [threading.Thread(target=_gen, args=(eng,)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert FakeFused.peak == 1


def test_only_recent_sampling_settings_keep_their_graphs(monkeypatch):
    eng = _engine(monkeypatch)            # keeps 2 settings by default
    temps = lambda: sorted({k[2] for k in eng._fused})   # noqa: E731
    _gen(eng, 0.8)
    _gen(eng, 0.8, rows=4)                # same setting, another batch bucket
    _gen(eng, 0.5)
    assert temps() == [0.5, 0.8] and len(eng._fused) == 3
    _gen(eng, 0.3)                        # a third setting frees the oldest one
    assert temps() == [0.3, 0.5]
    _gen(eng, 0.5)
    _gen(eng, 0.9)                        # 0.5 was used again, so 0.3 goes
    assert temps() == [0.5, 0.9]


def test_graph_budget_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("VIENEU_FUSED_SAMPLINGS", "1")
    eng = _engine(monkeypatch)
    _gen(eng, 0.8)
    _gen(eng, 0.5)
    assert {k[2] for k in eng._fused} == {0.5}


def test_generate_batch_rejects_nan_before_any_gpu_work(monkeypatch):
    eng = _engine(monkeypatch)
    with pytest.raises(ValueError, match="temperature"):
        eng.generate_batch([{"phonemes": "a"}], temperature=math.nan)
    assert eng._fused == {}
