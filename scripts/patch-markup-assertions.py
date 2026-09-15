#!/usr/bin/env python3
"""
마크업을 원문 그대로 단정하던 테스트가 속성 추가를 견디게 한다.

`<h1 class="visually-hidden">…` 처럼 태그를 통째로 적어 둔 단정은 우리가 data-i18n 을
붙이는 순간 깨진다. 단정의 뜻은 '이 구조가 있다' 이지 '속성이 하나도 없다' 가 아니므로,
닫는 꺾쇠 앞에 `[^>]*` 를 넣어 속성이 더 붙어도 통과하게 한다.
"""
import pathlib
import re
import sys

CLASSES = ('md-label|tb-label|sb-ribbon-label|sb-field-label|menu-title|visually-hidden'
           '|stb-item|tb-split-item|sb-dropdown-item')
PATTERNS = [
    re.compile(rf'(class="(?:{CLASSES})"(?:[^>\n]*?)?)(>)'),
    # id 와 aria-label 을 함께 적어 둔 단정(nav·main·div 등 태그를 가리지 않는다)
    re.compile(r'(<\w+ id="[\w-]+"[^>\n]*aria-label="[^"]+"[^>\n]*?)(>)'),
    re.compile(r'(<option value="[^"]*")(>)'),
]


def main():
    tests_dir = pathlib.Path(sys.argv[1])
    write = '--write' in sys.argv
    changed = 0
    for path in sorted(tests_dir.glob('*.test.ts')):
        src = path.read_text(encoding='utf-8')
        out = src
        for pattern in PATTERNS:
            def sub(match):
                head = match.group(1)
                # 이미 고친 단정(상류에 병합된 뒤): 게으른 매치가 `[^>]*>` 안의 `>` 에서 멈춰 head 가 `[^` 로 끝난다.
                # 또 넣으면 `[^[^>]*>]*>` 가 된다(2026-09-16 d5fbe8b5d 재생성에서 잡힘).
                if head.endswith('[^>]*') or head.endswith('[^'):
                    return match.group(0)
                return head + '[^>]*>'
            out = pattern.sub(sub, out)
        if out != src:
            changed += 1
            if write:
                path.write_text(out, encoding='utf-8')
    print(f'속성 허용으로 고친 테스트 파일 {changed}개')


if __name__ == '__main__':
    main()
