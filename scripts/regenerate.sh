#!/bin/sh
# 상류 devel 원본에서 언어팩 적용 상태 전체를 다시 만든다 — 한 번에, 같은 순서로.
#
# 손으로 일부만 다시 돌리다 두 번 사고가 났다(카탈로그를 덮어써 대화상자 키 823개가 날아감).
# 정본은 translations/ 이고 나머지는 전부 이 스크립트의 산출물이다.
#
#   sh scripts/regenerate.sh            # 현재 체크아웃 위에서 rhwp-studio 만 되돌리고 다시 만든다
set -eu
root=$(cd "$(dirname "$0")/.." && pwd)
repo="$root/work/rhwp"
studio="$repo/rhwp-studio"
catalog="$root/translations/catalog"
helpers="$root/build/display-helpers.tsv"

[ -d "$studio" ] || { echo "regenerate: 작업 사본이 없다 — 먼저 sh scripts/setup-work.sh"; exit 1; }
mkdir -p "$root/build" "$catalog"

# 메인테이너가 PR 가지에 올린 보정(overlay/patches/*.patch)을 정본에 흡수한다. 이미 상류에 들어갔으면 건너뛴다.
# 파일 이름의 커밋(pr7152-e917cffb9-…)이 origin/devel 에 들어 있으면 먼저 건너뛴다 — 병합 뒤 상류가 같은 자리를
# 또 고치면 역적용 검사가 실패하기 때문이다(#7171 이 그랬다).
apply_patch() {
  source_commit=$(basename "$1" | sed -n 's/^pr[0-9]*-\([0-9a-f]\{7,40\}\)-.*/\1/p')
  if [ -n "$source_commit" ] && git -C "$repo" merge-base --is-ancestor "$source_commit" origin/devel 2>/dev/null; then
    echo "   $(basename "$1"): 상류에 병합됨($source_commit)"
  elif git -C "$repo" apply --reverse --check "$1" 2>/dev/null; then
    echo "   $(basename "$1"): 이미 반영됨"
  elif git -C "$repo" apply "$1"; then
    echo "   $(basename "$1"): 적용"
  else
    echo "regenerate: 패치 $(basename "$1") 가 맞지 않는다 — 상류가 그 자리를 바꿨는지 볼 것" >&2
    exit 1
  fi
}

echo "== 0. 상류 원본으로 되돌림 + 언어팩 런타임(overlay) 얹기"
git -C "$repo" checkout -q origin/devel -- rhwp-studio/index.html rhwp-studio/src/ui rhwp-studio/src/command \
  rhwp-studio/tests rhwp-studio/src/main.ts rhwp-studio/src/styles/style-bar.css \
  rhwp-studio/src/engine/header-footer-mode.ts rhwp-studio/src/view/canvas-view.ts \
  rhwp-studio/src/view/page-indicator.ts rhwp-studio/e2e/responsive.test.mjs \
  rhwp-chrome/build.mjs rhwp-firefox/build.mjs scripts/frontend-extension-dist.test.mjs
printf '{\n}\n' > "$catalog/ko.json"
# 언어팩 런타임(src/i18n·locale-init·i18n 테스트)은 overlay/ 가 정본이다. 상류 트리에 그대로 얹는다.
cp -R "$root/overlay/rhwp-studio/." "$studio/"
# PR #7152 메인테이너 보정 e917cffb9 중 변환 전에 들어가야 하는 부분(변환기가 파일 머리에 import 를 넣으면 문맥이 어긋난다)
apply_patch "$root/overlay/patches/pr7152-e917cffb9-pre.patch"

echo "== 1. 도우미 판정"
python3 "$root/scripts/verify-helpers.py" "$studio/src/ui" "$helpers" > "$root/build/step-1.log"
head -1 "$root/build/step-1.log"

echo "== 2. 변환 (마크업 → 대화상자 → 표 → 명령)"
python3 "$root/scripts/apply-i18n-html.py" "$studio/index.html" --catalog "$catalog" --write > "$root/build/step-2.log"
head -1 "$root/build/step-2.log"
# 상류에 이미 병합된 키(t('…') 로 바뀌어 한글이 없는 자리)를 심는다 — 마크업 변환이 카탈로그를 새로 쓰므로 그 뒤에
python3 "$root/scripts/seed-catalog.py" "$repo" "$catalog/ko.json" "$root/build/seed-keys.json"
python3 "$root/scripts/apply-i18n-ts.py" "$studio/src/ui" "$catalog/ko.json" --helpers "$helpers" --write > "$root/build/step-3.log"
head -1 "$root/build/step-3.log"
python3 "$root/scripts/apply-i18n-tables.py" "$studio/src/ui" "$catalog/ko.json" "$helpers" --write > "$root/build/step-4.log"
head -1 "$root/build/step-4.log"
python3 "$root/scripts/apply-i18n-ts.py" "$studio/src/command/commands" "$catalog/ko.json" --helpers "$helpers" --write > "$root/build/step-5.log"
head -1 "$root/build/step-5.log"

echo "== 3. 손 조정(main.ts·재키잉·css·locale-init)"
python3 "$root/scripts/apply-extras.py" "$studio" "$catalog/ko.json"
# 같은 보정의 CSS 부분 — apply-extras 가 붙인 영어 폭 보정 블록까지 고치므로 그 뒤에 적용한다
apply_patch "$root/overlay/patches/pr7152-e917cffb9-css.patch"

echo "== 4. 번역 → 카탈로그 .ts"
# 파이프 뒤 grep 이 앞 명령의 실패를 삼키지 않게 출력은 파일로 받는다(거짓 'ok' 를 낸 적이 있다).
if ! sh "$root/scripts/rebuild-langpack.sh" > "$root/build/rebuild-langpack.log" 2>&1; then
  cat "$root/build/rebuild-langpack.log" >&2
  echo "regenerate: 카탈로그 만들기 실패" >&2
  exit 1
fi
grep -E "en.json|번역하지" "$root/build/rebuild-langpack.log" || true
python3 "$root/scripts/seed-catalog.py" --check "$catalog/ko.json" "$root/build/seed-keys.json"

echo "== 5. 테스트 상태(4단계)"
sh "$root/scripts/stage-tests.sh" 4 "$catalog/ko.json" > "$root/build/stage-tests.log"
tail -1 "$root/build/stage-tests.log"

if [ -f "$catalog/en.todo.json" ]; then
  echo "regenerate: 미번역이 있다(화면에는 원문 한국어로 나온다):"
  python3 -c "import json;[print('   ',repr(v)) for v in sorted(json.load(open('$catalog/en.todo.json')))]"
  # 번역할 것만 엑셀로 모은다. 이미 번역한 문구는 번역 메모리가 값으로 찾아 자동으로 채웠다.
  python3 "$root/scripts/export-delta-xlsx.py" || true
  echo "regenerate: 엑셀을 번역한 뒤 sh scripts/apply-translations.sh <그 파일>"
  exit 2
fi
echo "regenerate: ok"
