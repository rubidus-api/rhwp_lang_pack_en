#!/usr/bin/env python3
"""
무회귀 증명 — 표시를 전부 떼어내면 원본과 바이트 단위로 같아야 한다.

두 가지를 본다.
  1. 변환된 마크업에서 data-i18n* 속성만 지우면 원본과 완전히 같은가.
  2. ko 카탈로그의 값이 원본이 실제로 갖고 있던 문자열인가.

하나라도 어긋나면 종료 코드 1.
"""
import json
import re
import sys

ATTR = re.compile(r' data-i18n(?:-[a-z-]+)?="[^"]*"')

# 표시(data-i18n*) 말고 index.html 에 의도적으로 넣은 줄. 이 줄들을 지운 뒤에도 원본과 같아야 한다.
# 여기 적힌 것 외의 변경은 전부 결함으로 본다 — 허용 목록이 곧 '마크업에 우리가 남기는 발자국' 이다.
INTENDED_LINES = (
    '  <!-- 언어팩: 번들 전에 <html lang> 을 고른 로케일로 — 영어 사용자의 첫 페인트 깜빡임 방지 -->\n',
    '  <script src="/locale-init.js"></script>\n',
)


def main():
    original_path, current_path, catalog_path = sys.argv[1:4]
    original = open(original_path, encoding='utf-8').read()
    current = open(current_path, encoding='utf-8').read()
    catalog = json.load(open(catalog_path, encoding='utf-8'))

    ok = True

    stripped = ATTR.sub('', current)
    for line in INTENDED_LINES:
        stripped = stripped.replace(line, '', 1)
        # 1단계가 상류에 머지된 뒤에는 원본에도 이 줄이 있다. 양쪽에서 똑같이 뺀다.
        original = original.replace(line, '', 1)
    if stripped == original:
        print(f'표시 제거 후 원본과 동일: ok (의도한 추가 줄 {len(INTENDED_LINES)}개 제외)')
    else:
        ok = False
        print('표시 제거 후 원본과 다르다', file=sys.stderr)
        a, b = original.splitlines(), stripped.splitlines()
        for i, (x, y) in enumerate(zip(a, b), 1):
            if x != y:
                print(f'  줄 {i}\n   원본: {x[:120]}\n   현재: {y[:120]}', file=sys.stderr)
                break
        if len(a) != len(b):
            print(f'  줄 수 {len(a)} vs {len(b)}', file=sys.stderr)

    # 값 비교는 <br> 과 줄바꿈을 지운 뒤에 한다. 여러 줄 라벨의 값은 원본에서 <br/> 로
    # 나뉘어 있으므로, 그대로 찾으면 실제로는 멀쩡한 값이 없다고 나온다.
    def flatten(text):
        return re.sub(r'<br\s*/?>', '', text).replace('\n', '')

    # 마크업이 실제로 가리키는 키만 본다. 카탈로그에는 대화상자 소스에서 온 키도
    # 함께 들어 있는데, 그것들은 index.html 에 있을 리 없다(check-noregress-ts 가 본다).
    referenced = set(re.findall(r'data-i18n(?:-[a-z-]+)?="([^"]+)"', current))
    flat_original = flatten(original)
    missing = [key for key in sorted(referenced)
               if key in catalog and flatten(catalog[key]) not in flat_original]
    if missing:
        ok = False
        print(f'원본에 없는 값을 담은 키 {len(missing)}개', file=sys.stderr)
        for key in missing[:10]:
            print(f'  {key}: {catalog[key]!r}', file=sys.stderr)
    else:
        print(f'마크업이 가리키는 키 {len(referenced)}개 값이 모두 원본에 있다: ok')

    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
