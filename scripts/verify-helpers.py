#!/usr/bin/env python3
"""
도우미 메서드의 첫 인자가 '화면에 나가기만 하는가' 를 확인한다.

이름이 label 이라고 표시 전용이라는 보장은 없다. 인자가 비교에 쓰이거나 id·class·
dataset 로 들어가면 옮기는 순간 로직이 깨진다. 그러니 정의를 읽어서 판정한다.

표시로 인정하는 자리:
  textContent / innerText / title / label / placeholder / alt / value 대입,
  createTextNode(...), setAttribute('title'|'aria-label'|'placeholder', ...)
"""
import collections
import pathlib
import re
import sys

DISPLAY = [
    re.compile(r'\.(?:textContent|innerText|title|label|placeholder|alt|value)\s*=\s*[^;]*\b%s\b'),
    re.compile(r'createTextNode\(\s*[^)]*\b%s\b'),
    re.compile(r'setAttribute\(\s*[\'"](?:title|aria-label|placeholder|alt)[\'"]\s*,[^)]*\b%s\b'),
    re.compile(r'\b(?:this\.)?[A-Za-z_$][\w$]*\(\s*%s\b'),   # 다른 표시 도우미로 넘김
]

# 매개변수 목록의 끝은 정규식으로 못 찾는다 — `handler: () => void` 처럼 타입에 괄호가 들면
# `[^)]*\)` 가 첫 `)` 에서 멈춰 정의 자체를 못 읽는다(createButton·createRow 가 그랬다).
# 그래서 머리만 정규식으로 잡고 괄호 깊이로 끝을 센다.
DEF_HEAD = re.compile(
    r'^\s*(?:private |protected |public |static |async )*(?:function\s+)?'
    r'(?P<name>[A-Za-z_$][\w$]*)\(\s*(?P<param>[A-Za-z_$][\w$]*)\s*[?:]'
    r'|'
    # 지역 화살표 도우미: const addFormatButton = (label: string, …) => {
    r'^\s*(?:const|let)\s+(?P<name2>[A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(\s*(?P<param2>[A-Za-z_$][\w$]*)\s*[?:]',
    re.M,
)
SKIP_NAMES = {'if', 'for', 'while', 'switch', 'catch', 'constructor', 'super', 'return'}


def param_list_end(src, open_paren):
    depth = 0
    i = open_paren
    while i < len(src):
        ch = src[i]
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def param_names(src, open_paren, close):
    """매개변수 (이름, 문자열형인가) 목록. 깊이 0 의 , 로 가른다.

    변환기가 옮기는 것은 문자열 인자뿐이다. 그러니 판정도 `text: string` 처럼 타입이 string
    (또는 string 을 품은 합집합·옵션)인 매개변수만 보면 된다. 숫자 매개변수(`mm: number`)는
    `.value = mm` 로 쓰여도 표시 글자가 아니다 — 그걸 세면 hwp16ToMm 이 '표시 전용' 으로 둔갑한다.
    """
    text = src[open_paren + 1:close]
    names, depth, cur = [], 0, ''
    for ch in text:
        if ch in '([{<':
            depth += 1
        elif ch in ')]}>':
            depth -= 1
        if ch == ',' and depth == 0:
            names.append(cur)
            cur = ''
        else:
            cur += ch
    names.append(cur)
    out = []
    for piece in names:
        m = re.match(r'\s*(?:readonly\s+|private\s+|public\s+)?(?:\.\.\.)?([A-Za-z_$][\w$]*)\s*\??\s*(?::\s*([^=]+))?', piece)
        if not m:
            continue
        name, typ = m.group(1), (m.group(2) or '').strip()
        # 타입이 없으면 기본값으로 판단한다: `disabled = false`·`count = 0` 은 문자열이 아니다.
        # 기본값도 없으면 문자열일 수 있으니 후보에 둔다.
        default = re.search(r'=\s*(.+)$', piece.split(':')[-1] if typ else piece)
        if typ:
            is_string = bool(re.search(r'\bstring\b', typ))
        elif default:
            is_string = default.group(1).lstrip()[:1] in ("'", '"', "`")
        else:
            is_string = True
        out.append((name, is_string))
    return out


def definitions(src):
    """(이름, 매개변수 이름 목록, 본문 시작 위치) — 함수/메서드 정의만."""
    for match in DEF_HEAD.finditer(src):
        name = match.group('name') or match.group('name2')
        if name in SKIP_NAMES:
            continue
        open_paren = src.index('(', match.start() if match.group('name') else src.index('=', match.start()))
        close = param_list_end(src, open_paren)
        if close < 0:
            continue
        # 메서드/함수: `) : Type {` / 화살표: `) : Type => {` 둘 다 받는다
        # 반환 타입 뒤에 `=> {` 가 올 수 있으니 타입 부분에서 `=` 를 막으면 안 된다. 단 `=>` 의 `=` 만.
        tail = re.match(r'\)\s*(?::\s*(?:[^{;=]|=(?!>))+?)?\s*(?:=>\s*)?\{', src[close:close + 200])
        if not tail:
            continue            # 호출이거나 식 본문 화살표 — 정의가 아니다
        yield name, param_names(src, open_paren, close), close + tail.end() - 1


def var_uses(body, name):
    """변수로 쓰인 횟수. `opt.value` 의 속성 이름은 변수가 아니다."""
    return len(re.findall(r'(?<![.\w$])' + re.escape(name) + r'\b', body))


def body_of(src, start):
    depth = 0
    for i in range(start, len(src)):
        if src[i] == '{':
            depth += 1
        elif src[i] == '}':
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
    return src[start:]


# `for (const [값, 표시글] of 목록)` / `목록.forEach(([값, 표시글]) => ...)`
PAIR_LOOP = [
    re.compile(r'for\s*\(\s*const\s*\[\s*(?P<a>[\w$]+)\s*,\s*(?P<b>[\w$]+)\s*\]\s+of\s+(?P<src>[\w$.]+)'),
    re.compile(r'(?P<src>[\w$.]+)\.forEach\(\s*\(\s*\[\s*(?P<a>[\w$]+)\s*,\s*(?P<b>[\w$]+)\s*\]'),
]

# 기계 값이 가도 되는 자리 — 화면에 글자로 나오지 않는다.
MACHINE = re.compile(r'\.(?:value|id|htmlFor|className|name)\s*=\s*[^;]*\b%s\b|dataset\.[\w$]+\s*=\s*[^;]*\b%s\b')


def pair_consumer(body, param):
    """인자를 [값, 표시글] 짝으로 풀어 쓰는 도우미인가.

    표시글이 화면 자리로만 가고, 값이 기계 자리로만 가면 표시글을 옮겨도 안전하다.
    """
    for pattern in PAIR_LOOP:
        for match in pattern.finditer(body):
            if match.group('src').split('.')[-1] != param:
                continue
            first, second = match.group('a'), match.group('b')
            second_uses = var_uses(body, second) - 1
            second_display = len({
                m.start()
                for pattern2 in DISPLAY
                for m in re.finditer(pattern2.pattern % re.escape(second), body)
            })
            first_uses = var_uses(body, first) - 1
            first_machine = len(re.findall(MACHINE.pattern % (re.escape(first), re.escape(first)), body))
            if second_display >= second_uses and first_machine >= first_uses:
                return True
    return False


def main():
    root = pathlib.Path(sys.argv[1])
    verdicts = collections.defaultdict(list)
    for path in sorted(root.glob('*.ts')):
        src = path.read_text(encoding='utf-8')
        for name, params, brace in definitions(src):
            body = body_of(src, brace)
            # 모든 매개변수가 (a) 표시 자리로만 가거나 (b) 아예 안 쓰이거나 (c) 기계 자리로만 가야 한다.
            # 하나라도 비교·저장·계산에 쓰이면 그 도우미의 인자는 옮길 수 없다 — 둘째 인자까지
            # 옮기는 규칙이 생긴 뒤로는 첫 매개변수만 봐서는 안 된다.
            good = True
            total = display = 0
            string_params = [n for n, is_str in params if is_str]
            if not string_params:
                continue        # 문자열 인자가 없는 도우미 — 변환기가 건드릴 것이 없다
            for param in string_params:
                uses = [m.start() for m in re.finditer(r'(?<![.\w$])' + re.escape(param) + r'\b', body)]
                if not uses:
                    continue
                shown = len({
                    m.start()
                    for pattern in DISPLAY
                    for m in re.finditer(pattern.pattern % re.escape(param), body)
                })
                machine = len(re.findall(MACHINE.pattern % (re.escape(param), re.escape(param)), body))
                total += len(uses)
                display += shown
                if pair_consumer(body, param):
                    # [값, 표시글] 짝을 풀어 쓰는 소비자(selectOptions 등): 표시글이 표시 자리로만
                    # 가고 값은 기계 자리로만 간다는 것을 pair_consumer 가 확인했다. 표시 수에 더한다
                    # — 안 그러면 display==0 으로 걸려 '판정 무관' 이 되어 빠진다.
                    display += 1
                    continue
                if shown + machine < len(uses):
                    good = False
            if total == 0:
                continue        # 인자를 아예 안 쓰는 도우미 — 판정 대상 아님
            if display == 0:
                # 표시 자리가 하나도 없는 도우미(숫자 변환·clamp 등)는 '표시 전용' 이 아니라
                # '판정 무관' 이다. 목록에 넣으면 hwp16ToMm 같은 이름이 섞여 목록이 거짓이 된다.
                continue
            verdicts[name].append((path.name, good, total, display))

    # 판정은 파일별로 한다. `this.label(...)` 은 같은 파일의 정의를 부르므로,
    # 다른 파일의 같은 이름 때문에 멀쩡한 자리를 포기할 이유가 없다.
    ok, bad = [], []
    for name, entries in sorted(verdicts.items()):
        for filename, good, total, display in entries:
            (ok if good else bad).append((filename, name, total, display))

    print(f'표시 전용으로 판정된 (파일, 도우미) {len(ok)}쌍')
    names = sorted({name for _, name, _, _ in ok})
    print('  ' + ' '.join(names[:40]))
    print(f'\n표시 밖에서도 쓰는 것 {len(bad)}쌍 (건드리지 않는다)')
    for filename, name, total, display in bad[:10]:
        print(f'  {filename}: {name}  (사용 {total}회 중 표시 {display}회)')
    with open(sys.argv[2], 'w', encoding='utf-8') as f:
        for filename, name, _, _ in sorted(ok):
            f.write(f'{filename}\t{name}\n')
    print(f'\n{sys.argv[2]} 에 기록')


if __name__ == '__main__':
    main()
