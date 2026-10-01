# Hướng dẫn sử dụng Makefile 🛠️

Tài liệu này hướng dẫn cách sử dụng `Makefile` trong kho lưu trữ này để tự động hóa việc thiết lập, kiểm tra môi trường và chạy ứng dụng. `Makefile` giúp đơn giản hóa các tác vụ phức tạp và đảm bảo bạn có đầy đủ các phụ thuộc cần thiết.

---

## ⚙️ Hướng dẫn cài đặt `make`

Nếu lệnh `make` không được tìm thấy trên hệ thống của bạn, hãy làm theo hướng dẫn sau:

### Windows

- **Chocolatey** (Khuyên dùng): `choco install make`
- **Winget**: `winget install GnuWin32.Make`
- **MSYS2**: `pacman -S make`
- **Git Bash**: `make` thường đi kèm với "Git for Windows SDK". Hoặc bạn có thể tải tệp `make.exe` rời và thêm vào biến môi trường PATH.

### macOS

- **Homebrew**: `brew install make`
- **Xcode Tools**: Chạy lệnh `xcode-select --install` trong terminal. Lệnh này sẽ cài đặt bộ công cụ phát triển bao gồm cả `make`.

### Linux

- **Ubuntu/Debian**: `sudo apt update && sudo apt install make`
- **Arch Linux**: `sudo pacman -S make`
- **Fedora**: `sudo dnf install make`

---

## 📋 Tham khảo nhanh

| Lệnh              | Mô tả                                                                        |
| ----------------- | ---------------------------------------------------------------------------- |
| `make check`      | Kiểm tra công cụ hệ thống (Python, uv, eSpeak, Docker, GPU, .env, v.v.)      |
| `make setup-gpu`  | Thiết lập đầy đủ cho GPU (Kiểm tra phụ thuộc tương tác + `uv sync`)          |
| `make setup-cpu`  | Thiết lập đầy đủ cho CPU (Kiểm tra phụ thuộc tương tác + tráo đổi phụ thuộc) |
| `make demo`       | Chạy ứng dụng giao diện Gradio                                               |
| `make docker-gpu` | Khởi động môi trường Docker hỗ trợ GPU                                       |
| `make docker-cpu` | Khởi động môi trường Docker chỉ dùng CPU                                     |
| `make uv`         | Cài đặt hoặc cập nhật trình quản lý gói `uv`                                 |
| `make espeak`     | Cài đặt hoặc hướng dẫn cài đặt `eSpeak NG`                                   |
| `make clean`      | Dọn dẹp các tệp build, `.venv` và bộ nhớ đệm (cache)                         |

---

## 🔍 Hướng dẫn chi tiết

### 1. `make check`

Công cụ kiểm tra môi trường. Hãy chạy lệnh này đầu tiên để xem hệ thống của bạn còn thiếu gì.

- Kiểm tra phiên bản Python (yêu cầu ≥ 3.12).
- Phát hiện GPU (NVIDIA, Intel, AMD).
- Kiểm tra `uv`, `eSpeak NG`, `Docker` và tệp `.env`.
- **Đầu ra mã màu**: `[OK]` (Xanh lá), `[WARNING]` (Vàng), `[ERROR]` (Đỏ/Lỗi nghiêm trọng).

### 2. `make setup-gpu` / `make setup-cpu`

Thiết lập tự động với **kiểm tra phụ thuộc tương tác**.

- Trước khi cài đặt các gói Python, lệnh sẽ xác minh `python`, `uv` và `eSpeak NG`.
- **Thông báo tương tác**: Nếu thiếu công cụ, lệnh sẽ hỏi bạn có muốn cài đặt không.
  - Windows: Hướng dẫn tải xuống thủ công hoặc dùng `winget`.
  - macOS: Sử dụng `brew`.
  - Linux: Sử dụng `apt` hoặc `pacman`.
- **Dừng ngay khi lỗi (Fail-Fast)**: Nếu các phụ thuộc quan trọng bị thiếu và không được cài đặt, quá trình sẽ dừng ngay lập tức để tránh tình trạng môi trường bị lỗi.

### 3. `make uv` / `make espeak`

Các lệnh cài đặt riêng lẻ cho các công cụ cốt lõi.

- `make uv`: Chạy kịch bản cài đặt chính thức cho hệ điều hành của bạn.
- `make espeak`: Thử cài đặt tự động (Winget/Brew/Apt) hoặc cung cấp liên kết tải xuống trực tiếp.

### 4. `make demo`

Sau khi thiết lập xong, hãy dùng lệnh này để khởi chạy giao diện web Gradio. Lệnh sử dụng `uv run` để đảm bảo sử dụng đúng môi trường ảo.

### 5. `make docker-gpu` / `make docker-cpu`

Các lệnh Docker được đơn giản hóa.

- Tự động tạo tệp `.env` từ `.env.example` nếu chưa có.
- Thiết lập Docker profile phù hợp với phần cứng được phát hiện.

---

## 💻 Hệ điều hành hỗ trợ

`Makefile` được thiết kế để chạy đa nền tảng và đã được kiểm thử trên:

- **Windows**: (thông qua Git Bash / MSYS2)
- **macOS**: (Intel và Apple Silicon)
- **Linux**: (Ubuntu, Debian, Arch Linux)

---

## 🧹 Dọn dẹp

Nếu bạn cần đặt lại môi trường hoặc giải phóng dung lượng đĩa:

```bash
make clean
```

Lệnh này sẽ xóa `.venv`, `__pycache__` và các tệp tạm thời khác.
