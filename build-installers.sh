#!/bin/bash
# ============================================================
#  Đóng gói bộ cài riêng cho Windows / macOS / Linux
#  Chạy:  bash build-installers.sh
#  Kết quả: dist/VieNeu-Studio-Windows.zip, -macOS.zip, -Linux.zip
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
OUT="$ROOT/dist"
rm -rf "$OUT"
mkdir -p "$OUT"

# Các file/thư mục lõi cần để chạy app (chung cho mọi nền tảng)
COMMON=(
  pyproject.toml uv.lock .python-version
  src apps webapp
  LICENSE README.md
)

# Loại bỏ rác khi sao chép
EXCLUDES=(--exclude='__pycache__' --exclude='*.pyc' --exclude='.DS_Store' --exclude='.gstack' --exclude='*.egg-info')

stage_common() {
  local dest="$1"
  mkdir -p "$dest"
  for item in "${COMMON[@]}"; do
    if [ -e "$ROOT/$item" ]; then
      rsync -a "${EXCLUDES[@]}" "$ROOT/$item" "$dest/"
    fi
  done
}

build() {
  local name="$1"; shift          # vd: Windows
  local files=("$@")              # các file cài đặc thù nền tảng
  local dir="$OUT/AI-Audio-Studio-$name"
  echo "→ Đóng gói $name..."
  stage_common "$dir"
  for f in "${files[@]}"; do
    cp "$ROOT/$f" "$dir/"
  done
  ( cd "$OUT" && zip -rq "AI-Audio-Studio-$name.zip" "AI-Audio-Studio-$name" -x '*/__pycache__/*' )
  rm -rf "$dir"
  echo "   ✓ dist/AI-Audio-Studio-$name.zip"
}

build Windows install.bat tao-shortcut.bat HUONG-DAN-WINDOWS.txt
build macOS   install.command tao-shortcut.command HUONG-DAN-MAC-LINUX.txt
build Linux   install.sh tao-shortcut.sh HUONG-DAN-MAC-LINUX.txt

echo ""
echo "============================================================"
echo "  ✅ XONG! Các bộ cài nằm trong thư mục dist/:"
( cd "$OUT" && ls -1sh *.zip )
echo "============================================================"
