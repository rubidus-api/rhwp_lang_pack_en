#!/bin/sh
# 단계 브랜치마다 테스트 파일을 '맞는 상태' 로 만든다.
#
# 테스트는 세 겹으로 달라진다: ① 마크업 구조 단정은 속성 추가를 허용해야 하고(2단계부터),
# ② 대화상자 소스를 정규식으로 읽던 단정은 카탈로그-인지로 바꿔야 하며(3단계부터),
# ③ command 소스를 읽던 단정도 같다(4단계부터). 손으로 맞추면 단계마다 어긋난다.
#
#   sh scripts/stage-tests.sh <2|3|4> <카탈로그 ko.json>
set -eu
root=$(cd "$(dirname "$0")/.." && pwd)
repo="$root/work/rhwp"
tests="$repo/rhwp-studio/tests"
stage=$1
catalog=$2

# 언제나 상류 원본에서 시작한다. 단, 우리가 추가한 파일은 건드리지 않는다.
git -C "$repo" checkout origin/devel -- rhwp-studio/tests 2>/dev/null || true
# 상류에 없던 우리 테스트·도우미는 checkout 이 지우지 않으므로 그대로 남는다.

if [ "$stage" -ge 2 ]; then
  python3 "$root/scripts/patch-markup-assertions.py" "$tests" --write
fi
if [ "$stage" -ge 3 ]; then
  # 3단계 카탈로그에는 command 키가 없으므로 command 소스 단정은 자연히 그대로 남는다.
  python3 "$root/scripts/retarget-source-assertions.py" "$tests" "$catalog" --write
fi
if [ "$stage" -ge 6 ]; then
  # ID 를 먼저 분리한 함수(zoomPercentShortcutTitle)의 인자를 쓰는 단정 — 도구가 다루지 못해 손으로 적는다.
  python3 "$root/scripts/retarget-hand-tests.py" "$tests" > /dev/null
fi
echo "stage-tests: 단계 $stage 상태"
