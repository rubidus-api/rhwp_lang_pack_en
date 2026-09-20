#!/usr/bin/env python3
"""
대화상자 소스(src/ui/*.ts)의 한글 문자열을 t('key') 호출로 바꾼다.

바꿔도 안전하다고 **분명히 아는 자리**만 건드린다. 비교식(`=== '없음'`), 선택자,
객체 키, 데이터 표는 손대지 않는다 — 거기서 문자열은 화면이 아니라 값이다.
건드리지 않은 것은 그대로 한국어로 남고, 도구가 몇 개인지 보고한다.

정본은 이 스크립트다. 상류가 움직이면 다시 돌린다(RFC-0001 §2 P2).
"""
import hashlib
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import tsscan

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from tsscan import korean_literals  # noqa: E402

# (이름, 앞 문맥 정규식, 키 역할)
SAFE = [
    ('textContent', re.compile(r'\.textContent\s*=\s*$'), 'text'),
    ('titleAssign', re.compile(r'\.title\s*=\s*$'), 'tooltip'),
    ('placeholder', re.compile(r'\.placeholder\s*=\s*$'), 'placeholder'),
    # `.value =` 는 입력칸이면 화면 글자이고 선택 목록이면 기계 값이다.
    # 목록에 대입하는 자리는 건드리지 않는다 — 옮기면 선택이 깨진다.
    ('valueAssign', re.compile(r'(?<![Ss]elect)\.value\s*=\s*$'), 'value'),
    ('propTitle', re.compile(r'\btitle:\s*$'), 'tooltip'),
    # `name:` 도 넣는다. 기계 식별자로 쓰는 경우가 많아 처음에는 뺐는데, 실제로 화면에 띄워 보니
    # 스킨 카드 제목·수식 분류·유니코드 블록 이름이 전부 이 속성이었다(49곳, 모두 표시용).
    # 위험(어딘가에서 그 문자열과 비교하는 코드)은 check-comparisons.py 가 잡는다.
    ('propLabel', re.compile(r'\b(label|labelText|unitText|caption|hint|tooltip|placeholder|description|name)\s*:\s*$'), 'label'),
    ('setAttribute', re.compile(r'setAttribute\(\s*[\'"](?:title|aria-label|placeholder)[\'"]\s*,\s*$'), 'label'),
    ('alertConfirm', re.compile(r'\b(alert|confirm)\(\s*$'), 'message'),
    ('superTitle', re.compile(r'\bsuper\(\s*$'), 'title'),
    ('showToast', re.compile(r'\bshowToast\(\s*$'), 'message'),
    # 체크상자·라디오 라벨은 대부분 이 자리다(도우미 판정에는 있었는데 변환기에는 빠져 있었다).
    ('createTextNode', re.compile(r'createTextNode\(\s*$'), 'text'),
]

# 탭 라벨 — 로직이 탭 ID 로 구분하게 된 뒤(#7167) 라벨은 ID 바로 옆에 있다. 키도 ID 로 짓는다(dialog.<대화상자>.tab.<id>).
TAB_DEF_BEFORE = re.compile(r"\{\s*id:\s*'([A-Za-z]\w*)',\s*label:\s*$")
TAB_RECORD_ENTRY_BEFORE = re.compile(r"\n\s*([A-Za-z]\w*):\s*$")
TAB_RECORD_HEAD = re.compile(r"const\s+[A-Z_]*TAB_LABELS\b[^=]*=\s*\{")


def tab_id_before(src, pos, before):
    m = TAB_DEF_BEFORE.search(before)
    if m:
        return m.group(1)
    m = TAB_RECORD_ENTRY_BEFORE.search(before)
    if m:
        heads = list(TAB_RECORD_HEAD.finditer(src, 0, pos))
        if heads and '}' not in src[heads[-1].end():pos]:
            return m.group(1)
    return None


IDENT_BEFORE = re.compile(r'([A-Za-z_$][\w$]*)\s*\.\s*(?:textContent|title|placeholder|value)\s*=\s*$')


def slug(text):
    parts = [p for p in re.split(r'[^A-Za-z0-9]+', text) if p]
    if not parts:
        return 'x'
    head, *rest = parts
    return head[:1].lower() + head[1:] + ''.join(p[:1].upper() + p[1:] for p in rest)


def fingerprint(text):
    return 'x' + hashlib.blake2s(text.strip().encode('utf-8'), digest_size=3).hexdigest()


ENCLOSING = re.compile(
    r'(?:^|\n)[ \t]*(?:private |protected |public |static |async |override )*'
    r'(?:function\s+)?([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*(?::\s*[^{]+)?\{'
)


def enclosing_name(src, pos):
    """리터럴을 감싸는 가장 가까운 메서드·함수 이름.

    `dialog.bookmark.text.x31f4ef` 처럼 해시만 남은 키는 사람이 못 읽는다. 대입 대상 식별자가
    없을 때는(인자·삼항식 가지 등) 그 코드가 속한 메서드 이름을 힌트로 쓴다 —
    `dialog.bookmark.doAdd.text` 는 어디서 나온 글자인지 바로 보인다.
    """
    best = None
    for match in ENCLOSING.finditer(src, 0, pos):
        name = match.group(1)
        if name in ('if', 'for', 'while', 'switch', 'catch', 'constructor'):
            continue
        best = name
    return best


def dialog_name(path):
    stem = path.stem
    for suffix in ('-dialog', '-window'):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    return slug(stem)


def template_parts(body):
    """`a${x}b` → ('a{p1}b', ['x'])."""
    out = []
    params = []
    i = 0
    while i < len(body):
        if body[i] == '$' and i + 1 < len(body) and body[i + 1] == '{':
            depth = 1
            j = i + 2
            while j < len(body) and depth:
                if body[j] == '{':
                    depth += 1
                elif body[j] == '}':
                    depth -= 1
                j += 1
            expr = body[i + 2: j - 1]
            params.append(expr)
            out.append('{p%d}' % len(params))
            i = j
            continue
        out.append(body[i])
        i += 1
    return ''.join(out), params


def unescape(body, quote):
    text = body.replace('\\' + quote, quote)
    return text.replace('\\n', '\n').replace('\\t', '\t').replace('\\\\', '\\')


IMPORT_STATEMENT = re.compile(r'^import\b[\s\S]*?;\s*$', re.M)

# 문장 안에서 '값' 으로 쓰이는 자리 — 여기 든 문자열은 화면이 아니라 비교 대상이다.
COMPARE_BEFORE = re.compile(r'(===|!==|==|!=)\s*$|\bcase\s+$|\.(includes|startsWith|endsWith|indexOf)\(\s*$')


def statement_end(src, start):
    """안전 자리 뒤에서 문장이 끝나는 곳. 괄호·문자열 안의 ; 와 , 는 건너뛴다.

    `el.textContent = cond ? 'ㄱ' : 'ㄴ';` 처럼 우변이 식이면 그 식 전체가 화면으로 간다.
    변환기가 대입 바로 뒤 한 글자만 보면 이런 자리를 전부 놓치고, 남은 한국어가
    영어 화면에서 번역을 덮어쓴다(options-dialog 의 localBtn 이 그랬다).
    """
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
            if depth == 0:
                return i          # 인자 자리(super('...', 480))는 닫는 괄호가 끝이다
            depth -= 1
        elif ch == ',' and depth == 0:
            return i              # 인자 자리의 다음 인자
        elif ch == ';' and depth <= 0:
            return i
        i += 1
    return len(src)

# `t` 를 지역 이름으로 쓰는 곳이 있으면 임포트한 t 가 가려진다.
# 가려진 자리에서 t('key') 는 그 지역 값을 부르려 들어 조용히 깨진다.
SHADOWS_T = re.compile(r'(?:\(\s*t\s*[,)]|\b(?:const|let|var|function)\s+t\b|\bt\s*=>)')


def enclosing_call(src, pos):
    """pos 의 리터럴을 인자로 가진 가장 안쪽 호출의 함수 이름. 없으면 None."""
    depth = 0
    i = pos - 1
    while i >= 0:
        ch = src[i]
        if ch in ')]}':
            depth += 1
        elif ch in '([{':
            if depth == 0:
                if ch != '(':
                    return None
                m = re.search(r'([A-Za-z_$][\w$]*)\s*(?:<[^<>()]*>)?\s*$', src[max(0, i - 60):i])
                return m.group(1) if m else None
            depth -= 1
        elif ch == ';' and depth == 0:
            return None
        i -= 1
    return None


EXISTING_I18N_IMPORT = re.compile(r"import\s*\{[^}]*\bt\b(?:\s+as\s+([A-Za-z_$][\w$]*))?[^}]*\}\s*from\s*'[^']*i18n/index(?:\.ts)?'")


COMMAND_FACTORY = re.compile(r'^\s*(?:export\s+)?function\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*:\s*CommandDef\s*\{', re.M)


def matching_paren(src, open_pos, opener='(', closer=')'):
    """여는 괄호의 짝. 문자열 안의 괄호는 세지 않는다."""
    depth, i, quote = 0, open_pos, None
    while i < len(src):
        ch = src[i]
        if quote:
            if ch == '\\':
                i += 1
            elif ch == quote:
                quote = None
        elif ch in "'\"`":
            quote = ch
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return len(src)


def top_level_args(text, with_offsets=False):
    """깊이 0 의 쉼표로 가른 인자 목록(문자열 안 쉼표는 무시)."""
    out, depth, quote, start = [], 0, None, 0
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == '\\':
                i += 1
            elif ch == quote:
                quote = None
        elif ch in "'\"`":
            quote = ch
        elif ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth -= 1
        elif ch == ',' and depth == 0:
            out.append((start, text[start:i]))
            start = i + 1
        i += 1
    if text[start:].strip():
        out.append((start, text[start:]))
    return out if with_offsets else [a for _, a in out]


# [값, 표시글] 짝 배열을 for…of 로 풀어 option·단추를 만드는 자리. 선 종류·적용 범위·번호 모양 목록이 모두 이 꼴이다.
PAIR_LOOP = re.compile(
    r'for\s*\(\s*const\s*\[(?P<names>[^\]\n]+)\]\s+of\s+(?P<src>[A-Za-z_$][\w$.]*|\[)'
    r'|(?P<src2>[A-Za-z_$][\w$.]*)\.forEach\(\s*\(?\s*\[(?P<names2>[^\]\n]+)\]')
# 풀린 변수가 가도 되는 표시 자리
PAIR_DISPLAY = [
    r'\.(?:textContent|innerText|title|placeholder|alt)\s*=\s*[^;\n]*\b%s\b',
    r'createTextNode\(\s*[^)]*\b%s\b',
    r'setAttribute\(\s*[\'"](?:title|aria-label|placeholder|alt)[\'"]\s*,[^)]*\b%s\b',
    r'\b(?:label|title|text)\s*:\s*%s\b',
]
PAIR_MACHINE = (r'\.(?:value|id|htmlFor|className|name)\s*=\s*[^;\n]*\b%s\b|dataset\.[\w$]+\s*=\s*[^;\n]*\b%s\b'
                r'|\b%s\s*(?:===|!==|==|!=)|(?:===|!==|==|!=)\s*%s\b')


def code_only(body):
    """문자열·주석을 비운 사본(템플릿의 ${…} 는 코드라 남긴다).

    `const lbl = document.createElement('label')` 의 'label' 을 변수 사용으로 세면
    짝 배열의 표시글이 '섞임' 으로 판정돼 옮기지 못한다(2026-09-20).
    """
    out = list(body)
    for lit in tsscan.literals(body):
        for i in range(lit.start, min(lit.end, len(out))):
            out[i] = ' '
        if lit.quote == '`':
            for mm in re.finditer(r'\$\{[^{}]*\}', body[lit.start:lit.end]):
                for i in range(lit.start + mm.start(), lit.start + mm.end()):
                    out[i] = body[i]
    text = ''.join(out)
    text = re.sub(r'//[^\n]*', lambda mm: ' ' * len(mm.group(0)), text)
    return re.sub(r'/\*[\s\S]*?\*/', lambda mm: ' ' * len(mm.group(0)), text)


def pair_loop_labels(src, allowed=()):
    """짝 배열에서 '표시글' 자리에 있는 문자열 리터럴의 시작 위치 집합.

    풀린 이름이 표시 자리로만 가고 나머지 이름은 기계 자리로만 갈 때에만 인정한다.
    (하나라도 비교·저장에 쓰이면 그 배열은 건드리지 않는다.)
    """
    out = set()
    for m in PAIR_LOOP.finditer(src):
        raw_names = m.group('names') or m.group('names2')
        names = [n.strip() for n in raw_names.split(',') if n.strip()]
        if len(names) < 2:
            continue
        brace = src.find('{', m.end())
        if brace < 0:
            continue
        body = src[brace:matching_paren(src, brace, '{', '}') + 1]
        helper_alt = '|'.join(re.escape(h) for h in sorted(allowed)) if allowed else None
        code = code_only(body)
        roles = []
        for name in names:
            uses = len(re.findall(r'(?<![.\w$])' + re.escape(name) + r'\b', code))
            shown = sum(len(re.findall(pat % re.escape(name), body)) for pat in PAIR_DISPLAY)
            # 검증된 표시 도우미에 넘기는 것도 표시다: this.radioRow(name, value, label, checked).
            # 다만 한 호출에 값과 표시글이 함께 들어가므로 따로 센다 — 값 자리까지 표시로 보면 안 된다.
            helper_shown = len(re.findall(r'(?<![\w$.])(?:this\.)?(?:' + helper_alt + r')\([^()]*\b' + re.escape(name) + r'\b', body)) if helper_alt else 0
            machine = len(re.findall(PAIR_MACHINE % tuple([re.escape(name)] * 4), body))
            if uses == 0:
                roles.append('unused')
            elif machine and shown == 0:
                roles.append('machine')            # 비교·기계 대입만 — 도우미 인자 매칭은 값 자리일 수 있다
            elif shown + helper_shown >= uses and machine == 0:
                roles.append('display')
            else:
                roles.append('mixed')
        if 'display' not in roles:
            continue        # 표시 자리가 없는 배열은 건드리지 않는다. 섞인 이름의 칸은 아래에서 제외된다.
        # 배열 리터럴 자리 찾기
        source = m.group('src') or m.group('src2')
        if source == '[':
            open_bracket = src.index('[', m.end() - 1)
        else:
            var = source.split('.')[0]
            # 타입 표기에 대괄호·줄바꿈이 들어간다: `const presets: [string, string, () => void][] = [`
            decl = None
            for cand in re.finditer(r'(?:const|let|var)\s+' + re.escape(var) + r'\b[^;]*?=\s*\[', src[:m.start()], re.S):
                decl = cand
            if not decl:
                continue
            open_bracket = src.rindex('[', decl.start(), decl.end())
        close = matching_paren(src, open_bracket, '[', ']')
        for offset, element in top_level_args(src[open_bracket + 1:close], with_offsets=True):
            el = element.strip()
            if not el.startswith('['):
                continue
            el_open = open_bracket + 1 + offset + element.index('[')
            el_close = matching_paren(src, el_open, '[', ']')
            items = top_level_args(src[el_open + 1:el_close], with_offsets=True)
            for i, (inner_offset, item) in enumerate(items):
                if i >= len(roles) or roles[i] != 'display':
                    continue
                stripped = item.strip()
                if not stripped or stripped[0] not in "'\"`" or not re.search(r'[가-힣]', stripped):
                    continue
                out.add(el_open + 1 + inner_offset + (len(item) - len(item.lstrip())))
    return out


# 표시 전용으로 판정된 도우미에 **배열 리터럴**로 넘기는 글자: appendHeaderRow(thead, ['위치', '종류'])
# 그리고 그런 도우미로만 흘러가는 이름 붙은 글자 배열: const TAB_TYPE_NAMES = ['왼쪽', …]
def record_value_labels(src, allowed):
    """`const headLabel: Record<string, string> = { None: '없음', … }` 의 값.

    그 이름이 표시 자리(t() 인자·textContent 대입·검증된 도우미)에서만 읽힐 때만 옮긴다.
    """
    out = {}
    names = '|'.join(re.escape(h) for h in sorted(allowed)) if allowed else None
    for decl in re.finditer(r'(?:const|let)\s+([A-Za-z_$][\w$]*)\s*:\s*Record<\s*string\s*,\s*string\s*>\s*=\s*\{', src):
        var = decl.group(1)
        open_brace = src.index('{', decl.end() - 1)
        close = matching_paren(src, open_brace, '{', '}')
        body = src[open_brace + 1:close]
        if not re.search(r'[가-힣]', body):
            continue
        uses = [u for u in re.finditer(r'(?<![.\w$])' + re.escape(var) + r'\b', src) if u.start() != decl.start(1)]
        if not uses:
            continue
        ok = True
        for u in uses:
            head = src[max(0, u.start() - 90):u.start()]
            display = bool(re.search(r'\bt\(|\bi18n[A-Za-z]*\(', head) and head.rstrip().endswith((':', '(', ',')))
            display = display or bool(re.search(r'\.(?:textContent|innerText|title|placeholder)\s*=\s*[^;\n]*$', head))
            if names:
                display = display or bool(re.search(r'(?:this\.)?(?:' + names + r')\([^()]*$', head))
            if not display:
                ok = False
                break
        if not ok:
            continue
        for offset, entry in top_level_args(body, with_offsets=True):
            m = re.match(r"\s*([A-Za-z_$][\w$]*|'[^']*')\s*:\s*", entry)
            if not m:
                continue
            value = entry[m.end():].strip()
            if not value or value[0] not in "'`\"" or not re.search(r'[가-힣]', value):
                continue
            pos = open_brace + 1 + offset + m.end() + (len(entry[m.end():]) - len(entry[m.end():].lstrip()))
            out[pos] = f'{slug(var)}.{slug(m.group(1).strip(chr(39)))}'
    return out


def helper_array_labels(src, allowed):
    """표시 도우미로 가는 배열 리터럴 원소의 시작 위치."""
    out = set()
    if not allowed:
        return out
    names = '|'.join(re.escape(h) for h in sorted(allowed))
    for call in re.finditer(r'(?<![\w$.])(?:this\.)?(' + names + r')(?:<[^<>()]*>)?\(', src):
        open_paren = call.end() - 1
        close = matching_paren(src, open_paren)
        for offset, arg in top_level_args(src[open_paren + 1:close], with_offsets=True):
            stripped = arg.strip()
            if not stripped.startswith('['):
                continue
            el_open = open_paren + 1 + offset + arg.index('[')
            for inner_offset, item in top_level_args(src[el_open + 1:matching_paren(src, el_open, '[', ']')], with_offsets=True):
                text = item.strip()
                base_pos = el_open + 1 + inner_offset + (len(item) - len(item.lstrip()))
                if text.startswith('['):
                    # `[['custom', '사용자'], …]` — 한 겹 더 들어간다. 마지막 칸이 표시글이다.
                    nested_open = base_pos
                    nested = top_level_args(src[nested_open + 1:matching_paren(src, nested_open, '[', ']')], with_offsets=True)
                    if nested:
                        off2, last = nested[-1]
                        text2 = last.strip()
                        if text2 and text2[0] in "'`\"" and re.search(r'[가-힣]', text2):
                            out.add(nested_open + 1 + off2 + (len(last) - len(last.lstrip())))
                    continue
                if text and text[0] in "'`\"" and re.search(r'[가-힣]', text):
                    out.add(base_pos)
    # 이름 붙은 배열: 그 이름이 표시 자리(도우미 인자·textContent 대입)에서만 읽힐 때
    for decl in re.finditer(r'(?:const|let)\s+([A-Za-z_$][\w$]*)\s*(?::[^;]*?)?=\s*\[', src):
        var = decl.group(1)
        open_bracket = src.index('[', decl.end() - 1)
        close = matching_paren(src, open_bracket, '[', ']')
        items = top_level_args(src[open_bracket + 1:close], with_offsets=True)
        if not items or not any(re.search(r'[가-힣]', it.strip()) for _, it in items):
            continue
        uses = [u for u in re.finditer(r'(?<![.\w$])' + re.escape(var) + r'\b', src) if u.start() != decl.start(1)]
        shown = 0
        for u in uses:
            head = src[max(0, u.start() - 80):u.start()]
            if names and re.search(r'(?:this\.)?(?:' + names + r')\(\s*[^()]*$', head):
                shown += 1
            elif re.search(r'\.(?:textContent|innerText|title|placeholder)\s*=\s*[^;\n]*$', head):
                shown += 1
            else:
                # `sampleLines.forEach((text) => { … text … })` — 푼 이름이 표시 자리로만 가면 표시다
                tail = src[u.end():u.end() + 400]
                fm = re.match(r'\.forEach\(\s*\(?\s*([A-Za-z_$][\w$]*)', tail)
                if not fm:
                    continue
                item = fm.group(1)
                open_brace = src.find('{', u.end())
                if open_brace < 0:
                    continue
                loop_body = src[open_brace:matching_paren(src, open_brace, '{', '}') + 1]
                item_uses = len(re.findall(r'(?<![.\w$])' + re.escape(item) + r'\b', loop_body)) - 1
                item_shown = sum(len(re.findall(pat % re.escape(item), loop_body)) for pat in PAIR_DISPLAY)
                if item_shown and item_shown >= item_uses:
                    shown += 1
        if not uses or shown < len(uses):
            continue
        for inner_offset, item in items:
            text = item.strip()
            if text and text[0] in "'`\"" and re.search(r'[가-힣]', text):
                out.add(open_bracket + 1 + inner_offset + (len(item) - len(item.lstrip())))
    return out


def pick_name(src):
    """이 파일에서 쓸 수 있는 이름을 고른다.

    `t` 가 지역 이름으로 쓰이면 임포트가 가려진다. 그렇다고 아무 별칭이나 쓰면
    그 별칭이 또 지역 이름일 수 있다(`msg` 로 한 번 당했다). 그러니 **소스에
    아예 나오지 않는 이름**임을 확인하고 쓴다.
    """
    if not SHADOWS_T.search(src):
        return 't'
    for candidate in ['i18nText', 'i18nMessage', 'localizedText']:
        if not re.search(r'\b' + candidate + r'\b', src):
            return candidate
    n = 2
    while re.search(r'\bi18nText' + str(n) + r'\b', src):
        n += 1
    return f'i18nText{n}'


def insert_import(src, line="import { t } from '@/i18n/index.ts';"):
    """마지막 import 문 **뒤에** 넣는다.

    여러 줄 import 는 첫 줄만 'import' 로 시작한다. 줄 단위로 보고 넣으면
    괄호 안에 끼어들어 파일을 망가뜨린다 — 문장 끝을 찾아야 한다.
    """
    last = None
    for match in IMPORT_STATEMENT.finditer(src):
        last = match
    if last is None:
        # import 가 하나도 없는 파일: 머리의 문서 주석(/** … */) 뒤에 넣는다.
        # 주석 위에 박으면 파일을 여는 사람 눈에 기계가 넣은 줄이 먼저 보인다.
        doc = re.match(r'\s*/\*\*[\s\S]*?\*/\s*', src)
        if doc:
            end = doc.end()
            return src[:end] + line + '\n' + src[end:]
        return line + '\n' + src
    end = last.end()
    return src[:end] + '\n' + line + src[end:]


def load_helpers(path):
    """verify-helpers.py 가 표시 전용이라고 판정한 (파일, 도우미) 쌍.

    이름을 믿지 않고 정의를 읽어 판정한 목록만 받는다.
    """
    allowed = {}
    if not path or not pathlib.Path(path).exists():
        return allowed
    for line in pathlib.Path(path).read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        filename, name = line.split('\t')
        allowed.setdefault(filename, set()).add(name)
    return allowed


def main():
    root = pathlib.Path(sys.argv[1])
    catalog_path = pathlib.Path(sys.argv[2])
    # 상대 경로 import 의 목적지 — root 는 언제나 rhwp-studio/src 아래의 디렉터리다.
    src_root = root
    while src_root.name != 'src':
        src_root = src_root.parent
    i18n_index = src_root / 'i18n' / 'index.ts'
    write = '--write' in sys.argv
    helpers_path = None
    if '--helpers' in sys.argv:
        helpers_path = sys.argv[sys.argv.index('--helpers') + 1]
    helpers = load_helpers(helpers_path)

    catalog = json.load(open(catalog_path, encoding='utf-8')) if catalog_path.exists() else {}
    added = {}
    touched_files = 0
    changed = 0
    left = 0

    shadowed_files = []
    for path in sorted(root.glob('*.ts')):
        src = path.read_text(encoding='utf-8')
        base = f'dialog.{dialog_name(path)}'
        # 이미 i18n 을 가져오는 파일(상류에 병합된 대화상자)은 그 이름을 쓴다. 새 이름을 고르면 import 가
        # 이미 있다고 보고 넣지 않아 없는 이름을 부르게 된다(d5fbe8b5d: `t as i18nText` 파일에 i18nMessage).
        existing = EXISTING_I18N_IMPORT.search(src)
        name = (existing.group(1) or 't') if existing else pick_name(src)
        if name != 't':
            shadowed_files.append(f'{path.name}({name})')
        allowed_helpers = helpers.get(path.name, set())
        edits = []
        # 안전 자리 뒤의 문장 범위를 먼저 모은다. 그 범위 안의 한글 리터럴은 식의 어디에
        # 있든(삼항식·??·||·+ 의 가지) 화면으로 가는 글자다 — 단, 비교식 안은 값이다.
        all_korean = korean_literals(src)
        covered = {}   # lit.start -> (role, hint)
        for lit in all_korean:
            before = src[max(0, lit.start - 90): lit.start]
            role = None
            for _, pattern, kind in SAFE:
                if pattern.search(before):
                    role = kind
                    break
            if role is None and allowed_helpers:
                call = re.search(r'(?:this\.)?([A-Za-z_$][\w$]*)(?:<[^<>()]*>)?\(\s*$', before)
                if call and call.group(1) in allowed_helpers:
                    role = 'label'
            if role is None and allowed_helpers:
                # 검증된 도우미의 둘째·셋째 인자도 화면 글자다: mmRow(t('…'), x, '위쪽') 에서
                # '위쪽' 만 한국어로 남는 것이 그 증거였다. 이 리터럴이 어느 호출의 인자인지
                # 괄호를 거슬러 올라가 본다 — 그 호출이 검증된 도우미면 역할을 준다.
                owner = enclosing_call(src, lit.start)
                if owner in allowed_helpers:
                    role = 'label'
            if role is None:
                continue
            end = statement_end(src, lit.start)
            for other in all_korean:
                if lit.start <= other.start < end and other.start not in covered:
                    head = src[max(0, other.start - 40): other.start]
                    if COMPARE_BEFORE.search(head):
                        continue
                    covered[other.start] = role
        # 안전 자리 뒤 문장 안에 있지는 않지만 우변 식의 첫 리터럴이 아닌 경우도 있다:
        # `x.textContent = cond ? 'ㄱ' : 'ㄴ'` 에서 'ㄱ' 은 대입 바로 뒤가 아니라 `? ` 뒤다.
        # 그래서 대입 자체를 기준으로 한 번 더 훑는다.
        for m in re.finditer(r'\.(?:textContent|innerText|title|placeholder|alt|value)\s*=(?!=)|\bsuper\(|\b(?:alert|confirm|showToast)\(', src):
            if re.search(r'[Ss]elect\.value\s*=$', src[max(0, m.start() - 12): m.end()]):
                continue
            end = statement_end(src, m.end())
            role = 'text' if 'textContent' in m.group(0) or 'innerText' in m.group(0) else (
                'tooltip' if 'title' in m.group(0) else 'title' if 'super' in m.group(0) else 'message')
            for other in all_korean:
                if m.end() <= other.start < end and other.start not in covered:
                    head = src[max(0, other.start - 40): other.start]
                    if COMPARE_BEFORE.search(head):
                        continue
                    covered[other.start] = role

        # 짝 배열(`for (const [val, lbl] of [['0','선 없음'], …])`)의 표시글 자리
        for start in pair_loop_labels(src, allowed_helpers):
            covered.setdefault(start, 'label')

        # 표시 도우미로 넘기는 배열 리터럴·이름 붙은 표시용 배열
        for start in helper_array_labels(src, allowed_helpers):
            covered.setdefault(start, 'label')

        # 지역 Record<string, string> 표의 값
        record_keys = record_value_labels(src, allowed_helpers)
        for start in record_keys:
            covered.setdefault(start, 'label')

        # 명령 정의 공장(`function stub(id: string, label: string): CommandDef`)의 label 인자는 명령 팔레트·
        # 메뉴에 나가는 이름이다. 본문에서 label 이 돌려주는 객체의 label 속성으로만 쓰일 때만 옮긴다.
        # 같은 문장의 다른 한글(되돌리기 기록 이름 등)까지 번지지 않게 그 인자 하나만 표시한다.
        factory_keys = {}
        for fm in COMMAND_FACTORY.finditer(src):
            fname = fm.group(1)
            open_paren = src.index('(', fm.start())
            close = matching_paren(src, open_paren)
            names = [re.match(r'\s*(?:\.\.\.)?([A-Za-z_$][\w$]*)', a).group(1) for a in top_level_args(src[open_paren + 1:close])
                     if re.match(r'\s*(?:\.\.\.)?[A-Za-z_$]', a)]
            if 'label' not in names:
                continue
            index = names.index('label')
            brace = src.index('{', close)
            body = src[brace:matching_paren(src, brace, '{', '}') + 1]
            rest = re.sub(r'(?<![.\w$])label\s*:\s*label\b|^\s*label\s*(?=,|\n)', '', body, flags=re.M)
            if re.search(r'(?<![.\w$\'"])label\b(?!\s*:)', rest):
                continue
            for call in re.finditer(r'(?<![\w$.])' + re.escape(fname) + r'\(', src):
                if src[max(0, call.start() - 9):call.start()].endswith('function '):
                    continue
                open_call = call.end() - 1
                args = top_level_args(src[open_call + 1:matching_paren(src, open_call)], with_offsets=True)
                if len(args) <= index:
                    continue
                offset, arg = args[index]
                lead = len(arg) - len(arg.lstrip())
                start = open_call + 1 + offset + lead
                if src[start] not in "'`\"" or not re.search(r'[가-힣]', arg):
                    continue
                covered.setdefault(start, 'label')
                first = args[0][1].strip()
                cmd = re.fullmatch(r"'([a-z]+):([a-z0-9-]+)'", first)
                plain = re.fullmatch(r"'([A-Za-z][\w-]*)'", first)
                if cmd:
                    # 마크업이 같은 명령에 같은 글로 만든 키가 있으면 그 키를 쓰고, 글이 다르면(메뉴 '위' / 팔레트
                    # '캡션 - 위') registryLabel 로 가른다 — 같은 키에 덮어쓰면 상류 메뉴 글이 바뀐다(seed 검사가 잡았다).
                    markup = f'command.{slug(cmd.group(1))}.{slug(cmd.group(2))}.label'
                    text_here = unescape(arg.strip()[1:-1], arg.strip()[0])
                    role_name = 'label' if catalog.get(markup) == text_here else 'registryLabel'
                    factory_keys[start] = f'{base}.{slug(cmd.group(2))}.{role_name}'
                elif plain:
                    factory_keys[start] = f'{base}.{slug(fname)}.{slug(plain.group(1))}'

        # 입력칸 기본값 중 '나중에 읽히는' 것은 화면 글자가 아니라 문서로 들어가는 값이다
        # (새 스타일 이름·누름틀 안내문·책갈피 이름). 영어 화면에서 문서 내용이 달라지면 안 되므로
        # 같은 식별자의 .value 를 어디선가 읽는 경우 그 대입은 옮기지 않는다. readOnly 입력칸처럼
        # 쓰기만 하는 자리는 화면 글자라 옮긴다.
        def value_is_read_back(ident):
            return re.search(r'\b' + re.escape(ident) + r'\.value\b(?!\s*=[^=])', src) is not None

        for m in re.finditer(r'\b([A-Za-z_$][\w$.]*?)\.value\s*=(?!=)', src):
            ident = m.group(1).split('.')[-1]
            if not value_is_read_back(ident):
                continue
            end = statement_end(src, m.end())
            for other in all_korean:
                if m.end() <= other.start < end:
                    covered.pop(other.start, None)

        # 모델 기본값(`name: '...'` 이 클래스 안에서 쓰이는 경우)도 같은 이유로 뺀다.
        # 모듈 최상위 표(상수 배열)의 name 은 화면 라벨이고, 클래스 안의 name 은 대개 저장되는 값이다.
        for lit in list(covered):
            before = src[max(0, lit - 30): lit]
            if re.search(r'\bname\s*:\s*$', before):
                # 이 리터럴이 모듈 최상위(들여쓰기 없는 const 표) 안에 있나?
                line_start = src.rfind('\n', 0, lit) + 1
                # 가장 가까운 위쪽의 'const X' 또는 'class ' 선언을 찾아 어느 쪽이 가까운지 본다
                up = src[:lit]
                last_const = max(up.rfind('\nconst '), up.rfind('\nexport const '))
                last_class = max(up.rfind('\nclass '), up.rfind('\nexport class '), up.rfind('\nfunction '), up.rfind('\nexport function '))
                if last_class > last_const:
                    covered.pop(lit, None)

        # ② 표시용 상수 맵: `const NAME: Record<…, string> = { k: '…', … }` 또는 값이 전부 한글 리터럴인
        #    객체. 키는 기계 값(상태 코드)이고 값은 화면 글자다(local-fonts-modal 의 STATUS_LABEL).
        for m in re.finditer(r'\b(?:const|let)\s+[A-Z_][A-Z0-9_]*\s*(?::\s*Record<[^=]*?string[^=]*?>)?\s*=\s*\{', src):
            start = m.end() - 1
            depth = 0
            end = start
            while end < len(src):
                if src[end] == '{':
                    depth += 1
                elif src[end] == '}':
                    depth -= 1
                    if depth == 0:
                        break
                end += 1
            body = src[start:end]
            inside = [l for l in all_korean if start < l.start < end]
            # 값 자리(`: '…'`)의 리터럴만. 키 자리·비교는 제외
            vals = [l for l in inside if re.search(r':\s*$', src[max(0, l.start - 10): l.start])]
            if vals and len(vals) == len(inside) and 'Record<' in m.group(0):
                for l in vals:
                    covered.setdefault(l.start, 'label')

        # ③ t() 파라미터로 흘러드는 변수의 폴백 리터럴: `const x = a || '…'` / `a ?? '…'` 가 뒤에서
        #    `{ p1: x }` 로 쓰이면 그 폴백은 화면으로 간다(unsaved-changes 의 '현재 문서').
        #    `const pageLine = \`${n}쪽\`` 처럼 템플릿 전체가 변수에 담겨 { p1: pageLine } 으로 가는 것도 같다.
        # 판정은 '원본' 기준이어야 한다: 변환 전 소스에서 이 변수가 안전 자리의 템플릿 `${var}` 안에
        # 쓰이면(곧 {pN} 이 될 자리) 그 변수에 대입되는 한글은 화면으로 간다. 변환 뒤의 `p1: var` 를
        # 찾으면 한 패스 안에서는 아직 없어서 놓친다(unsaved-changes 의 '현재 문서' 가 그랬다).
        for m in re.finditer(r'\b(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*', src):
            var = m.group(1)
            flows_to_display = (
                re.search(r'\$\{\s*' + re.escape(var) + r'\b', src) is not None
                or re.search(r'\bp\d+:\s*(?:[^,}]*\b)?' + re.escape(var) + r'\b', src) is not None
            )
            if not flows_to_display:
                continue
            end = statement_end(src, m.end() - 1)
            for l in all_korean:
                if m.start() <= l.start < end:
                    head = src[max(0, l.start - 40): l.start]
                    if not COMPARE_BEFORE.search(head):
                        covered.setdefault(l.start, 'text')

        for lit in all_korean:
            before = src[max(0, lit.start - 90): lit.start]
            role = covered.get(lit.start)
            if role is None:
                left += 1
                continue

            if lit.quote == '`':
                # 템플릿 리터럴 안의 \n 도 실제 줄바꿈이다. 풀지 않으면 카탈로그에
                # 역슬래시가 그대로 들어가 번역과 원문이 서로 다른 문자열이 된다.
                raw, params = template_parts(lit.body)
                text = unescape(raw, '`')
            else:
                text, params = unescape(lit.body, lit.quote), []
            # 앞뒤 줄바꿈을 떼지 않는다. `"{p1}"\n\n` 의 끝 줄바꿈은 white-space: pre-line 에서
            # 다음 문장과의 간격이다 — 떼면 한국어 화면에서 파일명과 다음 문장이 붙는다(회귀).

            hint = ''
            m = IDENT_BEFORE.search(before)
            if m:
                hint = slug(m.group(1))
            else:
                call = re.search(r'(?:this\.)?([A-Za-z_$][\w$]*)(?:<[^<>()]*>)?\(\s*(?:[^()]*,\s*)?$', before)
                if call and call.group(1) in allowed_helpers:
                    hint = slug(call.group(1))
            if not hint:
                # 삼항식 가지·인자·폴백처럼 대입 대상이 바로 앞에 없는 자리: 같은 문장의 대입 대상을
                # 먼저 찾고, 그것도 없으면 감싸는 메서드 이름을 쓴다. 해시만 남기지 않는다.
                stmt_start = max(src.rfind(';', 0, lit.start), src.rfind('{', 0, lit.start), src.rfind('\n\n', 0, lit.start))
                stmt = src[stmt_start:lit.start]
                owner = re.search(r'([A-Za-z_$][\w$]*)\s*\.\s*(?:textContent|innerText|title|placeholder|value|alt)\s*=', stmt)
                if owner:
                    hint = slug(owner.group(1))
                else:
                    enclosing = enclosing_name(src, lit.start)
                    if enclosing:
                        hint = slug(enclosing)
            stem = f'{base}.{hint}.{role}' if hint else f'{base}.{role}'
            tab_id = tab_id_before(src, lit.start, before) if not params else None
            if tab_id:
                stem = f'{base}.tab.{tab_id}'
            if lit.start in factory_keys:
                stem = factory_keys[lit.start]
            elif lit.start in record_keys:
                stem = f'{base}.{record_keys[lit.start]}'
            key = stem
            if catalog.get(key, text) != text or added.get(key, text) != text:
                key = f'{stem}.{fingerprint(text)}'
            added[key] = text
            catalog[key] = text

            if params:
                # 템플릿의 ${…} 안에 든 한글(`${name || '선택한 문서'}`)은 화면으로 가는 폴백이다.
                # 그대로 두면 영어 문장 한가운데 한국어가 박힌다. 키를 만들어 t() 로 감싼다.
                wrapped = []
                for expr in params:
                    def wrap(mm, _expr=expr):
                        inner = mm.group(0)[1:-1]
                        inner_key = f'{base}.{hint or role}.param.{fingerprint(inner)}'
                        added[inner_key] = inner
                        catalog[inner_key] = inner
                        return f"{name}('{inner_key}')"
                    wrapped.append(re.sub(r"'[^'\n]*[가-힣][^'\n]*'", wrap, expr))
                params = wrapped
                args = ', '.join(f'p{i + 1}: {expr}' for i, expr in enumerate(params))
                call = f"{name}('{key}', {{ {args} }})"
            else:
                call = f"{name}('{key}')"
            edits.append((lit.start, lit.end, call))

        if not edits:
            continue
        touched_files += 1
        changed += len(edits)
        if write:
            out = src
            for start, end, call in sorted(edits, reverse=True):
                out = out[:start] + call + out[end:]
            if "i18n/index.ts" not in out:
                # 별칭(@/)이 아니라 **상대 경로**로 임포트한다. 상류 테스트는 로더 없는 순수
                # `node --test` 로 소스 모듈을 직접 import 하기도 하는데(style-toolbar-overflow
                # 테스트가 실제 그랬다), 그 경로에는 @/ 를 풀어 줄 것이 없다. 상대 경로는
                # tsc·vite·순수 node 세 곳 모두에서 같은 파일로 풀린다.
                rel = os.path.relpath(i18n_index, path.parent).replace(os.sep, '/')
                if not rel.startswith('.'):
                    rel = './' + rel
                statement = (
                    f"import {{ t }} from '{rel}';" if name == 't'
                    else f"import {{ t as {name} }} from '{rel}';"
                )
                out = insert_import(out, statement)
            path.write_text(out, encoding='utf-8')

    print(f'파일 {touched_files}개, 치환 {changed}곳, 손대지 않음 {left}곳')
    if shadowed_files:
        print(f"지역 이름 t 가 있어 별칭(msg)을 쓴 파일 {len(shadowed_files)}개: {', '.join(shadowed_files[:5])}")
    if write:
        with open(catalog_path, 'w', encoding='utf-8') as f:
            json.dump(catalog, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write('\n')
        print(f'카탈로그 {catalog_path}: {len(catalog)}개 (+{len(added)})')


if __name__ == '__main__':
    main()
