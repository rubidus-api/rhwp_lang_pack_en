#!/bin/sh
# 상류 CI 가 도는 검사를 그대로 돌린다 — 단계 브랜치마다.
#
# CI 의 프론트 관문(.github/workflows/ci.yml):
#   npm ci → npx tsc --project tsconfig.ci-unit.json --noEmit → npm run test → npm run build
# Rust 관문은 우리가 Rust 파일을 건드리지 않으므로 대상이 아니지만,
# 정말 안 건드렸는지는 이 스크립트가 확인한다(주장 대신 측정).
set -eu

root=$(cd "$(dirname "$0")/.." && pwd)
repo="$root/work/rhwp"
studio="$repo/rhwp-studio"
base=${BASE_REF:-devel}
branches=${*:-"i18n/1-skeleton i18n/2-menus i18n/3-dialogs i18n/4-commands i18n/5-dialog-rest i18n/6-rest"}

[ -d "$studio" ] || { echo "verify-gates: 작업 사본이 없다"; exit 1; }
mkdir -p "$root/build"

touched=$(git -C "$repo" diff --name-only "$base" i18n/6-rest | grep -cE '\.rs$|Cargo\.(toml|lock)$|tsconfig|vite\.config|package(-lock)?\.json|\.github/' || true)
if [ "$touched" -ne 0 ]; then
  echo "verify-gates: Rust·빌드설정·CI 파일을 건드렸다 ($touched 개). 발자국 주장이 틀렸다." >&2
  exit 1
fi
echo "발자국: Rust·빌드설정·CI 무접촉 ok"

for branch in $branches; do
  echo "== $branch"
  git -C "$repo" checkout -q "$branch"
  log=$(echo "$branch" | tr / -)
  # `명령 && echo ok` 는 set -e 로 멈추지 않는다 — 실패를 출력만 하고 초록으로 끝난 적이 있다.
  (cd "$studio" && npx tsc --project tsconfig.ci-unit.json --noEmit) > "$root/build/tsc-$log.log" 2>&1 \
    || { cat "$root/build/tsc-$log.log" >&2; echo "verify-gates: $branch 타입검사 실패" >&2; exit 1; }
  echo "   ci-unit typecheck ok"
  status=0
  npm --prefix "$studio" run test > "$root/build/test-$log.log" 2>&1 || status=$?
  sed 's/\x1b\[[0-9;]*m//g' "$root/build/test-$log.log" | grep -E '^ℹ (pass|fail)' | tr '\n' ' ' | sed 's/^/   test: /'
  echo
  if [ "$status" -ne 0 ]; then
    sed 's/\x1b\[[0-9;]*m//g' "$root/build/test-$log.log" | grep -E '^not ok|✖' | head -10 >&2
    echo "verify-gates: $branch 테스트 실패" >&2
    exit 1
  fi
  npm --prefix "$studio" run build > "$root/build/build-$log.log" 2>&1 \
    || { tail -20 "$root/build/build-$log.log" >&2; echo "verify-gates: $branch 빌드 실패" >&2; exit 1; }
  echo "   build(tsc+vite) ok"
done

echo
echo "== 빌드 경고 대조 (기준선과 같아야 한다)"
git -C "$repo" checkout -q "$base"
npm --prefix "$studio" run build > "$root/build/build-base.log" 2>&1 || true
git -C "$repo" checkout -q i18n/6-rest
# 프로세스 치환(<(...))은 POSIX sh 에 없다. 임시 파일로 간다.
strip_warnings() {
  sed 's/\x1b\[[0-9;]*m//g' "$1" | grep -E '\(!\)|warn|deprecat' | sort -u > "$2" || true
}
strip_warnings "$root/build/build-base.log" "$root/build/warn-base.txt"
strip_warnings "$root/build/build-i18n-4-commands.log" "$root/build/warn-ours.txt"
if diff -q "$root/build/warn-base.txt" "$root/build/warn-ours.txt" >/dev/null; then
  echo "   경고 동일: 새로 생긴 경고 없음"
else
  echo "   ★경고가 달라졌다:" >&2
  diff "$root/build/warn-base.txt" "$root/build/warn-ours.txt" >&2 || true
  exit 1
fi
