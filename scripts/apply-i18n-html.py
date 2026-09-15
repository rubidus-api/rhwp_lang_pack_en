#!/usr/bin/env python3
"""
정적 마크업(index.html)에 언어팩 표시를 붙이고 ko 카탈로그를 뽑는다.

정본은 이 스크립트다. 상류가 움직이면 손으로 diff 를 고치는 대신 이 스크립트를
최신 파일에 다시 돌린다(RFC-0001 §2 P2).

규칙
  - 요소의 직계 한글 텍스트              → data-i18n           (직계 텍스트 노드만 치환)
  - <br> 로만 나뉜 한글 텍스트           → data-i18n-lines     (줄로 나눠 텍스트+<br> 재구성)
  - 한글이 든 title/aria-label/value/placeholder → data-i18n-<속성>

키
  - [data-cmd="file:open"] 안이면            command.file.open.<역할>
  - [data-menu="file"] 의 .menu-title 이면    menu.file
  - 그 밖에는 가장 가까운 id 를 써서          ui.<id>.<역할><n>
"""
import hashlib
import json
import re
import sys
from html.parser import HTMLParser

KO = re.compile(r'[가-힣]')
ATTR_TARGETS = ('title', 'aria-label', 'value', 'placeholder')
VOID = {'br', 'img', 'input', 'hr', 'meta', 'link', 'source', 'area', 'base', 'col'}

ROLE_BY_CLASS = {
    'md-label': 'label',            # 메뉴 항목 이름
    'tb-label': 'toolbarLabel',     # 툴바 버튼의 두 줄 라벨
    'tb-split-item': 'splitLabel',  # 툴바 분할 버튼의 목록 항목
    'sb-dropdown-item': 'label',    # 서식 막대 드롭다운 항목
    'sb-ribbon-label': 'ribbonLabel',
    'sb-field-label': 'fieldLabel',
    'stb-item': 'label',
    'tb-hf-label': 'toolbarLabel',
    'tb-note-label': 'toolbarLabel',
    'menu-title': None,             # 메뉴 이름에는 역할 마디를 붙이지 않는다
    'sb-ga': 'sample',              # 글꼴 효과 미리보기 글자
    'visually-hidden': 'srLabel',
}


def slug(text: str) -> str:
    """임의 문자열을 키 마디로. 영숫자만 남기고 camelCase 로 잇는다."""
    parts = re.split(r'[^A-Za-z0-9]+', text)
    parts = [p for p in parts if p]
    if not parts:
        return 'x'
    head, *rest = parts
    return head[:1].lower() + head[1:] + ''.join(p[:1].upper() + p[1:] for p in rest)


class Element:
    __slots__ = ('tag', 'attrs', 'line', 'col', 'raw', 'children', 'texts', 'brs')

    def __init__(self, tag, attrs, line, col, raw):
        self.tag = tag
        self.attrs = dict(attrs)
        self.line = line
        self.col = col
        self.raw = raw
        self.children = 0      # <br> 을 제외한 자식 요소 수
        self.texts = []        # 직계 텍스트 조각
        self.brs = 0


class Collector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.found = []        # (Element, ancestors) — 한글 텍스트를 가진 요소
        self.attr_hits = []    # (Element, ancestors, attr_name)

    def handle_starttag(self, tag, attrs):
        raw = self.get_starttag_text()
        line, col = self.getpos()
        el = Element(tag, attrs, line, col, raw)
        if self.stack:
            parent = self.stack[-1]
            if tag == 'br':
                parent.brs += 1
            else:
                parent.children += 1
        for name in ATTR_TARGETS:
            value = el.attrs.get(name)
            if not value or not KO.search(value):
                continue
            # <option value="바탕"> 의 value 는 화면 글자가 아니라 앱이 실제로 쓰는 값이다.
            # 여기를 옮기면 글꼴 선택이 영어 화면에서만 조용히 깨진다.
            if tag == 'option' and name == 'value':
                continue
            self.attr_hits.append((el, list(self.stack), name))
        if tag not in VOID:
            self.stack.append(el)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.stack and self.stack[-1].tag == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i].tag == tag:
                el = self.stack[i]
                ancestors = self.stack[:i]
                if any(KO.search(t) for t in el.texts):
                    self.found.append((el, list(ancestors)))
                del self.stack[i:]
                return

    def handle_data(self, data):
        if self.stack:
            self.stack[-1].texts.append(data)


def ancestor_context(el, ancestors):
    chain = ancestors + [el]
    cmd = menu = anchor_id = None
    for node in chain:
        if node.attrs.get('data-cmd'):
            cmd = node.attrs['data-cmd']
        if node.attrs.get('data-menu'):
            menu = node.attrs['data-menu']
        if node.attrs.get('id'):
            anchor_id = node.attrs['id']
    return cmd, menu, anchor_id


def role_of(el, ancestors):
    """요소의 역할. 자기 class 에 없으면 조상에서 물려받는다(<b> 로 강조된 라벨 등)."""
    for node in [el] + list(reversed(ancestors)):
        for cls in (node.attrs.get('class') or '').split():
            if cls in ROLE_BY_CLASS:
                return ROLE_BY_CLASS[cls]
    if el.tag == 'option':
        return 'option'
    return 'text'


def icon_mark(el, ancestors):
    """형제 아이콘 class(icon-footer 등)를 구분자로 쓴다. 마크업이 이미 가진 이름이다."""
    parent = ancestors[-1] if ancestors else None
    if parent is None:
        return None
    for cls in (parent.attrs.get('class') or '').split():
        if cls.startswith('icon-'):
            return slug(cls[len('icon-'):])
    return None


def text_mark(value):
    """구분자가 아무것도 없을 때 원문에서 뽑는 짧은 지문.

    번호(label2, label3…)는 상류가 순서를 바꾸면 번역이 조용히 다른 항목에 붙는다.
    지문은 순서에 흔들리지 않고, 원문이 바뀌면 키도 바뀌어 번역이 자동으로 무효가 된다.
    """
    return 'x' + hashlib.blake2s(value.strip().encode('utf-8'), digest_size=3).hexdigest()


def discriminators(el):
    """같은 data-cmd 를 여러 요소가 나눠 쓸 때 서로를 가르는 data-* 값.

    번호(label2, label3…)로 가르면 상류가 순서를 바꿀 때 번역이 조용히 어긋난다.
    마크업이 이미 갖고 있는 구분자를 쓰면 순서가 바뀌어도 키가 따라간다.
    """
    out = []
    for name in sorted(el.attrs):
        if not name.startswith('data-') or name in ('data-cmd', 'data-menu'):
            continue
        value = el.attrs[name] or ''
        base = slug(name[len('data-'):])
        if value == 'true':
            out.append(base)
        elif value == 'false':
            out.append(base + 'No')
        else:
            out.append(base + slug(value)[:1].upper() + slug(value)[1:])
    return out


def key_stem(el, ancestors, kind):
    """구분자까지 반영한 키의 몸통. 같은 몸통이 둘 이상이면 지문으로 가른다."""
    cmd, menu, anchor_id = ancestor_context(el, ancestors)
    role = 'tooltip' if kind == 'title' else slug(kind)
    if kind == 'text':
        role = role_of(el, ancestors) or ''

    if cmd:
        base = 'command.' + '.'.join(slug(p) for p in cmd.split(':'))
        marks = []
        for node in list(ancestors) + [el]:
            if node.attrs.get('data-cmd') == cmd:
                marks = discriminators(node)
        if marks:
            base = base + '.' + '.'.join(marks)
    elif menu:
        base = f'menu.{slug(menu)}'
    elif anchor_id:
        base = f'ui.{slug(anchor_id)}'
    else:
        base = 'ui'

    if el.tag == 'option' and el.attrs.get('value') is not None:
        key = f'{base}.option.{slug(el.attrs["value"]) or "empty"}'
    else:
        key = f'{base}.{role}' if role else base
    return key


def element_lines(el):
    """<br> 로 나뉜 줄 목록. 텍스트 조각은 순서대로 들어 있다."""
    return [t for t in el.texts]


def main():
    path = sys.argv[1]
    write = '--write' in sys.argv
    out_dir = None
    if '--catalog' in sys.argv:
        out_dir = sys.argv[sys.argv.index('--catalog') + 1]

    src = open(path, encoding='utf-8').read()
    lines = src.splitlines(keepends=True)
    offsets = []
    total = 0
    for line in lines:
        offsets.append(total)
        total += len(line)

    def abs_pos(el):
        return offsets[el.line - 1] + el.col

    collector = Collector()
    collector.feed(src)

    # 1패스: 후보를 모은다 (요소, 조상, 종류, 값, 붙일 속성 이름)
    candidates = []
    for el, ancestors in collector.found:
        joined = ''.join(el.texts)
        if not KO.search(joined):
            continue
        # 글꼴 이름 목록(<select id="font-name">)의 <option> 은 라벨도 옮기지 않는다.
        # 값=라벨=실제 글꼴 이름이고(README '글꼴 이름은 옮기지 않는다'), 툴바가 문서를 열 때
        # 목록을 원문 이름으로 다시 만들므로 마크업 번역은 어차피 첫 문서에서 사라진다.
        if el.tag == 'option' and any(a.attrs.get('id') == 'font-name' for a in ancestors):
            continue
        if el.brs > 0:
            pieces = [t for t in el.texts if t.strip()]
            value = '\n'.join(p.strip() for p in pieces)
            candidates.append((el, ancestors, 'text', value, 'data-i18n-lines'))
        else:
            # 자식 요소가 섞여 있으면 직계 텍스트 노드만 값이 된다(런타임도 그렇게 바꾼다).
            meaningful = [t for t in el.texts if t.strip()]
            value = meaningful[0] if el.children > 0 and meaningful else joined
            candidates.append((el, ancestors, 'text', value, 'data-i18n'))
    for el, ancestors, name in collector.attr_hits:
        candidates.append((el, ancestors, name, el.attrs[name], f'data-i18n-{name}'))

    # 2패스: 몸통이 겹치는 후보는 전부 지문을 붙인다.
    # 첫 하나만 맨 몸통을 갖게 하면 상류가 순서를 바꿀 때 그 몸통이 다른 글에 옮겨 붙는다.
    stems = [key_stem(el, anc, kind) for el, anc, kind, _, _ in candidates]
    crowded = {stem for stem in stems if stems.count(stem) > 1}

    edits = []
    catalog = {}
    for (el, ancestors, kind, value, attr_name), stem in zip(candidates, stems):
        if stem in crowded:
            mark = icon_mark(el, ancestors) or text_mark(value)
            key = f'{stem}.{mark}'
        else:
            key = stem
        existing = el.attrs.get(attr_name)
        if existing:
            # 상류에 이미 들어간 표시(2단계 병합 뒤): 붙어 있는 키를 그대로 쓰고 속성을 또 붙이지 않는다.
            # 다시 계산한 키가 다르면 알린다 — 상류 키가 정본이다.
            if existing != key:
                print(f'  알림: 기존 키 유지 {existing} (다시 계산하면 {key})')
            if catalog.get(existing, value) != value:
                print(f'  경고: 키 충돌 {existing}: {catalog[existing]!r} vs {value!r}')
            catalog[existing] = value
            continue
        previous = catalog.get(key)
        if previous is not None and previous != value:
            print(f'  경고: 키 충돌 {key}: {previous!r} vs {value!r}')
        catalog[key] = value
        pos = abs_pos(el) + len(el.raw) - 1
        attr = f' {attr_name}="{key}"'
        if el.raw.endswith('/>'):
            # `<input … value="10.0" />` 는 `/` 앞 공백 **앞에** 속성을 끼운다:
            # `value="10.0" data-i18n-title="…" />`. 원본 공백을 지우거나 새로 넣으면 표시를 뗀 뒤
            # 원본과 바이트가 달라진다(check-noregress 가 잡는다).
            pos -= 1
            while pos > 0 and src[pos - 1] == ' ':
                pos -= 1
        edits.append((pos, attr))

    skipped = []

    print(f'키 {len(catalog)}개, 편집 {len(edits)}곳, 건너뜀 {len(skipped)}곳')
    if skipped:
        print('-- 자식 요소가 섞여 건드리지 않은 곳 --')
        for tag, cls, text in skipped[:20]:
            print(f'   <{tag} class="{cls}">  {text}')

    if out_dir:
        with open(f'{out_dir}/ko.json', 'w', encoding='utf-8') as f:
            json.dump(catalog, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write('\n')
        print(f'카탈로그: {out_dir}/ko.json')

    if write:
        result = src
        for pos, attr in sorted(edits, reverse=True):
            result = result[:pos] + attr + result[pos:]
        open(path, 'w', encoding='utf-8').write(result)
        print(f'적용: {path}')


if __name__ == '__main__':
    main()
