# 🐳 Docker Deployment Guide for VieNeu-TTS

## 📋 Table of Contents

- [System Requirements](#system-requirements)
- [Quick Start Guide (Dev)](#quick-start-guide-dev)
- [Production Deployment](#production-deployment)
- [Production Deployment Workflow](#production-deployment-workflow)
- [Remote Server Deployment (One-Command)](#remote-server-deployment-one-command)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

---

## 🖥️ System Requirements

1. **Docker**: Version 20.10 or higher
2. **Docker Compose**: Version 2.20 or higher
3. **NVIDIA Docker Runtime** (for GPU variants): Requires `nvidia-container-toolkit` installation.

---

## 🚀 Quick Start Guide (Dev)

The Development environment is designed to allow you to edit code on your host machine (Windows/Linux) and run it immediately in Docker without rebuilding the image.

### 1. Startup (App + Interactive)

Run the following command to start the Web UI. You can also open another terminal to `exec` into the container.

> **Note:** Docker deployment currently supports **GPU only**. For CPU usage, please install from source (see main README).

```bash
# GPU only
docker compose -f docker/docker-compose.yml --profile gpu up
```

Access: **http://localhost:7860**

### 2. Run Manual Commands (Optional)

If you want to run scripts manually in the running container:

```bash
docker compose exec gpu bash
```

In the shell, you can run: `uv run examples/main.py`, `uv run examples/infer_long_text.py`, ...

The current directory code is mounted to `/workspace`, so when you edit code outside, it updates immediately in the container.

---

## 🚢 Production Deployment

The Production environment uses `docker/docker-compose.prod.yml`. Source code will be **copied into the image** (no volume mount), ensuring stability and portability. By default, these services will **automatically run the Web UI**.

**Standard workflow:**

1. **Build Image**: Use `docker/docker-compose.build.yml`.
2. **Push to Registry**: Push the image to Docker Hub / Private Registry.
3. **Deploy**: On the server, use `docker/docker-compose.prod.yml` to pull and run.

---

## 🏗️ Production Deployment Workflow

### 1. Build Docker Image

Copy `.env.example` to `.env` and set your image name (e.g., `myregistry.com/vieneu-tts-gpu`):

```bash
IMAGE_NAME=myregistry.com/vieneu-tts-gpu
IMAGE_TAG=v1.0.0
```

Run the build command:

```bash
# Build both (if needed) or specify service
docker compose -f docker/docker-compose.build.yml build gpu
```

### 2. Push Image

```bash
docker compose -f docker/docker-compose.build.yml push gpu
```

### 3. Run on Production

On the production server, you only need the `docker/docker-compose.prod.yml` file and the `.env` file.

**Startup:**

```bash
# Pull the latest image
docker compose -f docker/docker-compose.prod.yml --profile gpu pull

# Start the service
docker compose -f docker/docker-compose.prod.yml --profile gpu up -d
```

---

## 🌐 Remote Server Deployment (One-Command) <a name="remote-server-deployment-one-command"></a>

To enable the "One-Command" deployment experience for your users (where they just run `docker run ...` and it works purely from the cloud), you must build and push the special server image to Docker Hub.

### 1. Build & Push Image

We have prepared Makefile targets for this specific purpose:

```bash
# 1. Login to Docker Hub (if you haven't)
docker login

# 2. Build the server image
make docker-build-serve

# 3. Push to Docker Hub
make docker-push-serve
```

*Note: The image is tagged `pnnbao97/vieneu-tts:serve` by default. Update the Makefile if you use a different registry.*

### 2. User Experience

Once pushed, ANY user with an NVIDIA GPU can run your server with a single command (no repo cloning needed):

```bash
docker run --runtime nvidia --gpus all \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  pnnbao97/vieneu-tts:serve
```

This image is optimized purely for serving the API (minimal size, pre-installed dependencies).

---

## ⚙️ Configuration

### Profiles

We use Docker Compose Profiles to manage variants:

| Profile | Environment | File                      | Description                          |
| ------- | ----------- | ------------------------- | ------------------------------------ |
| `gpu`   | **Dev**     | `docker/docker-compose.yml`      | Dev mode (Mount code + Web UI + GPU) |
| `gpu`   | **Prod**    | `docker/docker-compose.prod.yml` | Run mode (Baked code + Web UI + GPU) |

### Environment Variables

Important environment variables (already set in docker-compose):

- `HF_HOME`: HuggingFace cache path (mounted as volume `huggingface_cache`).
- `PHONEMIZER_ESPEAK_LIBRARY`: espeak library path.

---

## 🔧 Troubleshooting

### 1. GPU Not Detected

Make sure you have installed `nvidia-container-toolkit` and the latest drivers. Test with:

```bash
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

### 2. Permission Error When Editing Files (Linux)

Due to volume mounting, files created in Docker may be owned by root. You may need to change ownership:

```bash
sudo chown -R $USER:$USER output_audio/
```

(On Windows Docker Desktop, this issue does not occur).
