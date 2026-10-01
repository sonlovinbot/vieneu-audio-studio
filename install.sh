#!/bin/bash
# ============================================================
#  AI Audio Studio (Coachio Edition) — Bộ cài Linux
#  Chạy:  bash install.sh   (hoặc ./install.sh)
# ============================================================
set -e
cd "$(dirname "$0")"
APPDIR="$(pwd)"
PORT="${VIENEU_PORT:-8001}"
URL="http://127.0.0.1:${PORT}"

echo "============================================================"
echo "  🦜  CÀI ĐẶT AI AUDIO STUDIO (Coachio Edition) — Linux"
echo "============================================================"
echo "  Thư mục: $APPDIR"
echo ""

# 1) Cài uv nếu chưa có ────────────────────────────────────
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  echo "→ [1/3] Cài trình quản lý uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
else
  echo "→ [1/3] uv đã có sẵn ($(uv --version))."
fi

# 2) Cài thư viện (CPU/ONNX mặc định) ──────────────────────
echo "→ [2/3] Cài thư viện (có thể mất vài phút lần đầu)..."
uv sync

# 3) Tạo lối tắt .desktop trên Desktop + menu ứng dụng ──────
echo "→ [3/3] Tạo lối tắt..."

# Launcher script trong thư mục app (khởi chạy + mở trình duyệt)
LAUNCHER="$APPDIR/vieneu-studio-launcher.sh"
cat > "$LAUNCHER" <<EOF
#!/bin/bash
export PATH="\$HOME/.local/bin:\$HOME/.cargo/bin:\$PATH"
cd "$APPDIR"
( for i in \$(seq 1 90); do
    if curl -s "$URL/api/health" >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1; break; fi
    sleep 1
  done ) &
exec uv run vieneu-studio
EOF
chmod +x "$LAUNCHER"

# Chọn icon: dùng favicon.ico nếu có, không thì icon hệ thống
ICON="$APPDIR/webapp/static/favicon.ico"
[ -f "$ICON" ] || ICON="audio-x-generic"

# Nội dung file .desktop
make_desktop() {
  cat <<EOF
[Desktop Entry]
Type=Application
Name=AI Audio Studio
Comment=Vietnamese TTS — sinh giọng, clone giọng, hội thoại
Exec=bash "$LAUNCHER"
Icon=$ICON
Terminal=true
Categories=AudioVideo;Audio;
EOF
}

# Thư mục Desktop THẬT (xdg-user-dir hiểu cả tên đã đổi theo ngôn ngữ,
# vd "Bureau", "Escritorio" — tương tự vụ OneDrive trên Windows)
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
[ -d "$DESKTOP_DIR" ] || DESKTOP_DIR="$HOME/Desktop"
mkdir -p "$DESKTOP_DIR"

DESK_FILE="$DESKTOP_DIR/AI Audio Studio.desktop"
make_desktop > "$DESK_FILE"
chmod +x "$DESK_FILE"
# Đánh dấu "tin cậy" để bấm được ngay trên GNOME (bỏ qua nếu không có gio)
gio set "$DESK_FILE" metadata::trusted true 2>/dev/null || true
echo "   ✓ Đã tạo icon trên Desktop: $DESK_FILE"

# Thêm vào menu ứng dụng
APP_DIR="$HOME/.local/share/applications"
mkdir -p "$APP_DIR"
make_desktop > "$APP_DIR/vieneu-studio.desktop"
update-desktop-database "$APP_DIR" 2>/dev/null || true
echo "   ✓ Đã thêm vào menu ứng dụng."

# Autostart (tùy chọn) ─────────────────────────────────────
echo ""
read -r -p "Bạn có muốn TỰ CHẠY khi mở máy? (y/N): " AUTO
if [[ "$AUTO" =~ ^[Yy]$ ]]; then
  AUTOSTART_DIR="$HOME/.config/autostart"
  mkdir -p "$AUTOSTART_DIR"
  {
    make_desktop
    echo "X-GNOME-Autostart-enabled=true"
  } > "$AUTOSTART_DIR/vieneu-studio.desktop"
  echo "   ✓ Đã bật tự chạy khi mở máy."
  echo "     Tắt: xóa $AUTOSTART_DIR/vieneu-studio.desktop"
fi

echo ""
echo "============================================================"
echo "  ✅ CÀI ĐẶT XONG!"
echo "  • Mở app: nhấp icon 'AI Audio Studio' trên Desktop"
echo "    (lần đầu có thể phải chuột phải → 'Allow Launching')"
echo "  • Hoặc chạy: uv run vieneu-studio"
echo "  • Giao diện: $URL"
echo "============================================================"
echo ""
read -r -p "Khởi chạy ngay bây giờ? (Y/n): " RUN
if [[ ! "$RUN" =~ ^[Nn]$ ]]; then
  ( for i in $(seq 1 90); do
      if curl -s "$URL/api/health" >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1; break; fi
      sleep 1
    done ) &
  exec uv run vieneu-studio
fi
