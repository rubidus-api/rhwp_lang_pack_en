#!/bin/sh
# 단계 브랜치 4개를 현재 작업 트리(= regenerate.sh 가 만든 전체 상태)에서 다시 쌓는다.
#
# 전제: 트리 전체가 최신 origin/devel 체크아웃 위에 있고, 그 위에서 regenerate.sh 가
# 막 돈 상태(옛 브랜치 체크아웃 위에서 돌리면 src/core 등이 옛것으로 남는다 — LESSONS).
# 커밋 메시지는 docs/manual/stage-msgs/msg{1..4}.txt (수치는 실행 전에 손봐 둘 것).
set -eu
R=$(cd "$(dirname "$0")/.." && pwd)
W=$R/work/rhwp
ST=$W/rhwp-studio
CAT=$R/translations/catalog
TMP=$R/build/stage-build
mkdir -p $TMP
cp $R/docs/manual/stage-msgs/msg1.txt $R/docs/manual/stage-msgs/msg2.txt \
   $R/docs/manual/stage-msgs/msg3.txt $R/docs/manual/stage-msgs/msg4.txt $TMP/
G="git -C $W"   # 신원은 전역 설정(rubidus-api) — 저장소별 -c 지정 금지

# 0. 전체 상태 스냅샷 — 작업 트리(= regenerate 결과)를 tmp/full 에 커밋한다.
# ★예전에는 여기서 checkout -f·reset --hard·clean 을 먼저 해서, 커밋 안 된 재생성 결과를 지웠다.
#   작업 트리를 버리는 명령은 스냅샷을 뜬 **뒤에만** 쓴다.
BASE=$(git -C $W rev-parse origin/devel)
git -C $W checkout -q -B tmp/full          # 시작점 없이 -B: 작업 트리를 그대로 두고 가지만 옮긴다
if ! git -C $W merge-base --is-ancestor "$BASE" HEAD; then
  echo "build-stages: 작업 트리가 origin/devel($BASE) 위에 있지 않다 — 새 devel 로 트리를 세운 뒤 regenerate 할 것" >&2
  exit 1
fi
# rhwp-studio 밖에서 바꾸는 파일(확장 빌드)도 스냅샷에 담는다 — 빠뜨리면 4단계 불변식이 같이 속는다.
$G add -A rhwp-studio rhwp-chrome/build.mjs rhwp-firefox/build.mjs scripts/frontend-extension-dist.test.mjs
$G commit -q -m "tmp: full stage-4 tree on new devel" || true
FULL=$(git -C $W rev-parse tmp/full)
echo "tmp/full = $FULL"

filter_locales() {   # $1 = 단계 번호(카운트 표시용)
  LP_ROOT=$R python3 - "$1" <<'PY'
import json, pathlib, re, subprocess, sys
import os
R = pathlib.Path(os.environ['LP_ROOT'])
ST = R/'work/rhwp/rhwp-studio'
ko = json.load(open(R/'translations/catalog/ko.json', encoding='utf-8'))
en = json.load(open(R/'translations/catalog/en.json', encoding='utf-8'))
blobs = []
for p in [ST/'index.html', ST/'src/main.ts', ST/'src/engine/header-footer-mode.ts', ST/'src/view/canvas-view.ts', ST/'src/view/page-indicator.ts']:
    if p.exists(): blobs.append(p.read_text(encoding='utf-8'))
for d in [ST/'src/ui', ST/'src/command/commands']:
    for p in sorted(d.glob('*.ts')):
        blobs.append(p.read_text(encoding='utf-8'))
text = '\n'.join(blobs)
keys = {k for k in ko if f"'{k}'" in text or f'"{k}"' in text}
fko = {k: ko[k] for k in keys}
fen = {k: en[k] for k in keys if k in en}
out = pathlib.Path(R/'build/stage-build/stage-cat')
out.mkdir(exist_ok=True)
json.dump(fko, open(out/'ko.json','w',encoding='utf-8'), ensure_ascii=False, indent=2, sort_keys=True)
json.dump(fen, open(out/'en.json','w',encoding='utf-8'), ensure_ascii=False, indent=2, sort_keys=True)
sc = R/'scripts/write-catalog-ts.py'
loc = ST/'src/i18n/locales'
loc.mkdir(parents=True, exist_ok=True)
subprocess.run(['python3', sc, out/'ko.json', loc/'ko.ts', 'ko'], check=True, capture_output=True)
subprocess.run(['python3', sc, out/'en.json', loc/'en.ts', 'en'], check=True, capture_output=True)
print(f"단계 {sys.argv[1]}: 카탈로그 {len(fko)}키 (en {len(fen)})")
PY
}

# ---- 1단계: 골격 ----
git -C $W checkout -q -B i18n/1-skeleton origin/devel
git -C $W checkout -q tmp/full -- \
  rhwp-studio/src/i18n/README.md rhwp-studio/src/i18n/core.ts rhwp-studio/src/i18n/dom.ts \
  rhwp-studio/src/i18n/index.ts rhwp-studio/src/i18n/resolve.ts \
  rhwp-studio/public/locale-init.js rhwp-studio/src/main.ts \
  rhwp-studio/src/engine/header-footer-mode.ts rhwp-studio/src/view/canvas-view.ts rhwp-studio/src/view/page-indicator.ts \
  rhwp-chrome/build.mjs rhwp-firefox/build.mjs scripts/frontend-extension-dist.test.mjs \
  rhwp-studio/tests/i18n-core.test.ts rhwp-studio/tests/i18n-dom.test.ts \
  rhwp-studio/tests/i18n-locale-init.test.ts rhwp-studio/tests/i18n-resolve.test.ts \
  rhwp-studio/tests/i18n-preference.test.ts \
  rhwp-studio/tests/support/i18n-text.ts
LP_ROOT=$R python3 - <<'PY'
# index.html 은 원본 + locale-init 연결 두 줄만 (apply-extras 4번과 같은 삽입)
import pathlib
import os
p = pathlib.Path(os.environ['LP_ROOT'])/'work/rhwp/rhwp-studio/index.html'
s = p.read_text(encoding='utf-8')
anchor = '  <script src="/theme-init.js"></script>\n'
if '/locale-init.js' in s:
    raise SystemExit(0)   # 1단계가 상류에 머지돼 이미 있다
assert anchor in s
s = s.replace(anchor, anchor + '  <!-- 언어팩: 번들 전에 <html lang> 을 고른 로케일로 — 영어 사용자의 첫 페인트 깜빡임 방지 -->\n  <script src="/locale-init.js"></script>\n', 1)
p.write_text(s, encoding='utf-8')
PY
filter_locales 1
# 이미 상류에 머지된 단계는 바뀐 것이 없다 — 빈 커밋을 만들지 않고 넘어간다(1단계는 PR #7142 로 머지됨).
$G add -A
if git -C $W diff --cached --quiet; then echo "1단계: 변경 없음(이미 devel 에 반영)"; else $G commit -q -F $TMP/msg1.txt; fi
echo "1단계 커밋: $(git -C $W rev-parse --short HEAD)"

# ---- 2단계: 메뉴·툴바 ----
git -C $W checkout -q -B i18n/2-menus   # 앞 단계 커밋 위에 새 가지 — 빠뜨리면 네 커밋이 1단계 가지에 쌓인다
git -C $W checkout -q tmp/full -- rhwp-studio/index.html rhwp-studio/src/styles/style-bar.css rhwp-studio/e2e/responsive.test.mjs
# PR #7152 메인테이너 보정 e917cffb9 는 src/ui/style-toolbar-overflow.ts 도 고친다. 그 파일의 문자열 변환은 3단계라
# 2단계에는 보정만 얹는다(3단계가 tmp/full 의 src/ui 를 가져오면 보정+변환이 된다).
if ! git -C $W merge-base --is-ancestor e917cffb9 origin/devel 2>/dev/null \
   && ! git -C $W apply --reverse --check $R/overlay/patches/pr7152-e917cffb9-pre.patch 2>/dev/null; then
  git -C $W apply --include='rhwp-studio/src/ui/*' $R/overlay/patches/pr7152-e917cffb9-pre.patch
fi
filter_locales 2
sh $R/scripts/stage-tests.sh 2 $TMP/stage-cat/ko.json | tail -1
# 이미 상류에 머지된 단계는 바뀐 것이 없다 — 빈 커밋을 만들지 않고 넘어간다(1단계는 PR #7142 로 머지됨).
$G add -A
if git -C $W diff --cached --quiet; then echo "2단계: 변경 없음(이미 devel 에 반영)"; else $G commit -q -F $TMP/msg2.txt; fi
echo "2단계 커밋: $(git -C $W rev-parse --short HEAD)"

# ---- 3단계: 대화상자 ----
git -C $W checkout -q -B i18n/3-dialogs   # 앞 단계 커밋 위에 새 가지 — 빠뜨리면 네 커밋이 1단계 가지에 쌓인다
git -C $W checkout -q tmp/full -- rhwp-studio/src/ui
filter_locales 3
sh $R/scripts/stage-tests.sh 3 $TMP/stage-cat/ko.json | tail -1
# 이미 상류에 머지된 단계는 바뀐 것이 없다 — 빈 커밋을 만들지 않고 넘어간다(1단계는 PR #7142 로 머지됨).
$G add -A
if git -C $W diff --cached --quiet; then echo "3단계: 변경 없음(이미 devel 에 반영)"; else $G commit -q -F $TMP/msg3.txt; fi
echo "3단계 커밋: $(git -C $W rev-parse --short HEAD)"

# ---- 4단계: 명령 레지스트리 ----
git -C $W checkout -q -B i18n/4-commands   # 앞 단계 커밋 위에 새 가지 — 빠뜨리면 네 커밋이 1단계 가지에 쌓인다
git -C $W checkout -q tmp/full -- rhwp-studio/src/command/commands
python3 $R/scripts/write-catalog-ts.py $CAT/ko.json $ST/src/i18n/locales/ko.ts ko >/dev/null
python3 $R/scripts/write-catalog-ts.py $CAT/en.json $ST/src/i18n/locales/en.ts en >/dev/null
sh $R/scripts/stage-tests.sh 4 $CAT/ko.json | tail -1
# 이미 상류에 머지된 단계는 바뀐 것이 없다 — 빈 커밋을 만들지 않고 넘어간다(1단계는 PR #7142 로 머지됨).
$G add -A
if git -C $W diff --cached --quiet; then echo "4단계: 변경 없음(이미 devel 에 반영)"; else $G commit -q -F $TMP/msg4.txt; fi
echo "4단계 커밋: $(git -C $W rev-parse --short HEAD)"

# ---- 검증: 4단계 트리 == 전체 스냅샷 ----
if [ -n "$(git -C $W diff $FULL i18n/4-commands --stat)" ]; then
  echo "★4단계 트리가 전체 상태와 다르다:"; git -C $W diff $FULL i18n/4-commands --stat | tail -20; exit 1
fi
echo "불변식: 4단계 트리 == regenerate 전체 상태 (바이트 동일)"
