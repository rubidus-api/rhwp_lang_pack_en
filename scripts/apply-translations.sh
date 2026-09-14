#!/bin/sh
# 번역해 온 변경분 엑셀을 정본에 병합하고, 코드(카탈로그 .ts·변환 결과)까지 다시 만든다.
#
#   sh scripts/apply-translations.sh review/delta-….xlsx
#
# 1) import-delta-xlsx.py 로 먼저 검사만 한다 — 거부 행이 있으면 여기서 멈추고 아무것도 안 쓴다.
# 2) 통과하면 translations/ko-en.json·reviewed.json 에 병합한다(시트에 없는 번역은 그대로).
# 3) regenerate.sh 로 상류 원본에서 전체를 다시 만든다(부분 재생성은 금지 — LESSONS).
# 4) 남은 변경분 수를 알려 준다. 단계 브랜치까지 갱신하려면 이어서 build-stages.sh.
set -eu
root=$(cd "$(dirname "$0")/.." && pwd)
[ $# -ge 1 ] || { echo "사용법: sh scripts/apply-translations.sh <변경분.xlsx>" >&2; exit 1; }
book=$1
[ -f "$book" ] || { echo "apply-translations: 파일이 없다: $book" >&2; exit 1; }

echo "== 1. 검사"
python3 "$root/scripts/import-delta-xlsx.py" "$book"
echo "== 2. 병합"
python3 "$root/scripts/import-delta-xlsx.py" "$book" --write | tail -1
echo "== 3. 재생성"
status=0
sh "$root/scripts/regenerate.sh" || status=$?
echo "== 4. 남은 변경분"
python3 "$root/scripts/export-delta-xlsx.py" --check || true
if [ "$status" -ne 0 ] && [ "$status" -ne 2 ]; then
  echo "apply-translations: regenerate 실패 (종료코드 $status)" >&2
  exit "$status"
fi
echo "apply-translations: ok — 단계 브랜치 갱신은 sh scripts/build-stages.sh, 관문은 sh scripts/verify-gates.sh"
