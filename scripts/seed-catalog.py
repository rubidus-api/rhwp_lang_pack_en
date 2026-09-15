#!/usr/bin/env python3
"""상류에 이미 병합된 카탈로그 키를 ko.json 에 심는다.

변환기는 한글 리터럴을 보고 키를 만든다. 상류에 이미 t('…') 로 바뀐 자리는 한글이 없어
변환기가 키를 만들지 못하므로, 그대로 두면 카탈로그에서 병합된 키가 빠진다(LESSONS: 카탈로그 덮어쓰기).
상류(origin/devel)의 locales/ko.ts 가 정본이다. 없으면(언어팩 병합 전 커밋) 아무것도 하지 않는다.

  seed-catalog.py <work/rhwp> <ko.json> <seed 목록 출력.json>          # 심기
  seed-catalog.py --check <ko.json> <seed 목록.json>                   # 심은 키가 값까지 그대로인지
"""
import json
import re
import subprocess
import sys


def parse_catalog_ts(text):
    body = text[text.index('= {') + 2:text.index('\n} as const')]
    body = re.sub(r',\s*$', '', body.rstrip())
    return json.loads(body + '\n}')


def upstream_catalog(repo, locale):
    r = subprocess.run(['git', '-C', repo, 'show', f'origin/devel:rhwp-studio/src/i18n/locales/{locale}.ts'],
                       capture_output=True, text=True)
    return parse_catalog_ts(r.stdout) if r.returncode == 0 else {}


def main():
    if sys.argv[1] == '--check':
        ko = json.load(open(sys.argv[2], encoding='utf-8'))
        seed = json.load(open(sys.argv[3], encoding='utf-8'))
        lost = [k for k in seed if k not in ko]
        changed = [k for k in seed if k in ko and ko[k] != seed[k]]
        if lost or changed:
            for k in lost[:20]:
                print(f'  빠짐: {k}', file=sys.stderr)
            for k in changed[:20]:
                print(f'  값 바뀜: {k}: {seed[k]!r} → {ko[k]!r}', file=sys.stderr)
            raise SystemExit(f'seed-catalog: 상류 키 {len(lost)}개 빠짐, {len(changed)}개 값 바뀜')
        print(f'seed-catalog: 상류 키 {len(seed)}개 모두 그대로')
        return
    repo, ko_path, out = sys.argv[1:4]
    ko = json.load(open(ko_path, encoding='utf-8'))
    seed = upstream_catalog(repo, 'ko')
    clash = [k for k in seed if k in ko and ko[k] != seed[k]]
    if clash:
        for k in clash[:20]:
            print(f'  충돌: {k}: 상류 {seed[k]!r} / 변환 {ko[k]!r}', file=sys.stderr)
        raise SystemExit(f'seed-catalog: 마크업에서 뽑은 값과 상류 카탈로그가 {len(clash)}곳 다르다')
    ko.update(seed)
    json.dump(ko, open(ko_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2, sort_keys=True)
    open(ko_path, 'a').write('\n')
    json.dump(seed, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=2, sort_keys=True)
    print(f'seed-catalog: 상류 키 {len(seed)}개 심음 → 카탈로그 {len(ko)}')


if __name__ == '__main__':
    main()
