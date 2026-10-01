"""Hugging Face Spaces entry point cho VieNeu Studio.

HF Spaces (SDK = gradio) sẽ chạy file này. Nó nạp giao diện Gradio có sẵn
trong gói `vieneu` (module apps.gradio_main) và mở trên cổng 7860.

Hướng dẫn deploy đầy đủ: ../../HUONG-DAN-DEPLOY-HUGGINGFACE.txt
"""
import os

# HF Spaces phục vụ app ở cổng 7860 và cần bind ra 0.0.0.0 (không phải 127.0.0.1).
os.environ.setdefault("GRADIO_SERVER_NAME", "0.0.0.0")
os.environ.setdefault("GRADIO_SERVER_PORT", "7860")

# `demo` là Blocks dựng sẵn ở module-level của apps.gradio_main.
from apps.gradio_main import demo

if __name__ == "__main__":
    demo.queue().launch(
        server_name=os.environ["GRADIO_SERVER_NAME"],
        server_port=int(os.environ["GRADIO_SERVER_PORT"]),
    )
