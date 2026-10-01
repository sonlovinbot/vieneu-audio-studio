#!/bin/bash
# ============================================================
#  AI Audio Studio — cài bằng 1 lệnh (macOS / Linux)
#
#    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/sonlovinbot/vieneu-audio-studio/main/install-online.sh)"
#
#  Tải bộ cài mới nhất từ GitHub Releases về ~/AI-Audio-Studio rồi chạy
#  install.command / install.sh. Tải qua curl nên macOS không gắn cờ cách ly
#  → không bị chặn "Apple could not verify". Chạy lại lệnh này = cập nhật.
# ============================================================
set -euo pipefail

REPO="sonlovinbot/vieneu-audio-studio"
DEST="${VIENEU_INSTALL_DIR:-$HOME/AI-Audio-Studio}"

case "$(uname -s)" in
  Darwin) PLAT="macOS"; INSTALLER="install.command" ;;
  Linux)  PLAT="Linux"; INSTALLER="install.sh" ;;
  *) echo "❌ Hệ điều hành chưa hỗ trợ: $(uname -s). Windows hãy dùng lệnh PowerShell trong README."; exit 1 ;;
esac

URL="https://github.com/$REPO/releases/latest/download/AI-Audio-Studio-$PLAT.zip"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "============================================================"
echo "  ⚡ AI Audio Studio — cài đặt tự động ($PLAT)"
echo "     Phát triển bởi Đặng Hữu Sơn · model VieNeu-TTS"
echo "============================================================"
echo "→ Tải bộ cài mới nhất..."
curl -fL --progress-bar "$URL" -o "$TMP/app.zip"

echo "→ Giải nén vào: $DEST"
unzip -q -o "$TMP/app.zip" -d "$TMP"
mkdir -p "$DEST"
# Chép đè mã nguồn, giữ nguyên .venv / log của lần cài trước (cập nhật nhanh).
cp -R "$TMP/AI-Audio-Studio-$PLAT/." "$DEST/"
chmod +x "$DEST"/*.command "$DEST"/*.sh 2>/dev/null || true
if [ "$PLAT" = "macOS" ]; then
  /usr/bin/xattr -r -d com.apple.quarantine "$DEST" 2>/dev/null || true
fi

if [ -n "${VIENEU_NO_RUN:-}" ]; then
  echo "✓ Đã giải nén (VIENEU_NO_RUN — bỏ qua bước cài)."
  exit 0
fi
echo ""
exec bash "$DEST/$INSTALLER"
