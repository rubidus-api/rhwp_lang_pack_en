#!/usr/bin/env python3
"""
드롭다운 옵션 표의 표시 글자를 언어팩으로 옮긴다.

표는 `[값, 표시글]` 짝의 배열이다. 값은 기계가 쓰고 표시글은 사람이 본다.
그런데 표시글을 어딘가에서 **비교**하고 있으면 옮기는 순간 그 비교가 거짓이 된다.
그래서 두 조건을 모두 만족하는 표만 건드린다.

  1. 그 표를 쓰는 자리가 전부 표시 전용으로 검증된 도우미 호출이다.
  2. 그 표의 글자가 이 파일 어디에서도 비교에 쓰이지 않는다.

조건에 못 미치는 표는 그대로 두고 이유와 함께 센다.
"""
import hashlib
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from tsscan import korean_literals  # noqa: E402

KO = re.compile(r'[가-힣]')
TABLE = re.compile(r'^(?:const|let)\s+(?P<name>[A-Z][A-Z0-9_]*)\s*(?::[^=]*)?=\s*\[', re.M)
PAIR = re.compile(r"\[\s*'(?P<value>[^']*)'\s*,\s*'(?P<label>[^']*)'\s*\]")
COMPARE = [
    re.compile(r'(===|!==|==|!=)\s*$'),
    re.compile(r'\bcase\s+$'),
    re.compile(r'\.(includes|startsWith|endsWith|indexOf)\(\s*$'),
    re.compile(r'\b(querySelector|querySelectorAll|closest|matches)\(\s*$'),
]


def slug(text):
    parts = [p for p in re.split(r'[^A-Za-z0-9]+', text) if p]
    if not parts:
        return 'x'
    # DIAGONAL_LINE_TYPE_OPTIONS 처럼 전부 대문자인 이름은 마디마다 소문자로 내린 뒤 잇는다.
    # 그러지 않으면 dIAGONALLINETYPEOPTIONS 같은 이름이 나온다.
    if text.isupper():
        parts = [p.lower() for p in parts]
    head, *rest = parts
    return head[:1].lower() + head[1:] + ''.join(p[:1].upper() + p[1:] for p in rest)


def fingerprint(text):
    return 'x' + hashlib.blake2s(text.strip().encode('utf-8'), digest_size=3).hexdigest()


def array_end(src, start):
    depth = 0
    for i in range(start, len(src)):
        if src[i] == '[':
            depth += 1
        elif src[i] == ']':
            depth -= 1
            if depth == 0:
                return i + 1
    return len(src)


def compared_texts(src):
    out = set()
    for lit in korean_literals(src):
        before = src[max(0, lit.start - 60): lit.start]
        if any(pattern.search(before) for pattern in COMPARE):
            out.add(lit.raw[1:-1])
    return out


def main():
    root = pathlib.Path(sys.argv[1])
    catalog_path = pathlib.Path(sys.argv[2])
    helpers_file = sys.argv[3]
    write = '--write' in sys.argv

    helpers = {}
    for line in pathlib.Path(helpers_file).read_text(encoding='utf-8').splitlines():
        if line.strip():
            filename, name = line.split('\t')
            helpers.setdefault(filename, set()).add(name)

    catalog = json.load(open(catalog_path, encoding='utf-8'))
    moved = 0
    skipped = {'도우미 아님': 0, '비교에 쓰임': 0, '짝 아님': 0}
    touched_files = 0

    for path in sorted(root.glob('*.ts')):
        src = path.read_text(encoding='utf-8')
        allowed = helpers.get(path.name, set())
        # 이 파일이 이미 언어팩을 어떤 이름으로 부르는지 따른다.
        # `t` 가 지역 이름인 파일은 별칭으로 임포트되어 있다 — 그걸 무시하고 t 를 쓰면
        # 이름이 없다는 오류가 난다.
        existing = re.search(r"import\s*\{\s*t(?:\s+as\s+([\w$]+))?\s*\}\s*from\s*'@/i18n/index\.ts'", src)
        fn = (existing.group(1) or 't') if existing else 't'
        compared = compared_texts(src)
        edits = []

        for match in TABLE.finditer(src):
            name = match.group('name')
            # 정규식이 실제로 맞춘 여는 대괄호를 쓴다. 앞에서부터 '[' 를 찾으면
            # 타입 표기(string[][])의 대괄호를 배열 시작으로 잘못 잡는다.
            start = match.end() - 1
            end = array_end(src, start)
            body = src[start:end]
            if not KO.search(body):
                continue

            pairs = list(PAIR.finditer(body))
            korean_pairs = [m for m in pairs if KO.search(m.group('label'))]
            korean_all = [lit for lit in korean_literals(body)]
            if not korean_pairs or len(korean_pairs) < len(korean_all) / 2:
                skipped['짝 아님'] += 1
                continue

            uses = [m for m in re.finditer(r'\b' + name + r'\b', src) if m.start() != match.start(1)]
            call_sites = []
            for use in uses:
                if use.start() >= start and use.end() <= end:
                    continue
                head = src[max(0, use.start() - 60): use.start()]
                call = re.search(r'(?:this\.)?([A-Za-z_$][\w$]*)\(\s*$', head)
                call_sites.append(call.group(1) if call else None)
            if not call_sites or any(c is None or c not in allowed for c in call_sites):
                skipped['도우미 아님'] += 1
                continue

            if any(m.group('label') in compared for m in korean_pairs):
                skipped['비교에 쓰임'] += 1
                continue

            for pair in korean_pairs:
                label = pair.group('label')
                stem = f'option.{slug(name)}.{slug(pair.group("value")) or fingerprint(label)}'
                key = stem
                if catalog.get(key, label) != label:
                    key = f'{stem}.{fingerprint(label)}'
                catalog[key] = label
                lit_start = start + pair.start('label') - 1
                lit_end = start + pair.end('label') + 1
                edits.append((lit_start, lit_end, f"{fn}('{key}')"))
                moved += 1

        if not edits:
            continue
        touched_files += 1
        if write:
            out = src
            for lit_start, lit_end, call in sorted(edits, reverse=True):
                out = out[:lit_start] + call + out[lit_end:]
            if '@/i18n/index.ts' not in out:
                last = None
                for m in re.finditer(r'^import\b[\s\S]*?;\s*$', out, re.M):
                    last = m
                statement = "import { t } from '@/i18n/index.ts';"
                out = (out[:last.end()] + '\n' + statement + out[last.end():]) if last else statement + '\n' + out
            path.write_text(out, encoding='utf-8')

    print(f'파일 {touched_files}개, 표시글 {moved}개 이관')
    print('  건드리지 않은 표: ' + ', '.join(f'{k} {v}개' for k, v in skipped.items()))
    if write:
        with open(catalog_path, 'w', encoding='utf-8') as f:
            json.dump(catalog, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write('\n')
        print(f'카탈로그 {len(catalog)}개')


if __name__ == '__main__':
    main()
