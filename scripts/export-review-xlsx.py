#!/usr/bin/env python3
"""
번역 검토용 엑셀을 만든다.

사람이 한 줄씩 읽고 고칠 수 있어야 하므로, 키만 늘어놓지 않고
**그 문구가 화면 어디에 나오는지**를 소스에서 찾아 함께 적는다.

열: 순서 | 구분 | 화면 위치 | 원문 | 번역 | 키 | 비고 | 검토 의견
"""
import json
import pathlib
import re
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

AREA_ORDER = {'menu': 0, 'command': 1, 'ui': 2, 'option': 3, 'dialog': 4}
AREA_NAME = {
    'menu': '메뉴 막대',
    'command': '메뉴 항목·툴바',
    'ui': '화면 요소',
    'option': '드롭다운 목록',
    'dialog': '대화상자',
}
# 명령으로도 원본으로도 이름이 안 잡히는 대화상자 — 화면에 보이는 이름을 적는다.
EXTRA_TITLES = {
    'compare': '문서 비교',
    'compareResult': '문서 비교 상세',
    'commandPalette': '명령 검색',
    'equationEditor': '수식 편집',
    'history': '문서 이력 관리',
    'paraShapeTabBuilders': '문단 모양 — 탭 설정',
    'dialog': '공용 대화상자 골격',
    'fontSet': '대표 글꼴',
    'localFonts': '로컬 글꼴 감지',
    'skinOnboarding': '화면 스킨 선택',
    'hwpPassword': '문서 암호',
    'saveAs': '다른 이름으로 저장',
    'printPdfGuide': 'PDF로 저장 안내',
    'hmlImportWarning': 'HML 가져오기 경고',
    'hwpxNonstandard': 'HWPX 비표준 감지',
    'chartData': '차트 데이터 편집',
    'dropConfirm': '로컬 파일 열기 확인',
    'recovery': '복구',
    'toast': '알림',
    'styleBar': '서식 도구 모음',
    'equationProps': '수식 속성',
    'fontSetEdit': '대표 글꼴 편집',
    'shapePicker': '도형 고르기',
    'styleEdit': '스타일 편집',
    'toolbar': '툴바',
}

ROLE_NAME = {
    'label': '항목 이름',
    'toolbarLabel': '툴바 라벨',
    'splitLabel': '분할 버튼 항목',
    'tooltip': '툴팁',
    'title': '제목',
    'text': '본문',
    'message': '메시지',
    'placeholder': '입력 안내',
    'ariaLabel': '보조기술 이름',
    'value': '입력값',
    'sample': '미리보기 글자',
    'fieldLabel': '항목 라벨',
    'ribbonLabel': '묶음 이름',
    'option': '목록 항목',
    'srLabel': '화면낭독기 문구',
}


def find_uses(root, keys):
    """키가 실제로 쓰인 파일을 찾는다. 맥락 열의 근거가 된다."""
    uses = {}
    targets = list(root.glob('index.html')) + sorted(root.glob('src/**/*.ts'))
    pattern = re.compile(r"['\"]([a-zA-Z][\w.]*)['\"]")
    for path in targets:
        if '/i18n/locales/' in str(path):
            continue
        text = path.read_text(encoding='utf-8')
        for match in pattern.finditer(text):
            key = match.group(1)
            if key in keys:
                uses.setdefault(key, set()).add(path.name)
        for match in re.finditer(r'data-i18n(?:-[a-z-]+)?="([^"]+)"', text):
            uses.setdefault(match.group(1), set()).add(path.name)
    return uses


def stem_of(filename):
    stem = filename[:-3] if filename.endswith('.ts') else filename
    for suffix in ('-dialog', '-window'):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    parts = [p for p in re.split(r'[^A-Za-z0-9]+', stem) if p]
    if not parts:
        return stem
    head, *rest = parts
    return head[:1].lower() + head[1:] + ''.join(p[:1].upper() + p[1:] for p in rest)


def dialog_titles(catalog, baseline_dir):
    """대화상자의 한국어 이름. 키에서 못 찾으면 옮기기 전 소스의 super('제목') 에서 뽑는다.

    검토자는 'bookmark' 가 아니라 '책갈피' 로 찾는다.
    """
    titles = {}
    for key, value in catalog.items():
        parts = key.split('.')
        if len(parts) >= 3 and parts[0] == 'dialog' and parts[2] == 'title':
            titles.setdefault(parts[1], value)
    # 대화상자 stem 은 그 대화상자를 여는 명령의 이름과 같다
    # (charShape ↔ command.format.charShape). 그 연결로 이름을 얻는다.
    for key, value in catalog.items():
        parts = key.split('.')
        if parts[0] == 'command' and len(parts) >= 4 and parts[3] == 'label':
            titles.setdefault(parts[2], value)

    if baseline_dir and baseline_dir.is_dir():
        for path in sorted(baseline_dir.glob('*.ts')):
            stem = stem_of(path.name)
            if stem in titles:
                continue
            match = re.search(r"super\(\s*'([^']*[가-힣][^']*)'", path.read_text(encoding='utf-8'))
            if match:
                titles[stem] = match.group(1)
    return titles


def where(key, catalog, titles, uses):
    parts = key.split('.')
    area = parts[0]
    role = parts[-1] if parts[-1] in ROLE_NAME else (parts[-2] if len(parts) > 1 and parts[-2] in ROLE_NAME else '')
    files = ', '.join(sorted(uses.get(key, ()))) or '—'

    if area == 'menu':
        name = catalog.get(f'menu.{parts[1]}', parts[1]) if len(parts) > 1 else ''
        return f'메뉴 「{name}」', ROLE_NAME.get(role, ''), files
    if area == 'command':
        command = ':'.join(parts[1:3]) if len(parts) > 2 else '.'.join(parts[1:])
        return f'명령 {command}', ROLE_NAME.get(role, ''), files
    if area == 'dialog':
        stem = parts[1] if len(parts) > 1 else ''
        title = titles.get(stem) or EXTRA_TITLES.get(stem)
        label = f'대화상자 「{title}」' if title else f'대화상자 {stem}'
        return label, ROLE_NAME.get(role, ''), files
    if area == 'option':
        return f'목록 {parts[1] if len(parts) > 1 else ""}', ROLE_NAME.get(role, '목록 항목'), files
    if area == 'ui':
        return f'화면 요소 {parts[1] if len(parts) > 1 else ""}', ROLE_NAME.get(role, ''), files
    return key, '', files


def main():
    root = pathlib.Path(sys.argv[1])
    out_path = sys.argv[2]
    # 카탈로그 JSON 은 이 저장소가 갖는다(상류 트리에는 .ts 만 간다).
    catalog = pathlib.Path(__file__).resolve().parent.parent / 'translations' / 'catalog'
    ko = json.load(open(catalog / 'ko.json', encoding='utf-8'))
    en = json.load(open(catalog / 'en.json', encoding='utf-8'))
    keep_path = catalog.parent / 'keep-as-is.json'
    keep = json.load(open(keep_path, encoding='utf-8')) if keep_path.exists() else {}
    keep_values, keep_keys = keep.get('values', {}), keep.get('keys', {})
    overrides_path = catalog.parent / 'ko-en-overrides.json'
    overrides = json.load(open(overrides_path, encoding='utf-8')) if overrides_path.exists() else {}

    baseline = pathlib.Path(sys.argv[3]) if len(sys.argv) > 3 else None
    uses = find_uses(root, set(ko))
    titles = dialog_titles(ko, baseline)

    rows = []
    for key in ko:
        area = key.split('.')[0]
        place, role, files = where(key, ko, titles, uses)
        note = ''
        if key in keep_keys:
            note = '한국어로 둠 — ' + keep_keys[key]
        elif ko[key] in keep_values:
            note = '한국어로 둠 — ' + keep_values[ko[key]]
        elif key in overrides:
            note = '이 자리만 다르게 — 같은 원문의 다른 자리는 ' + repr(en.get(key, ''))
        elif '{p' in ko[key]:
            note = '{p1} 은 코드가 채우는 값 — 번역에도 그대로 있어야 한다'
        rows.append((AREA_ORDER.get(area, 9), place, role, ko[key], en.get(key, ''), key, note, files))

    rows.sort(key=lambda r: (r[0], r[1], r[5]))

    wb = Workbook()
    ws = wb.active
    ws.title = '번역 검토'
    headers = ['순서', '구분', '화면 위치', '역할', '원문(한국어)', '번역(영어)',
               '키', '소스 파일', '비고', '검토 의견']
    ws.append(headers)

    for index, (order, place, role, korean, english, key, note, files) in enumerate(rows, start=1):
        ws.append([index, AREA_NAME.get(key.split('.')[0], key.split('.')[0]),
                   place, role, korean, english, key, files, note, ''])

    head_fill = PatternFill('solid', fgColor='DDE5F0')
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = head_fill
        cell.alignment = Alignment(vertical='center')
    widths = [6, 14, 26, 14, 46, 46, 40, 26, 34, 24]
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical='top', wrap_text=True)
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = f'A1:J{ws.max_row}'

    # 요약 시트 — 무엇을 얼마나 옮겼는지 한눈에
    summary = wb.create_sheet('요약')
    counts = {}
    for _, _, _, _, _, key, _, _ in rows:
        area = key.split('.')[0]
        counts[area] = counts.get(area, 0) + 1
    summary.append(['구분', '개수', '설명'])
    for area, count in sorted(counts.items(), key=lambda kv: AREA_ORDER.get(kv[0], 9)):
        summary.append([AREA_NAME.get(area, area), count, ''])
    summary.append(['합계', len(rows), '영어 100% 채움'])
    for cell in summary[1]:
        cell.font = Font(bold=True)
        cell.fill = head_fill
    summary.column_dimensions['A'].width = 18
    summary.column_dimensions['B'].width = 10
    summary.column_dimensions['C'].width = 40

    wb.save(out_path)
    print(f'{out_path}: {len(rows)}행')


if __name__ == '__main__':
    main()
