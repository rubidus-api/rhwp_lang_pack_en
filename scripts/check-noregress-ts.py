#!/usr/bin/env python3
"""
대화상자 무회귀 — 카탈로그 값이 원래 소스에 실제로 있던 글자인가.

옮기는 과정에서 글자가 조금이라도 달라지면(따옴표 해제 실수, 줄바꿈 처리, 공백)
한국어 화면이 미묘하게 바뀐다. 그것도 회귀다. 그래서 기준 소스에 대고 확인한다.

기준 소스는 git 이 아니라 파일로 받는다 — 도구가 저장소 상태에 기대지 않게.
"""
import json
import pathlib
import re
import sys

KO = re.compile(r'[가-힣]')


def flatten(text):
    """비교용 정규화 — 이스케이프와 자리표시자 차이를 지운다."""
    text = re.sub(r'\{p\d+\}', '\x00', text)      # 자리표시자는 원본에서 ${...} 였다
    text = text.replace('\\n', '\n').replace('\\t', '\t')
    return re.sub(r'\s+', '', text)


def main():
    baseline_dir = pathlib.Path(sys.argv[1])
    catalog = json.load(open(sys.argv[2], encoding='utf-8'))
    prefix = sys.argv[3] if len(sys.argv) > 3 else 'dialog.'

    haystack = []
    for path in sorted(baseline_dir.glob('*.ts')):
        haystack.append(flatten(path.read_text(encoding='utf-8')))
    joined = '\x01'.join(haystack)

    checked = [key for key in catalog if key.startswith(prefix)]
    missing = []

    # 앞뒤 줄바꿈은 white-space: pre-line 에서 배치의 일부다. flatten() 이 공백을 전부 지우므로
    # 그것만으로는 "\n\n 이 사라졌다" 를 못 본다(drop-confirm 이 그랬다). 값이 줄바꿈으로 시작하거나
    # 끝나야 하는데 카탈로그 값이 그렇지 않으면 잡는다: 원본 템플릿 중 같은 본문을 가진 것이
    # 앞뒤 \n 을 갖고 있는지 본다.
    raw_templates = []
    for path in sorted(baseline_dir.glob('*.ts')):
        src = path.read_text(encoding='utf-8')
        raw_templates += [m.group(1) for m in re.finditer(r'`((?:[^`\\]|\\.)*)`', src)]
    def edge_newlines(value):
        return (value.startswith('\n'), value.endswith('\n'))
    edge_missing = []
    for key in checked:
        value = catalog[key]
        core = flatten(value)
        if not core:
            continue
        for tpl in raw_templates:
            tpl_text = tpl.replace('\\n', '\n')
            if flatten(re.sub(r'\$\{[^}]*\}', '\x00', tpl_text)) == core:
                if edge_newlines(tpl_text) != edge_newlines(value):
                    edge_missing.append((key, value, tpl_text))
                break
    if edge_missing:
        print(f'앞뒤 줄바꿈이 원본과 다른 값 {len(edge_missing)}개', file=sys.stderr)
        for key, value, tpl in edge_missing[:10]:
            print(f'  {key}: 카탈로그 {value!r} / 원본 {tpl!r}', file=sys.stderr)
        return 1
    for key in checked:
        needle = flatten(catalog[key])
        if not needle:
            continue
        parts = [piece for piece in needle.split('\x00') if piece]
        if not all(piece in joined for piece in parts):
            missing.append(key)

    if missing:
        print(f'기준 소스에 없는 값 {len(missing)}개 / 검사 {len(checked)}개', file=sys.stderr)
        for key in missing[:10]:
            print(f'  {key}: {catalog[key]!r}', file=sys.stderr)
        return 1
    print(f'대화상자 키 {len(checked)}개 값이 모두 기준 소스에 있다: ok')
    return 0


if __name__ == '__main__':
    sys.exit(main())
