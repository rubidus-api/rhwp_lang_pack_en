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


if __name__ == '__main__':
    unittest.main()
