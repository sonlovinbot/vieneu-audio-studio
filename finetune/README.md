# 🦜 Fine-tune VieNeu-TTS v3 Turbo bằng LoRA — một giọng

Thư mục này dạy **VieNeu-TTS v3 Turbo** đọc bằng **một giọng** của bạn với **LoRA**: chỉ vài triệu tham số được học, model gốc giữ nguyên, train được trên một GPU phổ thông (~6 GB VRAM với cấu hình mặc định).

Toàn bộ quy trình dựa trên chính SDK `vieneu`: dữ liệu được chuẩn hoá, phiên âm và mã hoá **giống hệt lúc suy luận**, nên model sau khi merge dùng được ngay với `Vieneu(mode="v3turbo")`.

**Cách nó hoạt động, ngắn gọn:** mỗi clip được mã hoá thành codec codes (nhãn) và một speaker embedding 192 chiều; model học sinh ra codes từ phiên âm + embedding đó, **không dùng clip tham chiếu trong ngữ cảnh**. Giọng sau fine-tune = LoRA + embedding của giọng đó, nên khi dùng chỉ cần đóng gói một embedding (bước 4), không cần audio mẫu.

> **Bao nhiêu dữ liệu?** v3 Turbo đã clone giọng tức thì từ một clip **vài giây**, nên chỉ fine-tune khi cần bám giọng chặt hơn clone, một phong cách đọc đặc thù (đọc truyện, tin tức, thuyết minh…), hoặc sửa cách đọc trên một miền văn bản riêng. Với một giọng, **10–30 phút** audio sạch (100–300 câu khác nhau) là đủ; câu đa dạng quan trọng hơn tổng thời lượng. Data ít thì rủi ro là overfit chứ không phải thiếu: giữ eval bật và dừng khi eval loss ngừng giảm.
>
> Muốn nhiều giọng? Train mỗi giọng một LoRA riêng — đơn giản và ổn định hơn nhồi nhiều giọng vào một adapter.

## ⚙️ Cài đặt

```bash
git clone https://github.com/pnnbao97/VieNeu-TTS.git
cd VieNeu-TTS
uv sync --extra finetune        # torch, transformers, peft, accelerate (cần GPU CUDA để train)
```

## 1. Chuẩn bị dữ liệu

```
finetune/dataset/
  metadata.csv        mỗi dòng: file_name|text
  raw_audio/          các file audio được nhắc trong metadata.csv
```

- **Tất cả clip phải là cùng một người nói.** Đây là ràng buộc duy nhất của pipeline — một LoRA là một giọng.
- Mỗi clip **1–20 giây**, nội dung đúng với `text` (kể cả dấu câu). Clip dài hơn hãy cắt nhỏ trước.
- Audio sạch, ít vang, không nhạc nền. Tần số lấy mẫu bất kỳ, mono hay stereo đều được.

```bash
uv run python finetune/prepare_dataset.py --dataset-dir finetune/dataset
```

Script chạy trên CPU, không cần torch: phiên âm bằng sea-g2p, mã hoá audio bằng codec MOSS (ONNX) và trích speaker embedding 192 chiều của từng clip. Kết quả là `finetune/dataset/train.parquet` (cột `phones, codes, speaker_embedding, duration, text, file_name`).

## 2. Train LoRA

```bash
uv run python finetune/train_lora.py --data finetune/dataset/train.parquet --run my_voice --merge
```

Mặc định: LoRA rank 16 trên toàn bộ attention và MLP của backbone, learning rate 2e-4, 3 epoch, batch hiệu dụng 16, bf16. Vài tuỳ chọn hay dùng:

| Tuỳ chọn | Ý nghĩa |
|---|---|
| `--epochs 3` / `--max-steps N` | thời lượng train |
| `--r 16 --alpha 32` | dung lượng LoRA; giọng khó hoặc data nhiều thì tăng `--r 32` |
| `--target all` | thêm LoRA cho acoustic decoder (chất giọng bám sát hơn, cần data nhiều hơn) |
| `--grad-checkpoint` | tiết kiệm VRAM khi tăng `--batch-size` hoặc `--max-length` |
| `--merge` | ghi thêm model đầy đủ đã merge ở cuối |

Theo dõi log: `audio` là cross-entropy trung bình của 16 codebook, `acc_cb0` là độ chính xác top-1 của codebook đầu. Trên pipeline đúng, `acc_cb0` phải ở mức 0.2–0.4 ngay từ bước đầu và tăng dần; nếu gần 0 thì dữ liệu có vấn đề (phiên âm hoặc codes không khớp audio).

Kết quả nằm trong `finetune/output/my_voice/`:

```
adapter/        LoRA adapter (vài MB) — dùng với merge_lora.py
checkpoint-*/   adapter trung gian
merged/         model đầy đủ, đúng bố cục repo chính thức (khi có --merge)
```

## 3. Merge model

```bash
uv run python finetune/merge_lora.py --adapter finetune/output/my_voice/adapter --out finetune/output/my_voice/merged
# đẩy lên Hugging Face: thêm --push-to-hub your-name/VieNeu-TTS-v3-Turbo-my-voice [--private]
```

Model merge chạy trên **GPU (PyTorch)**. Đường CPU/ONNX của SDK dùng đồ thị đã export sẵn của model gốc, nên chưa nhận model fine-tune.

## 4. Đóng gói giọng và dùng

Lấy một clip 3–8 giây của **đúng người nói đó** (một clip trong dataset cũng được) để tạo speaker embedding và ghi thành giọng dựng sẵn đi kèm model:

```bash
uv run python finetune/make_voice.py --audio ref.wav --name "Giọng của tôi" \
    --description "Nữ · Bắc · Phong cách tự nhiên" --gender female \
    --out finetune/output/my_voice/merged
```

Lệnh này ghi `voices_v3_turbo.json` vào thư mục model — chỉ speaker embedding, **không có mã tham chiếu**, đúng như lúc train. SDK tự nạp file đó từ thư mục local hoặc repo Hub, cộng thêm vào các giọng có sẵn, và giọng bạn đặt thành mặc định:

```python
from vieneu import Vieneu
tts = Vieneu(mode="v3turbo", backbone_repo="finetune/output/my_voice/merged")   # hoặc "your-name/…"
audio = tts.infer("Xin chào, đây là giọng đã fine-tune.", voice="Giọng của tôi")
tts.save(audio, "out.wav")
```

Lưu ý: model merge được dạy cho **một giọng**; muốn nó clone giọng khác thì dùng model gốc. (`make_voice.py --with-ref-codes` chỉ dành cho đóng gói giọng cho model gốc.)

## Cấu trúc code

```
finetune/
  prepare_dataset.py   audio + text (một người nói)  →  train.parquet
  train_lora.py        train LoRA (peft)
  merge_lora.py        adapter + base  →  model đầy đủ, tuỳ chọn push Hub
  make_voice.py        clip  →  voices_v3_turbo.json (speaker embedding, không mã tham chiếu)
  vieneu_lora/
    data.py            dựng chuỗi token 2 chiều và nhãn từ một hàng dữ liệu (không ref)
    model.py           forward teacher-forcing + loss trên model của SDK
    lora.py            gắn, lưu, nạp, merge, export LoRA
```
