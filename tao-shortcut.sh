#!/bin/bash
# ============================================================
#  Tạo lại lối tắt "AI Audio Studio" trên Desktop (Linux)
#  Dùng khi đã cài xong nhưng chưa thấy icon. Chạy: bash tao-shortcut.sh
# ============================================================
set -e
cd "$(dirname "$0")"
APPDIR="$(pwd)"
PORT="${VIENEU_PORT:-8001}"
URL="http://127.0.0.1:${PORT}"

# Launcher trong thư mục app
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

ICON="$APPDIR/webapp/static/favicon.ico"
[ -f "$ICON" ] || ICON="audio-x-generic"

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

# Thư mục Desktop thật (hiểu cả tên đổi theo ngôn ngữ)
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
[ -d "$DESKTOP_DIR" ] || DESKTOP_DIR="$HOME/Desktop"
mkdir -p "$DESKTOP_DIR"

DESK_FILE="$DESKTOP_DIR/AI Audio Studio.desktop"
make_desktop > "$DESK_FILE"
chmod +x "$DESK_FILE"
gio set "$DESK_FILE" metadata::trusted true 2>/dev/null || true

APP_DIR="$HOME/.local/share/applications"
mkdir -p "$APP_DIR"
make_desktop > "$APP_DIR/vieneu-studio.desktop"
update-desktop-database "$APP_DIR" 2>/dev/null || true

echo "✓ Đã tạo lối tắt: $DESK_FILE"
echo "  Lần đầu có thể phải chuột phải icon → 'Allow Launching'."
