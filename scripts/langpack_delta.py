"""
변경분 번역 왕복(xlsx 내보내기 → 사람이 번역 → 반영)의 공용 규칙.

정본은 셋이다.
  translations/ko-en.json   번역 메모리(원문 값 → 번역). 키가 바뀌어도 번역이 산다.
  translations/reviewed.json 사람이 확정한 (원문 → 번역). 변경분을 가르는 기준.
  translations/catalog/ko.json  지금 코드가 쓰는 키 → 원문. regenerate.sh 가 만든다.

'변경분' 은 지금 코드가 쓰는 원문 가운데
  ① 번역 메모리에 아직 없는 것(새로 생긴 문구, 상류가 문구를 바꾼 것), 또는
  ② 번역은 있지만 사람이 확정한 값과 다른 것(도구·AI 가 채운 것, 확정 뒤 바뀐 것)
이다. 이미 사람이 확정한 번역은 다시 묻지 않는다.

반영은 **병합만** 한다. 시트에 없는 원문은 절대 지우지 않는다 —
시트만 보고 메모리를 새로 짜면 30행짜리 시트가 번역 1,000개를 지운다.
"""
import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TRANSLATIONS = ROOT / 'translations'

# openpyxl 을 시스템에 깔 수 없는 환경을 위해 저장소 안 자리도 본다:
#   pip install --target work/pylib openpyxl
_local = ROOT / 'work' / 'pylib'
if _local.is_dir() and str(_local) not in sys.path:
    sys.path.insert(0, str(_local))

SHEET = '번역할 문구'
INFO_SHEET = '정보'
HEADERS = ['번호', '상태', '화면 위치', '원문(한국어)', '번역(영어) ← 여기에 입력',
           '현재 값', '키', '소스 파일', '주의', '원문 지문']
COL = {name: i for i, name in enumerate(HEADERS)}
C_STATE, C_PLACE, C_KO, C_EN, C_CURRENT, C_KEYS, C_FILES, C_NOTE, C_FP = (
    1, 2, 3, 4, 5, 6, 7, 8, 9)

STATE_NEW = '새 문구'
STATE_UNREVIEWED = '검토 필요'

# 엑셀 자동고침이 만든 글자 → 사람이 친 글자 (apply-review.py 와 같은 표)
AUTOCORRECT = {'©': '(C)', '®': '(R)', '™': '(TM)', '€': '(E)', '£': '(L)', '¥': '(Y)'}
PLACEHOLDER = re.compile(r'\{(\w+)\}')
ACCESS_KEY = re.compile(r'\(([A-Z0-9])\)\s*$')


def load_json(path, default=None):
    path = pathlib.Path(path)
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text(encoding='utf-8'))


def save_json(path, data):
    pathlib.Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def fingerprint(korean):
    """원문 지문. 검토자가 원문 칸을 실수로 고쳐도 어느 문구였는지 되찾는다."""
    return hashlib.sha1(korean.encode('utf-8')).hexdigest()[:12]


def fix_autocorrect(korean, english):
    fixed = english
    for wrong, right in AUTOCORRECT.items():
        fixed = fixed.replace(wrong, right)
    if '...' in korean and '…' in fixed:
        fixed = fixed.replace('…', '...')
    return fixed


def normalize_cell(value):
    """엑셀 칸의 값을 문자열로. 엑셀은 줄바꿈을 \\r\\n 으로 돌려주기도 한다."""
    if value is None:
        return ''
    return str(value).replace('\r\n', '\n').replace('\r', '\n')


def check_translation(korean, english):
    """반영하면 화면이 깨지는 번역을 가린다. (오류 목록, 경고 목록)을 낸다."""
    errors, warnings = [], []
    ko_ph = sorted(PLACEHOLDER.findall(korean))
    en_ph = sorted(PLACEHOLDER.findall(english))
    if ko_ph != en_ph:
        errors.append(f'자리표시자가 다르다: 원문 {ko_ph} / 번역 {en_ph} — 코드가 채우는 값이 사라진다')
    if korean.count('\n') != english.count('\n'):
        warnings.append(f'줄 수가 다르다(원문 {korean.count(chr(10)) + 1}줄, 번역 {english.count(chr(10)) + 1}줄)')
    if korean != korean.strip() and english == english.strip():
        warnings.append('원문의 앞뒤 공백이 번역에서 사라졌다 — 이어 붙는 글자와 붙어 보일 수 있다')
    return errors, warnings


def keep_access_key(korean, english):
    """원문 끝에 접근키 표시 `(X)` 가 있으면 번역에도 남긴다(8/21 검토에서 굳은 규칙)."""
    match = ACCESS_KEY.search(korean)
    if not match or ACCESS_KEY.search(english) or not english:
        return english
    return f'{english}({match.group(1)})'


def delta_values(ko_catalog, memory, reviewed):
    """변경분 원문 → 상태. 코드가 지금 쓰는 원문만 본다."""
    out = {}
    for korean in set(ko_catalog.values()):
        if korean not in memory:
            out[korean] = STATE_NEW
        elif reviewed.get(korean) != memory[korean]:
            out[korean] = STATE_UNREVIEWED
    return out
