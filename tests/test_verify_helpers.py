"""
도우미 판정(verify-helpers.py)이 공유 모듈로 뺀 도우미를 따라가는지 시험한다.

상류가 문단 모양 대화상자의 createFieldset·label 을 para-shape-helpers.ts 로 빼자
`export function` 정의도, 그것을 import 한 파일도 판정에서 빠져 대화상자 전체가 한국어로 남았다.

  python3 -m unittest tests/test_verify_helpers.py
"""
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / 'scripts' / 'verify-helpers.py'


class VerifyHelpers(unittest.TestCase):
    def verdicts(self, files):
        with tempfile.TemporaryDirectory() as d:
            ui = pathlib.Path(d) / 'ui'
            ui.mkdir()
            for name, src in files.items():
                (ui / name).write_text(src, encoding='utf-8')
            out = pathlib.Path(d) / 'helpers.tsv'
            done = subprocess.run([sys.executable, str(SCRIPT), str(ui), str(out)], capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            return {tuple(line.split('\t')) for line in out.read_text(encoding='utf-8').splitlines()}

    def test_exported_helper_and_its_importers(self):
        got = self.verdicts({
            'shared.ts': (
                "export function label(text: string): HTMLSpanElement {\n"
                "  const l = document.createElement('span');\n"
                "  l.textContent = text;\n"
                "  return l;\n"
                "}\n"
                "export function keyed(key: string): HTMLSpanElement {\n"
                "  const l = document.createElement('span');\n"
                "  if (key === '가') l.className = 'x';\n"
                "  l.textContent = key;\n"
                "  return l;\n"
                "}\n"
            ),
            'dialog-a.ts': "import { label, keyed } from './shared';\nconst a = label('왼쪽');\n",
            'dialog-b.ts': "import { label as caption } from './shared.ts';\nconst b = caption('오른쪽');\n",
        })
        self.assertIn(('shared.ts', 'label'), got)
        self.assertIn(('dialog-a.ts', 'label'), got)
        self.assertIn(('dialog-b.ts', 'caption'), got)
        # 비교에 쓰는 도우미는 가져온 파일에서도 표시 전용이 아니다
        self.assertNotIn(('shared.ts', 'keyed'), got)
        self.assertNotIn(('dialog-a.ts', 'keyed'), got)

    def test_local_definition_wins_over_import(self):
        got = self.verdicts({
            'shared.ts': "export function label(text: string) {\n  const l = document.createElement('span');\n  l.textContent = text;\n  return l;\n}\n",
            'dialog.ts': (
                "import { label } from './shared';\n"
                "function label(text: string) {\n  if (text === '가') return 1;\n  el.textContent = text;\n}\n"
            ),
        })
        self.assertNotIn(('dialog.ts', 'label'), got)


    def test_name_inside_a_string_is_not_a_use(self):
        # `--color-text` 의 text 를 매개변수 사용으로 세면 표시 전용 도우미가 탈락한다(2026-09-16).
        got = self.verdicts({'dialog-a.ts': (
            "function label(text: string): HTMLSpanElement {\n"
            "  const span = document.createElement('span');\n"
            "  span.textContent = text;\n"
            "  span.style.cssText = 'color:var(--color-text);';\n"
            "  return span;\n"
            "}\n"
            "const a = label('왼쪽');\n")})
        self.assertIn(('dialog-a.ts', 'label'), got)

    def test_existence_guard_is_not_a_non_display_use(self):
        got = self.verdicts({'dialog-b.ts': (
            "function row(labelText: string, unitText?: string): HTMLDivElement {\n"
            "  const d = document.createElement('div');\n"
            "  d.textContent = labelText;\n"
            "  if (unitText) {\n"
            "    const u = document.createElement('span');\n"
            "    u.textContent = unitText;\n"
            "    d.appendChild(u);\n"
            "  }\n"
            "  return d;\n"
            "}\n"
            "const b = row('간격', 'mm');\n")})
        self.assertIn(('dialog-b.ts', 'row'), got)

    def test_use_inside_template_interpolation_still_counts(self):
        got = self.verdicts({'dialog-c.ts': (
            "function checkbox(text: string): HTMLLabelElement {\n"
            "  const lb = document.createElement('label');\n"
            "  lb.appendChild(document.createTextNode(` ${text}`));\n"
            "  return lb;\n"
            "}\n"
            "const c = checkbox('가나');\n")})
        self.assertIn(('dialog-c.ts', 'checkbox'), got)


    def test_generic_helper_definition_is_read(self):
        # `radioGroup<T extends string>(` 처럼 제네릭이 붙으면 정의를 못 읽어 인자가 통째로 빠졌다.
        got = self.verdicts({'dialog-d.ts': (
            "function radioGroup<T extends string>(\n"
            "  title: string,\n"
            "  options: [T, string][],\n"
            "  current: T,\n"
            "): HTMLElement {\n"
            "  const fs = document.createElement('fieldset');\n"
            "  fs.textContent = title;\n"
            "  for (const [value, labelText] of options) {\n"
            "    const input = document.createElement('input');\n"
            "    input.value = value;\n"
            "    input.checked = value === current;\n"
            "    fs.appendChild(document.createTextNode(labelText));\n"
            "  }\n"
            "  return fs;\n"
            "}\n"
            "const d = radioGroup('격자 모양', [['dots', '점']], 'dots');\n")})
        self.assertIn(('dialog-d.ts', 'radioGroup'), got)

    def test_compared_argument_is_still_rejected(self):
        # 비교는 짝 배열의 값 자리에서만 봐준다. 일반 인자를 비교하면 그 값이 로직이다.
        got = self.verdicts({'dialog-e.ts': (
            "function mark(kind: string): HTMLElement {\n"
            "  const s = document.createElement('span');\n"
            "  s.textContent = kind;\n"
            "  if (kind === '경고') s.className = 'warn';\n"
            "  return s;\n"
            "}\n"
            "const e = mark('경고');\n")})
        self.assertNotIn(('dialog-e.ts', 'mark'), got)

if __name__ == '__main__':
    unittest.main()
