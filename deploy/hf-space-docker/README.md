---
title: Coachio Audio Free
emoji: 🔊
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
short_description: Vietnamese TTS webapp — API + AI Prompt (CPU/ONNX, no GPU)
---

# Coachio Audio Free — Webapp (FastAPI)

Bản webapp đầy đủ: Sinh giọng, Clone giọng, Hội thoại, và tab **🔌 API** kèm
**🤖 AI Prompt** để cắm vào nền tảng agent khác. Mặc định chạy **CPU qua ONNX —
không cần GPU**.

- Engine: gói `vieneu` (PyPI), model `pnnbao-ump/VieNeu-TTS`
- Source: https://github.com/pnnbao97/VieNeu-TTS

> Lần đầu khởi động sẽ tải model (vài phút). Space free "ngủ" khi không ai dùng,
> tự thức khi có người mở.
