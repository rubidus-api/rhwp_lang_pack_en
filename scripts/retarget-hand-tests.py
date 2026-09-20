#!/usr/bin/env python3
"""손으로 재조준하는 테스트 — stage-tests.sh 가 테스트를 상류 원본으로 되돌린 **뒤에** 적용한다.

변환기·재조준 도구가 다루지 못하는 형태만 여기 둔다. 지금은 ID 를 먼저 분리한 함수
(`zoomPercentShortcutTitle(action: 'zoomIn' | 'zoomOut')`)의 인자를 쓰는 단정뿐이다.
표시 글자('확대'·'축소')는 카탈로그가 가지므로 단정은 ID 를 본다(#7167 과 같은 방식).

  retarget-hand-tests.py <tests 디렉터리>
"""
import pathlib
import sys

PAIRS = {
    'zoom-status-controls.test.ts': (
        ("zoomPercentShortcutTitle('확대', 'Ctrl++', 'mac')", "zoomPercentShortcutTitle('zoomIn', 'Ctrl++', 'mac')"),
        ("zoomPercentShortcutTitle('축소', 'Ctrl+-', 'mac')", "zoomPercentShortcutTitle('zoomOut', 'Ctrl+-', 'mac')"),
        ("zoomPercentShortcutTitle('확대', 'Ctrl++', 'other')", "zoomPercentShortcutTitle('zoomIn', 'Ctrl++', 'other')"),
        ("zoomPercentShortcutTitle('축소', 'Ctrl+-', 'other')", "zoomPercentShortcutTitle('zoomOut', 'Ctrl+-', 'other')"),
        # 기대값도 카탈로그의 ko 값이라 그대로 둔다 — 인자만 ID 로 바꾼다.
    ),
    # 재조준 도구가 먼저 assertShowsText 로 바꾼 뒤라, 그 형태에서 ID 단정으로 옮긴다.
    # main.ts 는 이제 표시 글자 대신 ID 를 넘기므로 '확대' 라는 글자가 없다.
    'zoom-dialog-integration.test.ts': (
        ("  assertShowsText(main, '확대');\n  assertShowsText(main, '축소');",
         "  assert.match(main, /zoomPercentShortcutTitle\\('zoomIn'/);\n"
         "  assert.match(main, /zoomPercentShortcutTitle\\('zoomOut'/);"),
    ),
}


def main():
    tests = pathlib.Path(sys.argv[1])
    changed = 0
    for name, pairs in PAIRS.items():
        path = tests / name
        if not path.exists():
            continue
        text = path.read_text(encoding='utf-8')
        for old, new in pairs:
            if new in text:
                continue        # 이미 반영됨(상류가 받아들인 뒤)
            if text.count(old) != 1:
                raise SystemExit(f'retarget-hand-tests: {name} 에서 기대한 코드가 {text.count(old)}번 나온다: {old[:60]}')
            text = text.replace(old, new)
            changed += 1
        path.write_text(text, encoding='utf-8')
    print(f'retarget-hand-tests: {changed}곳')


if __name__ == '__main__':
    main()
