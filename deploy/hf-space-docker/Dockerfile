# HF Spaces (Docker SDK) — chạy ĐÚNG webapp FastAPI của bạn
# (giao diện có tab API + AI Prompt). SDK giọng nói lấy từ PyPI, còn
# giao diện thì chép đè bằng thư mục webapp/ trong repo Space.
FROM python:3.12-slim

# libsndfile1 cần cho soundfile (đọc/ghi WAV)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# HF Spaces chạy container bằng user UID 1000 (không phải root)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    VIENEU_HOST=0.0.0.0 \
    VIENEU_PORT=7860 \
    VIENEU_LIBRARY=off \
    HF_HOME=/home/user/.cache/huggingface \
    VIENEU_DOWNLOAD_DIR=/app/downloads

WORKDIR /app

# Engine TTS torch-free (CPU/ONNX) — không cần GPU
RUN pip install --no-cache-dir --user vieneu==3.8.3

# Giao diện CỦA BẠN: đè lên bản webapp đóng kèm trong gói pip.
# Chạy "python -m webapp.server" từ /app sẽ ưu tiên thư mục này.
COPY --chown=user webapp ./webapp
# Bộ cài .zip cho nút "Tải bộ cài" trong onboarding (update-space.sh chép từ dist/).
COPY --chown=user downloads ./downloads

EXPOSE 7860
CMD ["python", "-m", "webapp.server"]
