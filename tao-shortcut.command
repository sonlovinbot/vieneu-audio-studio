#!/bin/bash
# ============================================================
#  Tạo lại icon "AI Audio Studio" trên Desktop (macOS)
#  Dùng khi đã cài xong nhưng chưa thấy icon. Nhấp đúp file này.
# ============================================================
set -e
cd "$(dirname "$0")"
APPDIR="$(pwd)"
PORT="${VIENEU_PORT:-8001}"
URL="http://127.0.0.1:${PORT}"

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

echo "✓ Đã tạo icon: ~/Desktop/AI Audio Studio.command"
echo "  Nhấp đúp icon đó để mở app."
