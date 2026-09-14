#!/bin/sh
# 언어팩 검사 묶음 — 작업 사본이 있을 때만 돈다.
#
#   1. 표시를 떼면 원본과 바이트 동일한가 (무회귀, R1)
#   2. ko/en 키 집합이 같고 미번역이 없는가 (R3 R4)
#   3. 마크업이 가리키는 키가 카탈로그에 다 있는가
#
# 작업 사본이 없으면 조용히 건너뛴다. 이 저장소만으로는 검사할 대상이 없다.
set -eu

root=$(cd "$(dirname "$0")/.." && pwd)
studio="$root/work/rhwp/rhwp-studio"
# 카탈로그 JSON 은 이 저장소가 갖는다. 상류 트리에는 코드가 읽는 .ts 만 올린다
# — 같은 데이터를 두 벌 올리면 어느 쪽이 정본인지 모호해진다.
locales="$root/translations/catalog"

if [ ! -d "$studio" ]; then
  echo "check-langpack: 작업 사본이 없다 — 건너뜀 (P0 참고)"
  exit 0
fi

baseline="$root/work/index.baseline.html"
if [ -f "$baseline" ]; then
  python3 "$root/scripts/check-noregress.py" "$baseline" "$studio/index.html" "$locales/ko.json"
else
  echo "check-langpack: 기준 원본이 없다 — 무회귀 검사 건너뜀 ($baseline)"
fi

if [ -d "$root/work/ui.baseline" ]; then
  python3 "$root/scripts/check-noregress-ts.py" "$root/work/ui.baseline" "$locales/ko.json"
else
  echo "check-langpack: 대화상자 기준 소스가 없다 — 건너뜀"
fi

# 같은 요소에 번역 쓰기와 한국어 쓰기가 섞인 곳 — 영어 화면에서 번역이 덮이거나 상태에 따라
# 한국어로 돌아간다. 타입 검사·단위 테스트는 한국어로 돌아 이것을 못 잡는다.
python3 "$root/scripts/check-mixed-writes.py" "$studio/src/ui"
python3 "$root/scripts/check-mixed-writes.py" "$studio/src/command/commands"

python3 "$root/scripts/check-comparisons.py" "$studio/src/ui" "$locales/ko.json" \
  "$root/translations/comparison-allow.json"
python3 "$root/scripts/check-comparisons.py" "$studio/src/command/commands" "$locales/ko.json" \
  "$root/translations/comparison-allow.json"

python3 "$root/scripts/check-parity.py" "$locales/ko.json" "$locales/en.json" \
  "$root/translations/keep-as-is.json"
python3 "$root/scripts/preview-locale.py" "$studio/index.html" "$locales/en.json" \
  "$root/build/index.en.html" >/dev/null
echo "check-langpack: ok"
