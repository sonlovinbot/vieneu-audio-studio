#!/bin/bash
# ============================================================
#  AI Audio Studio (Coachio Edition) — Bộ cài macOS
#  Nhấp đúp file này để cài. Mọi thứ tự động.
# ============================================================
set -e
cd "$(dirname "$0")"
APPDIR="$(pwd)"
PORT="${VIENEU_PORT:-8001}"
URL="http://127.0.0.1:${PORT}"

clear
echo "============================================================"
echo "  🦜  CÀI ĐẶT AI AUDIO STUDIO (Coachio Edition)"
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

# 2) Cài thư viện (CPU/ONNX mặc định — chạy mọi máy) ───────
echo "→ [2/3] Cài thư viện (có thể mất vài phút lần đầu)..."
uv sync

# 3) Tạo icon trên Desktop + (tùy chọn) tự chạy khi mở máy ─
echo "→ [3/3] Tạo lối tắt..."
LAUNCHER="$HOME/Desktop/AI Audio Studio.command"
cat > "$LAUNCHER" <<EOF
#!/bin/bash
# Khởi chạy AI Audio Studio rồi mở trình duyệt
export PATH="\$HOME/.local/bin:\$HOME/.cargo/bin:\$PATH"
cd "$APPDIR"
( for i in \$(seq 1 90); do
    if curl -s "$URL/api/health" >/dev/null 2>&1; then open "$URL"; break; fi
    sleep 1
  done ) &
exec uv run vieneu-studio
EOF
chmod +x "$LAUNCHER"
echo "   ✓ Đã tạo icon: ~/Desktop/AI Audio Studio.command"

# Autostart (tùy chọn lúc cài) ─────────────────────────────
echo ""
read -r -p "Bạn có muốn TỰ CHẠY khi mở máy? (y/N): " AUTO
if [[ "$AUTO" =~ ^[Yy]$ ]]; then
  PLIST="$HOME/Library/LaunchAgents/com.vieneu.studio.plist"
  mkdir -p "$HOME/Library/LaunchAgents"
  UV_BIN="$(command -v uv)"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.vieneu.studio</string>
  <key>ProgramArguments</key>
  <array>
    <string>$UV_BIN</string>
    <string>run</string>
    <string>vieneu-studio</string>
  </array>
  <key>WorkingDirectory</key><string>$APPDIR</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>$HOME/.local/bin:$HOME/.cargo/bin:/usr/bin:/bin:/usr/local/bin</string>
    <key>VIENEU_PORT</key><string>$PORT</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
  <key>StandardOutPath</key><string>$APPDIR/vieneu-studio.log</string>
  <key>StandardErrorPath</key><string>$APPDIR/vieneu-studio.log</string>
</dict>
</plist>
EOF
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST"
  echo "   ✓ Đã bật tự chạy khi mở máy (LaunchAgent)."
  echo "     Tắt tự chạy: launchctl unload \"$PLIST\""
fi

echo ""
echo "============================================================"
echo "  ✅ CÀI ĐẶT XONG!"
echo "  • Mở app: nhấp icon 'AI Audio Studio' trên Desktop"
echo "  • Hoặc chạy: uv run vieneu-studio"
echo "  • Giao diện: $URL"
echo "============================================================"
echo ""
read -r -p "Khởi chạy ngay bây giờ? (Y/n): " RUN
if [[ ! "$RUN" =~ ^[Nn]$ ]]; then
  ( for i in $(seq 1 90); do
      if curl -s "$URL/api/health" >/dev/null 2>&1; then open "$URL"; break; fi
      sleep 1
    done ) &
  exec uv run vieneu-studio
fi
