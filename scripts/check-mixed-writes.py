#!/usr/bin/env python3
"""
같은 요소에 번역 쓰기와 한국어 쓰기가 섞인 곳을 찾는다.

변환기는 `el.textContent = '...'` 처럼 문자열이 대입 바로 뒤에 오는 자리만 옮긴다.
그러면 같은 요소를 다른 줄에서 `cond ? '한국어' : '한국어'` 로 다시 쓰는 코드가 남고,
영어 화면에서 번역이 덮이거나(쓰기 순서가 뒤면) 상태에 따라 한국어로 돌아간다.
타입 검사도 단위 테스트도 이것을 못 잡는다 — 둘 다 한국어로 돌기 때문이다.

찾는 것:
  (ident, prop) 묶음 안에 t()/별칭 호출 쓰기와 한글 리터럴 쓰기가 함께 있는 경우,
  또는 한 대입의 우변에 t() 와 한글 리터럴이 함께 있는 경우.
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from tsscan import literals  # noqa: E402

KO = re.compile(r'[가-힣]')
PROPS = r'(?:textContent|innerText|title|placeholder|value|label|alt|innerHTML)'
WRITE = re.compile(r'\b([A-Za-z_$][\w$.]*?)\.(' + PROPS + r')\s*=(?!=)')
CALL = re.compile(r'\b(?:t|i18nText|i18nMessage|localizedText)\(')


def statement_end(src, start):
    """대입이 시작된 자리에서 문장 끝(세미콜론)까지 — 괄호·문자열 안의 ; 는 건너뛴다."""
    depth = 0
    i = start
    in_str = None
    while i < len(src):
        ch = src[i]
        if in_str:
            if ch == '\\':
                i += 2
                continue
            if ch == in_str:
                in_str = None
        elif ch in '\'"`':
            in_str = ch
        elif ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth -= 1
        elif ch == ';' and depth <= 0:
            return i
        i += 1
    return len(src)


MARKUP_ID = re.compile(r'id="([\w-]+)"[^>]*data-i18n')
GET_BY_ID = re.compile(r"getElementById\('([\w-]+)'\)")


def markup_rewrites(studio):
    """index.html 이 data-i18n 으로 표시한 요소를, 코드가 한글 리터럴로 다시 쓰는 곳.

    마크업 번역은 부팅 때 한 번 적용된다. 그 뒤 main.ts 가 `sb-mode` 를 '삽입' 으로 다시 쓰면
    영어 화면이 첫 문서 로드 순간 한국어로 돌아간다. 카탈로그 키는 살아 있지만 아무 일도 안 한다.
    """
    html = (studio / 'index.html').read_text(encoding='utf-8')
    tagged = set(MARKUP_ID.findall(html))
    out = []
    for path in sorted((studio / 'src').rglob('*.ts')):
        if '/i18n/' in str(path):
            continue
        src = path.read_text(encoding='utf-8')
        ko_starts = [l.start for l in literals(src) if KO.search(l.raw)]
        for m in GET_BY_ID.finditer(src):
            ident = m.group(1)
            if ident not in tagged:
                continue
            end = statement_end(src, m.end())
            if any(m.end() <= s < end for s in ko_starts):
                line = src[:m.start()].count('\n') + 1
                out.append((path.relative_to(studio).as_posix(), line, f'#{ident}', '마크업 번역을 한글로 다시 씀'))
    return out


def main():
    root = pathlib.Path(sys.argv[1])
    findings = []
    studio = root.parent.parent if root.name == 'ui' else None
    if studio and (studio / 'index.html').exists():
        findings.extend(markup_rewrites(studio))
    for path in sorted(root.glob('*.ts')):
        src = path.read_text(encoding='utf-8')
        ko_spans = [(l.start, l.end) for l in literals(src) if KO.search(l.raw)]
        groups = {}
        for m in WRITE.finditer(src):
            ident, prop = m.group(1), m.group(2)
            end = statement_end(src, m.end())
            rhs = src[m.end():end]
            has_t = bool(CALL.search(rhs))
            has_ko = any(m.end() <= s < end for s, _ in ko_spans)
            line = src[:m.start()].count('\n') + 1
            if has_t and has_ko:
                findings.append((path.name, line, f'{ident}.{prop}', '한 문장에 t() 와 한글이 함께'))
            groups.setdefault((ident.split('.')[-1], prop), []).append((line, has_t, has_ko))
        for (ident, prop), writes in groups.items():
            t_lines = [l for l, ht, _ in writes if ht]
            ko_lines = [l for l, _, hk in writes if hk]
            if t_lines and ko_lines:
                findings.append((path.name, ko_lines[0], f'{ident}.{prop}',
                                 f't() 쓰기 {t_lines} 와 한글 쓰기 {ko_lines} 가 같은 요소에'))
    if not findings:
        print('번역·한국어 혼재 쓰기 없음: ok')
        return 0
    print(f'같은 요소에 번역과 한국어가 섞여 쓰이는 곳 {len(findings)}건')
    for name, line, target, why in findings:
        print(f'  {name}:{line}  {target}  — {why}')
    return 1


if __name__ == '__main__':
    sys.exit(main())
