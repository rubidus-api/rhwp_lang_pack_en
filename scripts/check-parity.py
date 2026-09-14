#!/usr/bin/env python3
"""
로케일 짝 검사 — 키가 어긋나거나 번역이 빠진 곳을 찾는다.

  1. ko 와 en 의 키 집합이 같은가.
  2. en 값에 한글이 남아 있지 않은가(글꼴 이름 등 옮기지 않기로 한 것은 예외).
  3. 빈 값이 있는가.
"""
import json
import pathlib
import re
import sys

KO = re.compile(r'[가-힣]')

def load_keep(path):
    """옮기지 않기로 한 것과 그 이유. 이유가 없는 예외는 곧 잊히고 다시 논쟁된다."""
    if not path or not pathlib.Path(path).exists():
        return set(), set()
    data = json.load(open(path, encoding='utf-8'))
    return set(data.get('values', {})), set(data.get('keys', {}))


def main():
    ko = json.load(open(sys.argv[1], encoding='utf-8'))
    en = json.load(open(sys.argv[2], encoding='utf-8'))
    keep_values, keep_keys = load_keep(sys.argv[3] if len(sys.argv) > 3 else None)
    ok = True

    # en 은 ko 의 부분집합이어야 한다. 없는 키는 원문으로 물러나므로 정상이고,
    # ko 에 없는 en 키는 갈 곳 없는 번역이라 결함이다.
    orphans = sorted(set(en) - set(ko))
    if orphans:
        ok = False
        print(f'ko 에 없는 en 키 {len(orphans)}개', file=sys.stderr)
        for key in orphans[:10]:
            print(f'  {key}', file=sys.stderr)
    else:
        coverage = 100 * len(en) / len(ko) if ko else 100
        print(f'키 {len(en)}/{len(ko)}개 번역 ({coverage:.1f}%), 갈 곳 없는 키 0개')

    untranslated = [k for k, v in en.items()
                    if KO.search(v) and v not in keep_values and k not in keep_keys]
    if untranslated:
        ok = False
        print(f'번역되지 않은 값 {len(untranslated)}개', file=sys.stderr)
        for key in untranslated[:10]:
            print(f'  {key}: {en[key]!r}', file=sys.stderr)
    else:
        print(f'미번역 0개 (한국어로 두기로 한 것 {len(keep_keys)}개 키·{len(keep_values)}개 값)')

    empty = [k for k, v in en.items() if not v.strip()]
    if empty:
        ok = False
        print(f'빈 값 {len(empty)}개: {empty[:5]}', file=sys.stderr)

    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
