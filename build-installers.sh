#!/bin/bash
# ============================================================
#  Đóng gói bộ cài riêng cho Windows / macOS / Linux
#  Chạy:  bash build-installers.sh
#  Kết quả: dist/VieNeu-Studio-Windows.zip, -macOS.zip, -Linux.zip
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
# EDITION=Global bash build-installers.sh → dist/global/AI-Audio-Studio-Global-*.zip (bản đa ngôn ngữ phát hành riêng).
# Thư mục bên trong zip giữ tên AI-Audio-Studio-<OS> để lệnh cài 1 dòng dùng chung.
PREFIX="AI-Audio-Studio"
OUT="$ROOT/dist"
if [ "${EDITION:-}" = "Global" ]; then PREFIX="AI-Audio-Studio-Global"; OUT="$ROOT/dist/global"; fi
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
  if [ "$PREFIX" != "AI-Audio-Studio" ]; then
    # Bản Global: kèm hướng dẫn Đa ngôn ngữ; lệnh cài 1 dòng trong hướng dẫn trỏ về kênh global
    cp "$ROOT/HUONG-DAN-DA-NGON-NGU.txt" "$dir/"
    for t in "$dir"/HUONG-DAN-MAC-LINUX.txt; do
      [ -f "$t" ] && sed -i.bak 's|/bin/bash -c "\$(curl|VIENEU_CHANNEL=global /bin/bash -c "$(curl|' "$t" && rm -f "$t.bak"
    done
  fi
  ( cd "$OUT" && zip -rq "$PREFIX-$name.zip" "AI-Audio-Studio-$name" -x '*/__pycache__/*' )
  rm -rf "$dir"
  echo "   ✓ $OUT/$PREFIX-$name.zip"
}

build Windows install.bat tao-shortcut.bat HUONG-DAN-WINDOWS.txt
build macOS   install.command tao-shortcut.command HUONG-DAN-MAC-LINUX.txt
build Linux   install.sh tao-shortcut.sh HUONG-DAN-MAC-LINUX.txt

echo ""
echo "============================================================"
echo "  ✅ XONG! Các bộ cài nằm trong thư mục dist/:"
( cd "$OUT" && ls -1sh *.zip )
echo "============================================================"
