"""VieNeu-TTS v3 Nano — the light model for WEAK CPUs.

v3 Turbo stays the default (`Vieneu()`); reach for Nano only when Turbo is too slow
on your machine (old laptops, mini PCs, single-board computers). Trade-offs:
24 kHz output (Turbo: 48 kHz), preset voices only (no cloning), and weaker
English / code-switched speech.
"""
from time import time

from vieneu import Vieneu

tts = Vieneu(mode="v3nano")            # ONNX, CPU, torch-free

text = "Xin chào các bạn, mình là giọng đọc của VieNeu Nano. [cười] Mình nhẹ hơn nhiều so với bản Turbo, nên chạy được cả trên những máy yếu."

t0 = time()
audio = tts.infer(text, voice="Adam")  # default voice; see tts.list_preset_voices()
dt = time() - t0
tts.save(audio, "output_nano.wav")
secs = len(audio) / tts.sample_rate
print(f"{secs:.1f}s of audio in {dt:.1f}s -> RTF {dt / secs:.2f}")

for label, voice_id in tts.list_preset_voices():
    print(label, "->", voice_id)

# Faster on very slow CPUs: 8 Euler steps + sway sampling (~2x faster, slightly rougher)
audio_fast = tts.infer("Bản nhanh cho máy rất yếu.", voice="Ái Hân", steps=8, sway=-1)
tts.save(audio_fast, "output_nano_fast.wav")
