# ⚡ AI Audio Studio — Giọng nói AI tiếng Việt chạy trên máy tính của bạn

Biến văn bản tiếng Việt thành giọng nói tự nhiên, **clone giọng từ 3–5 giây audio**, tạo **hội thoại nhiều nhân vật**, và **xuất API** cho phần mềm khác (n8n, Make, script, OBS...) — chạy 100% trên máy, không cần card đồ họa.

**Phát triển bởi [Đặng Hữu Sơn](https://www.facebook.com/danghuuson.182/) — CEO & Co-Founder LovinBot AI**, dựa trên model AI mã nguồn mở [VieNeu-TTS](https://github.com/pnnbao97/VieNeu-TTS) của Phạm Nguyễn Ngọc Bảo.

## 🚀 Cài đặt — chỉ 1 lệnh (khuyên dùng)

> [!WARNING]
> **Người dùng MacBook đọc kỹ:** nếu tải file `.zip` bằng trình duyệt rồi nhấp đúp `install.command`, macOS sẽ báo **"install.command" Not Opened — Apple could not verify…** và chỉ có nút *Done / Move to Trash*. Đây **không phải virus**: phần mềm chưa mua chứng chỉ ký số của Apple nên macOS chặn mặc định.
>
> 👉 **Cách dễ nhất: cài bằng 1 lệnh bên dưới** — không hiện cảnh báo nào. Nếu đã lỡ tải file zip, xem [cách mở file bị chặn](#-đã-tải-file-zip-và-bị-macos-chặn).

### 🍎 macOS (và 🐧 Linux)

1. Mở **Terminal** (bấm `⌘ + Space`, gõ `Terminal`, Enter).
2. Dán lệnh này vào rồi nhấn **Enter**:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/sonlovinbot/vieneu-audio-studio/main/install-online.sh)"
```

3. Chờ cài xong (5–10 phút lần đầu). Khi hỏi *tự chạy khi mở máy?* gõ **y** rồi Enter. Trình duyệt tự mở **http://127.0.0.1:8001**.

### 🪟 Windows 10/11

1. Bấm **Start**, gõ `PowerShell`, mở **Windows PowerShell**.
2. Dán lệnh này vào rồi nhấn **Enter**:

```powershell
irm https://raw.githubusercontent.com/sonlovinbot/vieneu-audio-studio/main/install-online.ps1 | iex
```

3. Khi hỏi *TU CHAY khi mo may?* gõ **y** rồi Enter; hỏi *Khoi chay ngay?* nhấn Enter.

Phần mềm được cài vào thư mục **AI-Audio-Studio** trong thư mục người dùng, có icon **AI Audio Studio** trên Desktop. **Chạy lại đúng lệnh trên = cập nhật lên bản mới nhất** (giữ nguyên giọng đã lưu và lịch sử).

**Yêu cầu:** RAM 8 GB (tối thiểu 4 GB) · ổ trống ~5 GB · Internet ở lần cài đầu tiên (sau đó chạy offline) · không cần card đồ họa.

## ⬇️ Hoặc tải bộ cài thủ công (.zip)

| Hệ điều hành | Tải về | Cách cài |
|---|---|---|
| 🍎 **macOS** 12+ (chip M hoặc Intel) | [**AI-Audio-Studio-macOS.zip**](https://github.com/sonlovinbot/vieneu-audio-studio/releases/latest/download/AI-Audio-Studio-macOS.zip) | Giải nén → nhấp đúp `install.command` → bị chặn thì làm theo mục bên dưới |
| 🪟 **Windows** 10/11 (64-bit) | [**AI-Audio-Studio-Windows.zip**](https://github.com/sonlovinbot/vieneu-audio-studio/releases/latest/download/AI-Audio-Studio-Windows.zip) | Extract All → nhấp đúp `install.bat` → SmartScreen: **More info → Run anyway** |
| 🐧 **Linux** 64-bit | [**AI-Audio-Studio-Linux.zip**](https://github.com/sonlovinbot/vieneu-audio-studio/releases/latest/download/AI-Audio-Studio-Linux.zip) | Giải nén → `bash install.sh` |

Tất cả phiên bản và ghi chú cập nhật: [**Releases**](https://github.com/sonlovinbot/vieneu-audio-studio/releases).

### 🔓 Đã tải file zip và bị macOS chặn?

**Cách 1 — qua Cài đặt hệ thống (macOS 15 Sequoia trở lên):**
1. Nhấp đúp `install.command` một lần → bấm **Done** khi hiện cảnh báo.
2. Mở **🍎 → System Settings (Cài đặt hệ thống) → Privacy & Security (Quyền riêng tư & Bảo mật)**.
3. Kéo xuống mục **Security**, thấy dòng *"install.command" was blocked…* → bấm **Open Anyway (Vẫn mở)** → nhập mật khẩu máy.
4. Nhấp đúp `install.command` lần nữa → bấm **Open Anyway** → bộ cài chạy.

> macOS 14 trở về trước: chỉ cần **chuột phải** vào `install.command` → **Open** → **Open**.

**Cách 2 — 1 lệnh Terminal:** gõ `xattr -cr ` (có dấu cách ở cuối), **kéo thả thư mục AI-Audio-Studio-macOS** vào cửa sổ Terminal, nhấn Enter — sau đó nhấp đúp `install.command` bình thường.

### Sau khi cài

Lần sau chỉ cần mở icon **AI Audio Studio** trên Desktop (hoặc để tự chạy khi mở máy). Lần đầu mở, app có **hướng dẫn từng bước**: kiểm tra cấu hình máy → tải model giọng nói → thử tạo giọng.

> [!IMPORTANT]
> **Đây là phần mềm chạy trên máy tính của bạn.** Khi máy bật và app đang chạy, bạn dùng được giao diện và các phần mềm khác gọi được **API** tại `http://127.0.0.1:8001`. Khi tắt máy, máy ngủ hoặc thoát app thì giao diện và API ngừng hoạt động.

## 🎧 Nghe thử 25 giọng có sẵn

Mỗi giọng đọc cùng một câu mẫu: *"Chào bạn, đây là giọng đọc …. Giọng đọc được tạo bằng trí tuệ nhân tạo, sử dụng mô hình VieNeu TTS với giấy phép mã nguồn mở. Các tính năng của phần mềm này được phát triển bởi anh Đặng Hữu Sơn. Cảm ơn bạn đã sử dụng, chúc bạn có trải nghiệm thật tốt."*

Bấm **▶ Nghe thử** để mở trình phát của GitHub. Trong app, vào mục **🎧 Kho giọng** để nghe và chọn nhanh.

| Giọng | Giới tính | Vùng miền | Phong cách | Audio |
|---|---|---|---|---|
| ⭐ **Adam bựa** | Nam | Miền Bắc | Phong cách tự nhiên | [▶ Nghe thử](https://github.com/sonlovinbot/vieneu-audio-studio/blob/main/webapp/static/previews/adam-bua.mp3) |
| ⭐ **Trúc Ly** | Nữ | Miền Bắc | Phong cách tự nhiên | [▶ Nghe thử](https://github.com/sonlovinbot/vieneu-audio-studio/blob/main/webapp/static/previews/truc-ly.mp3) |
| ⭐ **Thiện Minh** | Nam | Miền Bắc | Phong cách kể chuyện | [▶ Nghe thử](https://github.com/sonlovinbot/vieneu-audio-studio/blob/main/webapp/static/previews/thien-minh.mp3) |
| ⭐ **Mai Anh** | Nữ | Miền Bắc | Phong cách tin tức | [▶ Nghe thử](https://github.com/sonlovinbot/vieneu-audio-studio/blob/main/webapp/static/previews/mai-anh.mp3) |
| ⭐ **Hải Đăng** | Nam | Miền Bắc | Phong cách tự nhiên | [▶ Nghe thử](https://github.com/sonlovinbot/vieneu-audio-studio/blob/main/webapp/static/previews/hai-dang.mp3) |
| ⭐ **Thùy Dung** | Nữ | Miền Nam | Phong cách tin tức | [▶ Nghe thử](https://github.com/sonlovinbot/vieneu-audio-studio/blob/main/webapp/static/previews/thuy-dung.mp3) |
| ⭐ **Thiền Tâm Đức** | Nam | Miền Bắc | Phong cách kể chuyện | [▶ Nghe thử](https://github.com/sonlovinbot/vieneu-audio-studio/blob/main/webapp/static/previews/thien-tam-duc.mp3) |
| ⭐ **Ngọc Huyền** | Nữ | Miền Bắc | Giọng đọc tự nhiên | [▶ Nghe thử](https://github.com/sonlovinbot/vieneu-audio-studio/blob/main/webapp/static/previews/ngoc-huyen.mp3) |
| ⭐ **Quang Sơn** | Nam | Miền Trung | Phong cách tự nhiên | [▶ Nghe thử](https://github.com/sonlovinbot/vieneu-audio-studio/blob/main/webapp/static/previews/quang-son.mp3) |
| ⭐ **Ngọc Trân** | Nữ | Miền Trung | Phong cách tự nhiên | [▶ Nghe thử](https://github.com/sonlovinbot/vieneu-audio-studio/blob/main/webapp/static/previews/ngoc-tran.mp3) |
| **Minh Đức** | Nam | Miền Bắc | Phong cách tin tức | [▶ Nghe thử](https://github.com/sonlovinbot/vieneu-audio-studio/blob/main/webapp/static/previews/minh-duc.mp3) |
| **Phạm Tuyên** | Nam | Miền Bắc | Phong cách tự nhiên | [▶ Nghe thử](https://github.com/sonlovinbot/vieneu-audio-studio/blob/main/webapp/static/previews/pham-tuyen.mp3) |
| **Thái Sơn** | Nam | Miền Nam | Phong cách kể chuyện | [▶ Nghe thử](https://github.com/sonlovinbot/vieneu-audio-studio/blob/main/webapp/static/previews/thai-son.mp3) |
| **Xuân Vĩnh** | Nam | Miền Bắc | Phong cách tự nhiên | [▶ Nghe thử](https://github.com/sonlovinbot/vieneu-audio-studio/blob/main/webapp/static/previews/xuan-vinh.mp3) |
| **Thanh Bình** | Nam | Miền Bắc | Phong cách kể chuyện | [▶ Nghe thử](https://github.com/sonlovinbot/vieneu-audio-studio/blob/main/webapp/static/previews/thanh-binh.mp3) |
| **Ngọc Linh** | Nữ | Miền Bắc | Phong cách kể chuyện | [▶ Nghe thử](https://github.com/sonlovinbot/vieneu-audio-studio/blob/main/webapp/static/previews/ngoc-linh.mp3) |
| **Đoan Trang** | Nữ | Miền Bắc | Phong cách tự nhiên | [▶ Nghe thử](https://github.com/sonlovinbot/vieneu-audio-studio/blob/main/webapp/static/previews/doan-trang.mp3) |
| **Thục Đoan** | Nữ | Miền Nam | Phong cách kể chuyện | [▶ Nghe thử](https://github.com/sonlovinbot/vieneu-audio-studio/blob/main/webapp/static/previews/thuc-doan.mp3) |
| **Minh Triết** | Nam | Miền Nam | Phong cách tin tức | [▶ Nghe thử](https://github.com/sonlovinbot/vieneu-audio-studio/blob/main/webapp/static/previews/minh-triet.mp3) |
| **Mỹ Duyên** | Nữ | Miền Nam | Phong cách đọc truyện | [▶ Nghe thử](https://github.com/sonlovinbot/vieneu-audio-studio/blob/main/webapp/static/previews/my-duyen.mp3) |
| **Quỳnh Anh** | Nữ | Miền Bắc | Phong cách đọc truyện | [▶ Nghe thử](https://github.com/sonlovinbot/vieneu-audio-studio/blob/main/webapp/static/previews/quynh-anh.mp3) |
| **Đức Trí** | Nam | Miền Nam | Phong cách đọc truyện | [▶ Nghe thử](https://github.com/sonlovinbot/vieneu-audio-studio/blob/main/webapp/static/previews/duc-tri.mp3) |
| **Kim Thanh** | Nữ | Miền Nam | Phong cách đọc truyện | [▶ Nghe thử](https://github.com/sonlovinbot/vieneu-audio-studio/blob/main/webapp/static/previews/kim-thanh.mp3) |
| **Adam** | Nam | Miền Nam | Giọng đọc tự nhiên | [▶ Nghe thử](https://github.com/sonlovinbot/vieneu-audio-studio/blob/main/webapp/static/previews/adam.mp3) |
| **Quốc Tuấn** | Nam | Miền Bắc | Phong cách tự nhiên | [▶ Nghe thử](https://github.com/sonlovinbot/vieneu-audio-studio/blob/main/webapp/static/previews/quoc-tuan.mp3) |

## ✨ Tính năng

- 🔊 **Sinh giọng** — 25 giọng có sẵn (nghe thử từng giọng trong **Kho giọng**), chèn cảm xúc `[cười]` `[thở dài]` `[hắng giọng]`, bộ đếm ký tự (tối đa 5.000 ký tự/lần).
- 🎙️ **Clone giọng** — từ 3–5 giây audio mẫu; lưu lại kèm nhãn cảm xúc (vui, buồn, thì thầm...) để dùng lại.
- 💬 **Hội thoại** — nhiều nhân vật, mỗi lượt một giọng, làm podcast.
- ⭐ **Thư viện** — Giọng của tôi và Lịch sử 50 lượt gần nhất.
- 🔌 **API** — ví dụ curl / JavaScript / Python và prompt sẵn cho AI agent.
- 🚀 **Hướng dẫn lần đầu** — kiểm tra cấu hình máy, tải model, thử tạo giọng.
- 🌗 Giao diện sáng / tối.

## 🙏 Ghi nhận

- Phần mềm AI Audio Studio (giao diện, tính năng, bộ cài): **Đặng Hữu Sơn** — [Facebook](https://www.facebook.com/danghuuson.182/).
- Model AI và SDK giọng nói: **[VieNeu-TTS](https://github.com/pnnbao97/VieNeu-TTS)** — thiết kế và huấn luyện bởi **Phạm Nguyễn Ngọc Bảo**, giấy phép Apache 2.0. Vui lòng giữ nguyên phần ghi nhận tác giả khi phân phối lại.
