#!/usr/bin/env python3
"""카탈로그 JSON 을 TypeScript 모듈로 내보낸다.

JSON 을 그대로 import 하면 저장소의 테스트 러너가 `./x.json` 을 `x.json.ts` 로
해석해 실패한다. 남의 테스트 지원 파일을 고치는 대신 우리 쪽 산출물 형식을 맞춘다.
"""
import json
import sys

src, out, locale = sys.argv[1], sys.argv[2], sys.argv[3]
catalog = json.load(open(src, encoding='utf-8'))
lines = [
    '/**',
    f' * {locale} 카탈로그.',
    ' *',
    ' * 값 대응 표에서 만들어진 파일이지만, 여기서 값을 고쳐도 된다 — 키는 그대로 두고',
    ' * 값만 바꾸면 화면에 그대로 반영된다. 키를 더하거나 지우는 일은 마크업의',
    ' * data-i18n 표시·소스의 t() 호출과 함께 바꿔야 한다. 자세한 규칙은 ../README.md.',
    ' */',
    '',
    'const catalog = {',
]
for key in sorted(catalog):
    value = json.dumps(catalog[key], ensure_ascii=False)
    lines.append(f'  {json.dumps(key)}: {value},')
lines += ['} as const;', '', 'export default catalog;', '']
open(out, 'w', encoding='utf-8').write('\n'.join(lines))
print(f'{out}: {len(catalog)}개')
