from vieneu import Vieneu
from time import time

# Default = v3 Turbo. CPU → ONNX (torch-free); GPU → PyTorch (auto-detected).
vieneu = Vieneu()

text = f"""[cười] Trời ơi, cái giọng nó tự nhiên mà nó mượt mà dã man, nghe không khác gì người thật luôn. Giờ thì tha hồ mà quẩy content với cả kho giọng nói đa dạng, đủ mọi sắc thái biểu cảm. Mọi người bật loa lên rồi cùng trải nghiệm thử với mình nhé!"""

start_time = time()
# 1. Default voice (Ngọc Lan) — 48 kHz, no reference needed
audio = vieneu.infer(text)
vieneu.save(audio, "output.wav")
end_time = time()
print(f"Time taken: {end_time - start_time} seconds")
# 2. Built-in voices by name
for label, voice_id in vieneu.list_preset_voices():
    print(label, voice_id)
audio = vieneu.infer("Mình là Xuân Vĩnh nè!", voice="Xuân Vĩnh")
vieneu.save(audio, "output_Xuân Vĩnh.wav")
# # 3. Emotion / non-verbal cues — EXPERIMENTAL: [cười] [thở dài] [hắng giọng]
# audio = vieneu.infer("Nghe hay quá đi [cười]. Để mình nói tiếp [hắng giọng].", voice="Ngọc Linh")

# # 4. Instant voice cloning from a 3–5s reference clip
# audio = vieneu.infer("Đây là giọng được nhân bản tức thì.", ref_audio="my_voice.wav")    