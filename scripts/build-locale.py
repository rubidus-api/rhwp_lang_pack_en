#!/usr/bin/env python3
"""
번역 메모리(값 → 값)로 대상 로케일 파일을 만든다.

정본은 `translations/ko-en.json` 의 **값 대응**이다. 키가 바뀌어도 번역은 살아남는다.

같은 원문이라도 자리에 따라 달라야 하는 것이 있다 — 「글자 모양」 대화상자의 미리보기
글자 `가` 는 영어 화면에서도 `가` 여야 하고, 툴바의 굵게 단추 위 `가` 는 `A` 여야 한다.
그런 것은 `translations/ko-en-overrides.json` 에 키로 적고, 값 대응 위에 덮는다.
"""
import json
import os
import sys

ko_path, memory_path, out_path = sys.argv[1:4]
overrides_path = sys.argv[4] if len(sys.argv) > 4 else None
ko = json.load(open(ko_path, encoding='utf-8'))
memory = json.load(open(memory_path, encoding='utf-8'))
overrides = {}
if overrides_path:
    import pathlib
    if pathlib.Path(overrides_path).exists():
        overrides = json.load(open(overrides_path, encoding='utf-8'))

out = {}
missing = []
for key, value in ko.items():
    if key in overrides:
        out[key] = overrides[key]
    elif value in memory:
        out[key] = memory[value]
    else:
        missing.append((key, value))

with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2, sort_keys=True)
    f.write('\n')

coverage = 100 * len(out) / len(ko) if ko else 100
print(f'{out_path}: {len(out)}/{len(ko)}개 ({coverage:.1f}%)'
      + (f', 키 단위 예외 {len(overrides)}개' if overrides else ''))
if missing:
    # 번역이 없는 키는 아예 넣지 않는다. 런타임이 원문(ko)으로 물러나므로
    # 화면은 한국어로 멀쩡히 나온다 — 진행 중 상태이지 결함이 아니다.
    values = sorted({value for _, value in missing})
    print(f'아직 번역하지 않은 값 {len(values)}개 (키 {len(missing)}개)')
    todo_path = out_path.replace('.json', '.todo.json')
    with open(todo_path, 'w', encoding='utf-8') as f:
        json.dump({v: '' for v in values}, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write('\n')
    print(f'  할 일 목록: {todo_path}')
else:
    # 다 채워졌으면 지난 실행의 할 일 목록을 지운다 — 남겨 두면 regenerate 가
    # 잔재 파일만 보고 '미번역이 있다' 며 영원히 멈춘다(2026-08-27 실제로 그랬다).
    todo_path = out_path.replace('.json', '.todo.json')
    if os.path.exists(todo_path):
        os.remove(todo_path)
