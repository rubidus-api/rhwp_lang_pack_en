#!/bin/sh
# 새로 받은 사람이 재생성 환경을 한 번에 세운다.
#
#   sh scripts/setup-work.sh            # 상류 devel 최신
#   sh scripts/setup-work.sh <커밋>      # 특정 상류 커밋에 고정(재현할 때)
#
# 하는 일
#   1. work/rhwp 에 edwardkim/rhwp 를 받는다(이미 있으면 devel 만 가져온다)
#   2. 트리를 그 커밋에 세우고 가지 tmp/full 을 만든다(build-stages.sh 가 여기서 단계를 쌓는다)
#   3. 무회귀 검사 기준(work/index.baseline.html, work/ui.baseline/)을 그 커밋의 원본으로 뜬다
#   4. rhwp-studio 의존성을 설치한다(npm ci)
# 네트워크를 쓴다. 상류 작업 사본(work/)은 이 저장소가 보관하지 않는다.
set -eu
root=$(cd "$(dirname "$0")/.." && pwd)
repo="$root/work/rhwp"
studio="$repo/rhwp-studio"
upstream=${RHWP_UPSTREAM:-https://github.com/edwardkim/rhwp.git}

for tool in git node npm python3; do
  command -v "$tool" >/dev/null 2>&1 || { echo "setup-work: $tool 이 필요하다" >&2; exit 1; }
done

mkdir -p "$root/work"
if [ ! -d "$repo/.git" ]; then
  echo "== 1. 상류 받기 (devel)"
  git clone --branch devel --single-branch "$upstream" "$repo"
else
  echo "== 1. 상류 devel 가져오기"
  git -C "$repo" fetch origin devel
fi

ref=${1:-origin/devel}
sha=$(git -C "$repo" rev-parse --verify "$ref^{commit}")
if [ -n "$(git -C "$repo" status --porcelain --untracked-files=no)" ]; then
  echo "setup-work: work/rhwp 에 커밋 안 된 변경이 있다 — 지우지 않는다. 확인 후 다시 실행할 것" >&2
  exit 1
fi
echo "== 2. 트리를 $sha 에 세움"
# origin/devel 을 이 커밋에 고정한다 — 재생성·단계 쌓기·관문 검사가 모두 이 이름을 기준으로 삼는다.
git -C "$repo" update-ref refs/remotes/origin/devel "$sha"
git -C "$repo" branch -f devel "$sha" 2>/dev/null || git -C "$repo" update-ref refs/heads/devel "$sha"
git -C "$repo" checkout -q -B tmp/full "$sha"

echo "== 3. 무회귀 기준 스냅샷"
git -C "$repo" show "$sha:rhwp-studio/index.html" > "$root/work/index.baseline.html"
rm -rf "$root/work/ui.baseline"
mkdir -p "$root/work/ui.baseline"
cp "$studio"/src/ui/*.ts "$root/work/ui.baseline/"

echo "== 4. 의존성"
npm --prefix "$studio" ci --no-audit --no-fund >/dev/null

echo
echo "setup-work: ok — 다음은 sh scripts/regenerate.sh"
echo "  빌드·관문 검사(verify-gates.sh)에는 새 WASM 이 필요하다: (cd work/rhwp && sh scripts/wasm-pack-locked.sh --target web --dev)"
echo "  변경분 엑셀 도구에는 openpyxl 이 필요하다: pip install --user openpyxl"
