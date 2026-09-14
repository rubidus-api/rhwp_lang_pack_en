#!/usr/bin/env python3
"""
번역이 비교를 깨뜨리는지 본다.

옮겨도 안전한 자리만 골랐다고 끝이 아니다. 어떤 코드가 화면 문자열을 만들고
다른 코드가 그 문자열과 **비교**하면, 앞을 영어로 옮기는 순간 뒤가 조용히 거짓이 된다.
테스트는 한국어로 돌기 때문에 이 결함은 초록 화면 뒤에 숨는다.

그래서 비교에 쓰인 한글 리터럴을 모으고, 같은 글자를 카탈로그가 옮기고 있으면
같은 파일 안에서 실제로 이어지는지 사람이 볼 수 있게 보고한다.
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from tsscan import korean_literals  # noqa: E402

COMPARE = [
    ('equality', re.compile(r'(===|!==|==|!=)\s*$')),
    ('case', re.compile(r'\bcase\s+$')),
    ('substring', re.compile(r'\.(includes|startsWith|endsWith|indexOf)\(\s*$')),
    ('selector', re.compile(r'\b(querySelector|querySelectorAll|closest|matches)\(\s*$')),
]


def unquote(raw):
    return raw[1:-1]


def main():
    root = pathlib.Path(sys.argv[1])
    catalog = json.load(open(sys.argv[2], encoding='utf-8'))
    # 사람이 확인해 안전하다고 판정한 자리. 판정을 적어 둘 곳이 없는 검사기는
    # 곧 무시당한다 — 근거와 함께 남기고, 남긴 것은 조용히 넘어간다.
    allow = {}
    if len(sys.argv) > 3 and pathlib.Path(sys.argv[3]).exists():
        allow = json.load(open(sys.argv[3], encoding='utf-8'))
    by_value = {}
    for key, value in catalog.items():
        by_value.setdefault(value, []).append(key)

    findings = []
    for path in sorted(root.glob('*.ts')):
        src = path.read_text(encoding='utf-8')
        for lit in korean_literals(src):
            before = src[max(0, lit.start - 60): lit.start]
            kind = next((name for name, pattern in COMPARE if pattern.search(before)), None)
            if kind is None:
                continue
            text = unquote(lit.raw)
            line = src[:lit.start].count('\n') + 1
            exact = by_value.get(text, [])
            partial = [k for value, keys in by_value.items()
                       if text in value and value != text for k in keys]
            if not (exact or partial):
                continue
            if f'{path.name}:{text}' in allow:
                continue
            findings.append((path.name, line, text, kind, exact, partial))

    if not findings:
        checked = len([k for k in allow if not k.startswith('_')])
        print(f'비교와 겹치는 번역 없음: ok (확인 완료로 기록된 자리 {checked}곳)')
        return 0

    print(f'비교에 쓰인 글자를 카탈로그도 옮기고 있다 — {len(findings)}곳. 사람이 확인할 것.')
    for filename, line, text, kind, exact, partial in findings:
        print(f'  {filename}:{line} [{kind}] {text!r}')
        for key in exact[:3]:
            print(f'      정확히 같은 키: {key}')
        for key in partial[:3]:
            print(f'      부분 일치 키: {key}')
    return 1


if __name__ == '__main__':
    sys.exit(main())
