#!/usr/bin/env python3
"""
표시된 마크업을 로케일로 치환해 미리보기를 만든다.

브라우저 없이도 '영어 화면이 실제로 무엇이 되는지'를 눈으로 볼 수 있고,
마크업이 가리키는 키가 카탈로그에 다 있는지도 함께 검사한다.

한계: 치환이 정규식 근사라, 자식 요소 뒤에 텍스트가 오는 모양
(`<span>가</span>양각`)은 미리보기에서 한글이 남는다. 실제 런타임은 직계 텍스트
노드만 바꾸므로 올바르게 동작하며, 그 동작은 tests/i18n-dom.test.ts 가 고정한다.
미리보기에 남은 한글을 곧바로 결함으로 읽지 말 것 — 판정은 check-parity 가 한다.
"""
import json
import re
import sys

html_path, locale_path, out_path = sys.argv[1:4]
src = open(html_path, encoding='utf-8').read()
catalog = json.load(open(locale_path, encoding='utf-8'))

missing = []


def value_of(key):
    if key in catalog:
        return catalog[key]
    missing.append(key)
    return None


# data-i18n="K" 가 붙은 요소의 직계 텍스트를 바꾼다(미리보기이므로 근사).
def replace_text(match):
    head, attrs, inner, tail = match.groups()
    key = re.search(r'data-i18n="([^"]+)"', attrs)
    if not key:
        return match.group(0)
    value = value_of(key.group(1))
    if value is None:
        return match.group(0)
    replaced = re.sub(r'(^|>)([^<>]*[^\s<>][^<>]*)', lambda m: m.group(1) + value, inner, count=1)
    return f'{head}{attrs}>{replaced}{tail}'


out = re.sub(r'(<(\w+)\s)([^<>]*data-i18n="[^"]+"[^<>]*)>(.*?)(</\2>)',
             lambda m: f'{m.group(1)}{m.group(3)}>' +
                       (lambda v: m.group(4) if v is None else re.sub(
                           r'([^<>]*[^\s<>][^<>]*)', v.replace('\\', '\\\\'), m.group(4), count=1))(
                           value_of(re.search(r'data-i18n="([^"]+)"', m.group(3)).group(1))) +
                       m.group(5),
             src, flags=re.S)

for attr in ('title', 'aria-label', 'placeholder', 'value'):
    def sub_attr(match, attr=attr):
        whole = match.group(0)
        key = match.group(1)
        value = value_of(key)
        if value is None:
            return whole
        return re.sub(rf'{attr}="[^"]*"', f'{attr}="{value}"', whole, count=1)

    out = re.sub(rf'<[^<>]*data-i18n-{attr}="([^"]+)"[^<>]*>', sub_attr, out)

# data-i18n-lines 는 줄바꿈을 <br> 로.
def sub_lines(match):
    head, attrs, inner, tail = match.group(1), match.group(3), match.group(4), match.group(5)
    key = re.search(r'data-i18n-lines="([^"]+)"', attrs).group(1)
    value = value_of(key)
    if value is None:
        return match.group(0)
    return f'{head}{attrs}>' + '<br/>'.join(value.split('\n')) + tail


out = re.sub(r'(<(\w+)\s)([^<>]*data-i18n-lines="[^"]+"[^<>]*)>(.*?)(</\2>)', sub_lines, out, flags=re.S)

open(out_path, 'w', encoding='utf-8').write(out)
print(f'{out_path} 생성')
if missing:
    print(f'카탈로그에 없는 키 {len(sorted(set(missing)))}개', file=sys.stderr)
    for key in sorted(set(missing))[:10]:
        print(f'  {key}', file=sys.stderr)
    sys.exit(1)
print('마크업이 가리키는 키가 모두 카탈로그에 있다: ok')
