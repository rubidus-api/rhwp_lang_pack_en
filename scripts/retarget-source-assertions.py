#!/usr/bin/env python3
"""
소스에 한글 리터럴이 있는지 정규식으로 보던 단정을 카탈로그-인지 도우미로 바꾼다.

문자열이 언어팩으로 옮겨가면 그런 단정은 전부 깨진다. 단정을 지우는 것은 검사를
잃는 것이고, 키를 하드코딩하는 것은 다음 변경에 또 깨진다. 그래서 "이 화면이 이
문구를 낸다" 라는 원래 뜻을 그대로 표현하는 도우미로 옮긴다.

이미 카탈로그로 옮겨간 문구만 바꾼다 — 아직 소스에 남아 있는 문구는 건드릴 이유가 없다.
"""
import json
import pathlib
import re
import sys

KO = re.compile(r'[가-힣]')
META = re.compile(r'[\[\]()|*+?{}^$]')
# for (const L of ['가', '나', …]) { assert.ok(V.includes(L), 메시지); } — 배열이 문자열
# 리터럴뿐이고 몸이 그 한 단정뿐인 루프만 본다. 그 밖의 꼴은 사람이 볼 일이다.
LOOP_INCLUDES = re.compile(
    r'for\s*\(\s*const\s+(\w+)\s+of\s+\[([^\]]*)\]\s*\)\s*\{\s*'
    r"(?P<assert>assert\.ok\(\s*(\w+)\.includes\(\s*\1\s*\)\s*"
    r'(?:,\s*((?:[^;`]|`[^`]*`)*?))?\s*\);)\s*\}'
)

CALL = re.compile(
    # 대상은 식별자이거나 식별자 하나를 받는 호출(`codeOnly(source)` — 주석을 뺀 소스)이다.
    r'assert\.(match|doesNotMatch)\(\s*((?:[A-Za-z_$][\w$]*\(\s*)?[A-Za-z_$][\w$]*(?:\s*\))?)\s*,\s*/((?:[^/\\\n]|\\.)+)/\s*(?:,\s*((?:[^,()]|\([^()]*\))*?))?\s*,?\s*\);'
)


def source_var(target):
    # `codeOnly(saveAsDialogSource)` → `saveAsDialogSource`. 어느 파일을 읽었는지는 안쪽 변수로 찾는다.
    inner = re.search(r'\(\s*([A-Za-z_$][\w$]*)\s*\)', target)
    return inner.group(1) if inner else target


def still_passes(kind, pattern):
    """원래 단정(match/doesNotMatch)이 지금 소스에서도 통과하나 — JS 정규식을 파이썬으로 그대로 돌려 본다.
    못 옮기는 꼴이면 None('문구가 있나' 로 돌아간다)."""
    try:
        compiled = re.compile(pattern)
    except re.error:
        return None
    if kind == 'doesNotMatch':
        return lambda content: not compiled.search(content)
    return lambda content: bool(compiled.search(content))


def plain_text(pattern):
    r"""정규식이 사실상 리터럴이면 그 글자를 낸다. 아니면 None.

    템플릿 자리(`\$\{si \+ 1\}`)만 든 정규식도 리터럴로 본다 — 자리를 {pN} 으로
    바꾸면 변환기가 만든 카탈로그 값과 같은 꼴이 된다(chart-data 테스트가 실제 그랬다).
    """
    holes = []
    def hole(m):
        holes.append(m)
        return '\x01%d\x01' % len(holes)
    tpl = re.sub(r'\\\$\\\{.*?\\\}', hole, pattern)
    if META.search(tpl.replace('\\.', '').replace('\\/', '')):
        return None
    unescaped = re.sub(r'\\(.)', r'\1', tpl)
    return re.sub('\x01(\\d+)\x01', r'{p\1}', unescaped)


def source_has_text(test_path, target_var, text, found=None):
    """테스트가 읽어 <target_var> 에 담은 소스 파일에 그 문구가 아직 있나. 못 찾으면 '있다' (보수적).

    found 를 주면 '문구가 있나' 대신 그 판정(소스 → bool)으로 묻는다.
    """
    found = found or (lambda content: text in content)
    src = test_path.read_text(encoding='utf-8')
    m = re.search(re.escape(target_var) + r"""\s*=\s*(?:await\s+)?\w+\(\s*(?:new URL\(\s*|join\([^,]+,\s*)?['"]([^'"]+\.(?:ts|html|css))['"]""", src)
    if not m:
        # 조각 변수(`const locked = body.slice(...)`)는 파일로 못 잇는다. 그때는 테스트가
        # 읽는 **모든** 소스 파일을 본다 — 전부에서 사라진 문구면 옮겨간 것이 맞다.
        rels = re.findall(r"""(?:new URL\(\s*|join\([^,]+,\s*)['"]([^'"]+\.(?:ts|html|css))['"]""", src)
        contents = []
        for rel in rels:
            for base in (test_path.parent, test_path.parent.parent):
                candidate = (base / rel).resolve()
                if candidate.exists():
                    contents.append(candidate.read_text(encoding='utf-8'))
                    break
        if not contents:
            return True
        return any(found(content) for content in contents)
    rel = m.group(1)
    # `new URL('../src/x.ts', import.meta.url)` 는 테스트 파일 기준, `join(rootDir, 'src/x.ts')` 는
    # studio 기준이다. 둘 다 시도해 존재하는 쪽을 쓴다.
    for base in (test_path.parent, test_path.parent.parent):
        candidate = (base / rel).resolve()
        if candidate.exists():
            return found(candidate.read_text(encoding='utf-8'))
    return True


def main():
    tests_dir = pathlib.Path(sys.argv[1])
    catalog = json.load(open(sys.argv[2], encoding='utf-8'))
    write = '--write' in sys.argv
    values = list(catalog.values())
    changed_files = 0
    changed = 0

    for path in sorted(tests_dir.glob('*.test.ts')):
        src = path.read_text(encoding='utf-8')
        out = src
        hits = []
        for match in LOOP_INCLUDES.finditer(src):
            loop_var, array_body, target, msg = (
                match.group(1), match.group(2), match.group(4), match.group(5))
            literals = re.findall(r"'((?:[^'\\]|\\.)*)'", array_body)
            korean = [lit for lit in literals if KO.search(lit)]
            if not korean:
                continue
            moved = [lit for lit in korean
                     if not source_has_text(path, target, lit) and any(lit in v for v in values)]
            if not moved:
                continue     # 전부 아직 소스에 있다 — 건드릴 이유가 없다
            call = f'assertShowsText({target}, {loop_var}'
            call += f', {msg});' if msg else ');'
            inner_span = match.span('assert')
            hits.append((inner_span[0], inner_span[1], call))
        for match in CALL.finditer(src):
            kind, target, pattern, message = match.group(1), match.group(2), match.group(3), match.group(4)
            if not KO.search(pattern):
                continue
            text = plain_text(pattern)
            if text is None:
                # `label:\s*'모양 붙여넣기'` 처럼 \s* 만 든 정규식은 사실상 리터럴이다.
                # 따옴표 안 문구만 뽑아 본다 — 그 문구가 카탈로그로 갔으면 단정의 뜻은 그대로다.
                inner = re.findall(r"'((?:[^'\\]|\\.)*[가-힣](?:[^'\\]|\\.)*)'", pattern)
                inner = [re.sub(r'\\(.)', r'\1', piece) for piece in inner]
                text = next((piece for piece in inner if any(piece in value for value in values)), None)
                if text is None:
                    continue
                if source_has_text(path, source_var(target), text, found=still_passes(kind, pattern)):
                    # 이 경로도 같은 질문을 해야 한다. 빠져 있어서 3단계(명령 소스는 그대로)에서
                    # `id: '…'[\s\S]*?label: '…'` 단정이 쓸데없이 약한 꼴로 바뀌었다.
                    # 문구가 '어딘가 있나' 로는 부족하다(같은 문구가 다른 문자열 속에 남는다) —
                    # 원래 단정이 지금 소스에서도 통과하면 그대로 둔다.
                    continue
            elif source_has_text(path, source_var(target), text):
                continue     # 테스트가 읽는 소스에 아직 그 문구가 있다 — 건드릴 이유가 없다(B-3)
            elif not any(text in value for value in values):
                # 정규식이 문구뿐 아니라 주변 코드까지 담은 경우
                # (`passwordButton.textContent = '암호 설정...'`) 따옴표 안을 본다.
                inner = re.findall(r"'([^']*[가-힣][^']*)'", text)
                inner += re.findall(r'`([^`]*[가-힣][^`]*)`', text)
                text = next((piece for piece in inner
                             if any(piece in value for value in values)), None)
                if text is None:
                    continue     # 아직 옮기지 않은 문구 — 그대로 둔다
            literal = json.dumps(text, ensure_ascii=False).replace('"', "'")
            fn = 'assertDoesNotShowText' if kind == 'doesNotMatch' else 'assertShowsText'
            call = f'{fn}({target}, {literal}'
            call += f', {message});' if message else ');'
            hits.append((match.start(), match.end(), call))
        if not hits:
            continue
        for start, end, call in sorted(hits, reverse=True):
            out = out[:start] + call + out[end:]
        if 'support/i18n-text.ts' not in out:
            # 여러 줄 import 는 첫 줄만 'import' 로 시작한다. 줄 단위로 끼워 넣으면
            # 괄호 안에 들어가 파일이 깨진다 — 문장 끝을 찾아야 한다.
            last = None
            for match in re.finditer(r'^import\b[\s\S]*?;\s*$', out, re.M):
                last = match
            statement = "import { assertShowsText, assertDoesNotShowText } from './support/i18n-text.ts';"
            out = (out[:last.end()] + '\n' + statement + out[last.end():]) if last else statement + '\n' + out
        changed_files += 1
        changed += len(hits)
        if write:
            path.write_text(out, encoding='utf-8')

    print(f'파일 {changed_files}개, 단정 {changed}곳')


if __name__ == '__main__':
    main()
