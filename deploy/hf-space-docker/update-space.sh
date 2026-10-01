#!/usr/bin/env bash
# ---------------------------------------------------------------
# Đồng bộ webapp/ (bản local) lên HF Space rồi push tự động.
#
# Dùng 1 lần đầu: git clone Space về máy, vd:
#   git clone https://huggingface.co/spaces/<ten-ban>/vieneu-studio ~/vieneu-space
#
# Mỗi lần muốn update:
#   ./deploy/hf-space-docker/update-space.sh ~/vieneu-space
# ---------------------------------------------------------------
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SPACE_DIR="${1:?Cần truyền đường dẫn tới thư mục Space đã git clone. Vd: ./update-space.sh ~/vieneu-space}"

if [ ! -d "$SPACE_DIR/.git" ]; then
  echo "❌ '$SPACE_DIR' chưa phải git repo của Space."
  echo "   Hãy clone trước:  git clone https://huggingface.co/spaces/<ten-ban>/vieneu-studio \"$SPACE_DIR\""
  exit 1
fi

echo "→ Đồng bộ webapp/, Dockerfile, README.md từ local sang Space..."
rsync -a --delete \
  --exclude='__pycache__' --exclude='*.pyc' --exclude='.DS_Store' --exclude='.gstack' \
  "$REPO_ROOT/webapp/" "$SPACE_DIR/webapp/"
cp "$REPO_ROOT/deploy/hf-space-docker/Dockerfile" "$SPACE_DIR/Dockerfile"
cp "$REPO_ROOT/deploy/hf-space-docker/README.md"  "$SPACE_DIR/README.md"

# Bộ cài cho onboarding (tạo bằng: bash build-installers.sh). HF bắt buộc file
# nhị phân đi qua Git LFS/Xet nên track *.zip trước khi add.
mkdir -p "$SPACE_DIR/downloads"
echo "Bộ cài .zip cho nút Tải bộ cài (onboarding)." > "$SPACE_DIR/downloads/README.txt"
if ls "$REPO_ROOT"/dist/AI-Audio-Studio-*.zip >/dev/null 2>&1; then
  ( cd "$SPACE_DIR" && git lfs install --local >/dev/null 2>&1 && git lfs track "downloads/*.zip" >/dev/null ) \
    || echo "⚠️  Chưa có git-lfs — cài bằng: brew install git-lfs (nếu push bị từ chối file .zip)."
  cp "$REPO_ROOT"/dist/AI-Audio-Studio-*.zip "$SPACE_DIR/downloads/"
else
  echo "⚠️  Chưa có bộ cài trong dist/ — chạy: bash build-installers.sh"
fi

cd "$SPACE_DIR"
git add -A
if git diff --cached --quiet; then
  echo "✓ Không có gì thay đổi để đẩy."
  exit 0
fi
git commit -m "update from local"
git push
echo "✅ Đã đẩy lên Space. Space tự build lại (~1-2 phút, vì engine đã cache sẵn)."
