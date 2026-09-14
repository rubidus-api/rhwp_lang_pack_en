#!/bin/sh
# 언어팩 산출물을 값 대응 표에서 다시 만든다.
#
# 정본은 이 저장소의 translations/ 다.
#   translations/ko-en.json           값 대응(번역 메모리) — 사람이 고치는 곳
#   translations/ko-en-overrides.json 자리마다 달라야 하는 것만 키로 적는다
#   translations/catalog/*.json  키→값 카탈로그 — 변환기가 쓰는 곳
# 상류 트리에는 코드가 읽는 .ts 만 올린다.
set -eu

root=$(cd "$(dirname "$0")/.." && pwd)
studio="$root/work/rhwp/rhwp-studio"
catalog="$root/translations/catalog"
locales="$studio/src/i18n/locales"

[ -d "$studio" ] || { echo "rebuild-langpack: 작업 사본이 없다"; exit 1; }
mkdir -p "$locales"

python3 "$root/scripts/build-locale.py" "$catalog/ko.json" "$root/translations/ko-en.json" \
  "$catalog/en.json" "$root/translations/ko-en-overrides.json"
python3 "$root/scripts/write-catalog-ts.py" "$catalog/ko.json" "$locales/ko.ts" ko
python3 "$root/scripts/write-catalog-ts.py" "$catalog/en.json" "$locales/en.ts" en
echo "rebuild-langpack: ok"
