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

cd "$SPACE_DIR"
git add -A
if git diff --cached --quiet; then
  echo "✓ Không có gì thay đổi để đẩy."
  exit 0
fi
git commit -m "update from local"
git push
echo "✅ Đã đẩy lên Space. Space tự build lại (~1-2 phút, vì engine đã cache sẵn)."
