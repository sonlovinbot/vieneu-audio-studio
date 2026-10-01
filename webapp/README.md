# 🦜 VieNeu Studio — Coachio Edition

Giao diện đào tạo gọn nhẹ cho **VieNeu-TTS**: sinh giọng tiếng Việt, nhân bản giọng (voice cloning) từ 3–5s, hội thoại đa nhân vật — chạy **100% offline trên máy bạn**, đồng thời mở sẵn **REST API** để cắm vào phần mềm khác.

> Mô hình VieNeu-TTS được thiết kế và huấn luyện bởi **Phạm Nguyễn Ngọc Bảo**. Phần ghi nhận tác giả nằm trong tab **Cài đặt & Giới thiệu** — vui lòng giữ nguyên khi phân phối lại.

---

## ⚡ Cài đặt 1-cú-nhấp

| Hệ điều hành | Cách làm |
|---|---|
| **macOS** | Nhấp đúp **`install.command`** |
| **Windows** | Nhấp đúp **`install.bat`** |

Bộ cài sẽ tự động: cài `uv` → cài thư viện (`uv sync`) → tạo **icon trên Desktop** → hỏi **có tự chạy khi mở máy không** → khởi chạy và mở trình duyệt tại `http://127.0.0.1:8001`.

> 💡 Bản mặc định chạy **CPU/ONNX (v3 Turbo, 48 kHz)** — nhẹ, không cần GPU, chạy mọi máy.

### Chạy thủ công (nếu thích dòng lệnh)
```bash
uv run vieneu-studio          # mở http://127.0.0.1:8001
```

---

## 🔌 REST API (cắm vào phần mềm khác)

Server mở API ngay tại `http://127.0.0.1:8001`. Ví dụ:

```bash
# Sinh giọng → file WAV
curl -X POST http://127.0.0.1:8001/api/tts \
  -H "Content-Type: application/json" \
  -d '{"text":"Xin chào lớp học","voice":"Bình An"}' \
  --output hello.wav
```

| Endpoint | Mô tả |
|---|---|
| `GET  /api/health` | Trạng thái server/model |
| `GET  /api/info` | Thông tin app + tác giả (branding) |
| `GET  /api/voices` | Danh sách giọng mặc định |
| `POST /api/tts` | `{text, voice, emotion, temperature, top_k}` → WAV |
| `POST /api/clone` | multipart: `text` + `ref_audio` (file 3–5s) → WAV |
| `POST /api/conversation` | `{turns:[{voice,text}], gap_seconds}` → WAV hội thoại |
| `GET  /api/stream?text=&voice=` | Streaming WAV (phát ngay) |
| `POST /api/load` | (nâng cao) đổi model: `{mode, backbone_repo, device}` |
| `GET  /api/version` | Phiên bản app / SDK / Python / hệ điều hành |
| `GET  /api/changelog` | Nhật ký cập nhật (cập nhật mới) |
| `GET  /api/history` | Lịch sử 50 lượt gần nhất (văn bản, giọng, model, thời lượng) |
| `GET  /api/history/{id}/audio` | File WAV của một lượt (`?download=1` để tải) |
| `DELETE /api/history[/{id}]` | Xóa một lượt / toàn bộ lịch sử |
| `GET  /api/voices/custom` | Giọng của tôi (giọng clone đã lưu) |
| `POST /api/voices/custom` | multipart: `name` + `ref_audio` → lưu thành giọng dùng lại được |
| `PATCH /api/voices/custom` | `{old, new}` đổi tên giọng |
| `DELETE /api/voices/custom?name=` | Xóa giọng đã lưu |
| `GET  /api/logs?lines=200&level=` | Logs server gần đây (xem trong tab Phiên bản & Logs) |

> 💡 Mở tab **🔌 API** trong giao diện để lấy sẵn ví dụ `curl` / `fetch` / `Python` cho từng endpoint (có nút sao chép, tự điền host).

→ Dễ tích hợp với **n8n / Make / Zapier**, Google Sheets, OBS, hoặc script Python/JS của bạn.

---

## 🖥️ Tự chạy khi mở máy

Chọn "có" lúc cài, hoặc bật lại sau:
- **macOS:** đã tạo LaunchAgent `~/Library/LaunchAgents/com.vieneu.studio.plist`. Tắt: `launchctl unload <đường-dẫn>`.
- **Windows:** đã đặt file trong thư mục `Startup`. Tắt: xóa `VieNeu Studio (autostart).bat` trong `shell:startup`.

---

## 🚀 Nâng cao: GPU / v2 / LoRA

Giao diện vẫn giữ **đầy đủ** các model. Để dùng v2/GPU/LoRA cần cài thêm bản GPU:
```bash
uv sync --group gpu
```
Rồi vào tab **Cài đặt & Giới thiệu → Đổi model (nâng cao)** để chọn chế độ và nhập repo HuggingFace.

---

## 🎨 Đổi nhận diện thương hiệu (theme)

Toàn bộ màu/font/spacing nằm trong **một file duy nhất**:
`webapp/static/css/coachio-theme.css` (khối `:root`).
Thông tin tác giả & app: `webapp/config/branding.json`.

---

## 🏗️ Kiến trúc

```
webapp/
  server.py              FastAPI: serve web tĩnh + REST API
  config/branding.json   Thông tin app + tác giả (tab Cài đặt)
  static/
    index.html           Giao diện 4 tab
    css/coachio-theme.css ⭐ token thương hiệu (1 nguồn)
    css/app.css          layout
    js/app.js            gọi API
install.command          Bộ cài macOS
install.bat              Bộ cài Windows
```
