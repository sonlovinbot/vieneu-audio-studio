# 🐳 Hướng Dẫn Deploy VieNeu-TTS với Docker

## 📋 Mục lục

- [Yêu cầu hệ thống](#yêu-cầu-hệ-thống)
- [Quick Start Guide (Dev)](#quick-start-guide-dev)
- [Production Deployment](#production-deployment)
- [Workflow Deploy Production](#workflow-deploy-production)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

---

## 🖥️ Yêu cầu hệ thống

1. **Docker**: Version 20.10 trở lên
2. **Docker Compose**: Version 2.20 trở lên
3. **NVIDIA Docker Runtime** (cho GPU variants): Cần cài đặt `nvidia-container-toolkit`.

---

## 🚀 Quick Start Guide (Dev)

Môi trường Development được thiết kế để bạn có thể chỉnh sửa code trên máy host (Windows/Linux) và chạy ngay trong Docker mà không cần rebuild image.

### 1. Khởi động (App + Interactive)

Chạy lệnh sau sẽ bật Web UI. Bạn cũng có thể mở terminal khác để `exec` vào container.

> **Lưu ý:** Docker hiện chỉ hỗ trợ **GPU**. Nếu muốn dùng CPU, vui lòng cài từ source (xem README chính).

```bash
# Chỉ hỗ trợ GPU
docker compose -f docker/docker-compose.yml --profile gpu up
```

Truy cập: **http://localhost:7860**

### 2. Chạy lệnh thủ công (Optional)

Nếu muốn chạy scripts thủ công trong container đang chạy:

```bash
docker compose exec gpu bash
```

Trong shell, bạn có thể chạy: `uv run examples/main.py`, `uv run examples/infer_long_text.py`, ...

Code thư mục hiện tại được mount vào `/workspace`, nên bạn sửa code ở ngoài là trong container cập nhật ngay.

---

## 🚢 Production Deployment

Môi trường Production sử dụng `docker/docker-compose.prod.yml`. Code source sẽ được **copy vào trong image** (không mount volume), đảm bảo tính ổn định và portable. Mặc định các service này sẽ **tự động chạy Web UI**.

**Quy trình chuẩn:**

1.  **Build Image**: Sử dụng `docker/docker-compose.build.yml`.
2.  **Push Registry**: Đẩy image lên Docker Hub / Private Registry.
3.  **Deploy**: Trên server, dùng `docker/docker-compose.prod.yml` để pull và chạy.

---

## 🏗️ Workflow Deploy Production

### 1. Build Docker Image

Copy `.env.example` ra `.env` và đặt tên image của bạn (VD: `myregistry.com/vieneu-tts-gpu`):

```bash
IMAGE_NAME=myregistry.com/vieneu-tts-gpu
IMAGE_TAG=v1.0.0
```

Chạy lệnh build:

```bash
# Build cả 2 (nếu cần) hoặc chỉ định service
docker compose -f docker/docker-compose.build.yml build gpu
```

### 2. Push Image

```bash
docker compose -f docker/docker-compose.build.yml push gpu
```

### 3. Run trên Production

Trên server production, bạn chỉ cần file `docker/docker-compose.prod.yml` và file `.env`.

**Startup:**

```bash
# Pull image mới nhất
docker compose -f docker/docker-compose.prod.yml --profile gpu pull

# Khởi chạy
docker compose -f docker/docker-compose.prod.yml --profile gpu up -d
```

---

## ⚙️ Configuration

### Profiles

Chúng tôi sử dụng Docker Compose Profiles để quản lý các variants:

| Profile | Môi trường | File                      | Mô tả                                |
| ------- | ---------- | ------------------------- | ------------------------------------ |
| `gpu`   | **Dev**    | `docker/docker-compose.yml`      | Dev mode (Mount code + Web UI + GPU) |
| `gpu`   | **Prod**   | `docker/docker-compose.prod.yml` | Run mode (Baked code + Web UI + GPU) |

### Environment Variables

Các biến môi trường quan trọng (đã được set sẵn trong docker-compose):

- `HF_HOME`: Đường dẫn cache HuggingFace (được mount volume `huggingface_cache`).
- `PHONEMIZER_ESPEAK_LIBRARY`: Đường dẫn thư viện espeak.

---

## 🔧 Troubleshooting

### 1. GPU không nhận

Đảm bảo bạn đã cài `nvidia-container-toolkit` và driver mới nhất. Test bằng:

```bash
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

### 2. Lỗi Permission khi edit file (Linux)

Do volume mount, owner của file tạo ra trong docker có thể là root. Bạn có thể cần chown lại folder:

```bash
sudo chown -R $USER:$USER output_audio/
```

(Trên Windows Docker Desktop thì không bị vấn đề này).
