"""
소스 단정 재조준(retarget-source-assertions.py)은 원래 단정이 아직 통과하면 건드리지 않는다.

3단계(명령 소스는 그대로)에서 `id: '…'[\\s\\S]*?label: '…'` 단정이 쓸데없이 약한 꼴로 바뀌었고,
'문구가 어딘가 있나' 로 고치자 4단계에서 같은 문구가 다른 문자열 속에 남아 테스트 2개가 깨졌다.

  python3 -m unittest tests/test_retarget_assertions.py
"""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / 'scripts' / 'retarget-source-assertions.py'

TEST = """import { readFileSync } from 'node:fs';
import { join } from 'node:path';
const source = readFileSync(join(rootDir, 'src/table.ts'), 'utf8');
assert.match(source, /id: 'table:copy'[\\s\\S]*?label: '행 복사'/);
assert.doesNotMatch(source, /update\\(100, '완료'\\)/);
"""


class RetargetAssertions(unittest.TestCase):
    def run_on(self, table_src):
        with tempfile.TemporaryDirectory() as d:
            studio = pathlib.Path(d)
            (studio / 'src').mkdir()
            (studio / 'tests').mkdir()
            (studio / 'src' / 'table.ts').write_text(table_src, encoding='utf-8')
            test = studio / 'tests' / 'table.test.ts'
            test.write_text(TEST, encoding='utf-8')
            catalog = studio / 'ko.json'
            catalog.write_text(json.dumps({'command.table.copy.label': '행 복사', 'x.done': '완료'}, ensure_ascii=False), encoding='utf-8')
            done = subprocess.run([sys.executable, str(SCRIPT), str(studio / 'tests'), str(catalog), '--write'],
                                  capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            return test.read_text(encoding='utf-8')

    def test_untouched_source_keeps_original_assertions(self):
        out = self.run_on("{ id: 'table:copy', label: '행 복사' }\nupdate(50, '완료');\n")
        self.assertEqual(out, TEST)

    def test_same_text_elsewhere_does_not_keep_a_failing_assertion(self):
        # 라벨은 키로 옮겨졌지만 같은 문구가 툴팁 문자열에 남았다 — 원래 match 는 이제 실패하므로 옮겨야 한다
        out = self.run_on("{ id: 'table:copy', label: t('command.table.copy.label'), tip: '행 복사 (Ctrl+C)' }\n")
        self.assertIn("assertShowsText(source, '행 복사')", out)
        self.assertIn("assert.doesNotMatch(source, /update\\(100, '완료'\\)/);", out)


if __name__ == '__main__':
    unittest.main()
