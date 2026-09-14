#!/usr/bin/env python3
"""
TypeScript 원본에서 문자열 리터럴만 정확히 골라낸다.

주석과 정규식 리터럴을 문자열로 잘못 읽으면 번역이 코드를 망가뜨린다.
그래서 파서 대신 상태 기계를 쓴다 — 필요한 것은 '어디부터 어디까지가 문자열인가' 뿐이다.
"""
import re

KO = re.compile(r'[가-힣]')

# 이 뒤에 오는 '/' 는 나눗셈이 아니라 정규식의 시작이다.
REGEX_PRECEDERS = set('=(,:[!&|?{};+-*%~^<>') | {'return', 'typeof', 'case', 'in', 'of', 'new', 'delete', 'void'}


class Literal:
    __slots__ = ('quote', 'start', 'end', 'raw')

    def __init__(self, quote, start, end, raw):
        self.quote = quote      # ' " `
        self.start = start      # 따옴표 포함 시작 오프셋
        self.end = end          # 따옴표 포함 끝 오프셋(배타)
        self.raw = raw

    @property
    def body(self):
        return self.raw[1:-1]

    def __repr__(self):
        return f'Literal({self.quote}, {self.start}, {self.raw[:30]!r})'


def _regex_allowed(src, i):
    """위치 i 의 '/' 가 정규식 시작일 수 있는지 — 바로 앞 의미 있는 토큰으로 판단."""
    j = i - 1
    while j >= 0 and src[j] in ' \t\r\n':
        j -= 1
    if j < 0:
        return True
    ch = src[j]
    if ch in REGEX_PRECEDERS:
        return True
    # 낱말 뒤라면 그 낱말이 키워드일 때만 정규식이다.
    k = j
    while k >= 0 and (src[k].isalnum() or src[k] in '_$'):
        k -= 1
    word = src[k + 1:j + 1]
    return word in REGEX_PRECEDERS


def literals(src):
    """소스의 모든 문자열 리터럴을 순서대로 낸다. 주석·정규식은 건너뛴다."""
    out = []
    i, n = 0, len(src)
    while i < n:
        ch = src[i]
        if ch == '/' and i + 1 < n:
            nxt = src[i + 1]
            if nxt == '/':
                i = src.find('\n', i)
                if i == -1:
                    break
                continue
            if nxt == '*':
                end = src.find('*/', i + 2)
                i = n if end == -1 else end + 2
                continue
            if _regex_allowed(src, i):
                j = i + 1
                in_class = False
                while j < n:
                    c = src[j]
                    if c == '\\':
                        j += 2
                        continue
                    if c == '[':
                        in_class = True
                    elif c == ']':
                        in_class = False
                    elif c == '/' and not in_class:
                        break
                    elif c == '\n':
                        j = i  # 정규식이 아니었다
                        break
                    j += 1
                if j > i:
                    i = j + 1
                    continue
        if ch in ('"', "'", '`'):
            start = i
            j = i + 1
            depth = 0
            while j < n:
                c = src[j]
                if c == '\\':
                    j += 2
                    continue
                if ch == '`':
                    if c == '$' and j + 1 < n and src[j + 1] == '{':
                        depth += 1
                        j += 2
                        continue
                    if c == '}' and depth > 0:
                        depth -= 1
                        j += 1
                        continue
                    if c == '`' and depth == 0:
                        break
                else:
                    if c == ch:
                        break
                    if c == '\n':
                        break
                j += 1
            if j < n and src[j] == ch:
                out.append(Literal(ch, start, j + 1, src[start:j + 1]))
                i = j + 1
                continue
        i += 1
    return out


def korean_literals(src):
    return [lit for lit in literals(src) if KO.search(lit.raw)]
