"""
언어팩 일부가 이미 상류에 병합된 뒤에도 재생성이 같은 결과를 내는지 시험한다.

  - 마크업 변환: 이미 붙은 data-i18n 을 또 붙이지 않고 그 키를 쓴다
  - 대화상자 변환: 탭 라벨 키를 탭 ID 로 짓는다(dialog.<대화상자>.tab.<id>)
  - 카탈로그 심기: 상류 키가 빠지거나 값이 바뀌면 멈춘다

  python3 -m unittest tests/test_merged_upstream.py
"""
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / 'scripts'


def run(*args):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True)


class MarkupAlreadyMarked(unittest.TestCase):
    def test_existing_attribute_is_kept_not_duplicated(self):
        with tempfile.TemporaryDirectory() as d:
            html = pathlib.Path(d) / 'index.html'
            original = '<div id="x"><span class="md-label" data-i18n="ui.old.key">열기</span></div>\n'
            html.write_text(original, encoding='utf-8')
            done = run(SCRIPTS / 'apply-i18n-html.py', html, '--catalog', d, '--write')
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(html.read_text(encoding='utf-8'), original)
            self.assertEqual(json.loads((pathlib.Path(d) / 'ko.json').read_text(encoding='utf-8')), {'ui.old.key': '열기'})


class TabLabelKeys(unittest.TestCase):
    def test_tab_defs_and_label_records_use_tab_ids(self):
        with tempfile.TemporaryDirectory() as d:
            src = pathlib.Path(d) / 'src'
            ui = src / 'ui'
            (src / 'i18n').mkdir(parents=True)
            (src / 'i18n' / 'index.ts').write_text('export const t = (k: string) => k;\n', encoding='utf-8')
            ui.mkdir()
            (ui / 'sample-dialog.ts').write_text(
                "type TabId = 'basic' | 'glow';\n"
                "const TAB_LABELS: Record<TabId, string> = {\n"
                "  basic: '기본',\n"
                "  glow: '네온',\n"
                "};\n"
                "export class SampleDialog {\n"
                "  build(): void {\n"
                "    const tabDefs = [\n"
                "      { id: 'extended', label: '확장' },\n"
                "    ];\n"
                "    void tabDefs; void TAB_LABELS;\n"
                "  }\n"
                "}\n",
                encoding='utf-8',
            )
            catalog = pathlib.Path(d) / 'ko.json'
            catalog.write_text('{}\n', encoding='utf-8')
            done = run(SCRIPTS / 'apply-i18n-ts.py', ui, catalog, '--write')
            self.assertEqual(done.returncode, 0, done.stderr)
            got = json.loads(catalog.read_text(encoding='utf-8'))
            self.assertEqual(got.get('dialog.sample.tab.basic'), '기본', got)
            self.assertEqual(got.get('dialog.sample.tab.glow'), '네온', got)
            self.assertEqual(got.get('dialog.sample.tab.extended'), '확장', got)


class ExistingI18nImport(unittest.TestCase):
    def test_reuses_existing_alias(self):
        with tempfile.TemporaryDirectory() as d:
            src = pathlib.Path(d) / 'src'
            ui = src / 'ui'
            (src / 'i18n').mkdir(parents=True)
            (src / 'i18n' / 'index.ts').write_text('export const t = (k: string) => k;\n', encoding='utf-8')
            ui.mkdir()
            dialog = ui / 'alias-dialog.ts'
            dialog.write_text(
                "import { t as i18nText } from '../i18n/index.ts';\n"
                "export function build(t: number): void {\n"
                "  const tabDefs = [{ id: 'basic', label: '기본' }];\n"
                "  void tabDefs; void t; void i18nText;\n"
                "}\n",
                encoding='utf-8')
            catalog = pathlib.Path(d) / 'ko.json'
            catalog.write_text('{}\n', encoding='utf-8')
            done = run(SCRIPTS / 'apply-i18n-ts.py', ui, catalog, '--write')
            self.assertEqual(done.returncode, 0, done.stderr)
            got = dialog.read_text(encoding='utf-8')
            self.assertIn("label: i18nText('dialog.alias.tab.basic')", got)
            self.assertEqual(got.count('i18n/index.ts'), 1)


class CommandFactoryLabels(unittest.TestCase):
    def test_only_label_argument_of_command_factory(self):
        with tempfile.TemporaryDirectory() as d:
            src = pathlib.Path(d) / 'src'
            commands = src / 'command' / 'commands'
            (src / 'i18n').mkdir(parents=True)
            (src / 'i18n' / 'index.ts').write_text('export const t = (k: string) => k;\n', encoding='utf-8')
            commands.mkdir(parents=True)
            f = commands / 'insert.ts'
            f.write_text(
                "function stub(id: string, label: string, icon?: string): CommandDef {\n"
                "  return {\n    id,\n    label,\n    icon,\n  };\n}\n"
                "function named(id: string, label: string): CommandDef {\n"
                "  return { id, label: label, execute() { record(label); } };\n}\n"
                "export const commands = [\n"
                "  stub('insert:caption-top', '캡션 - 위', 'icon-a'),\n"
                "  named('insert:x', '기록 이름'),\n"
                "  run(() => {}, '되돌리기 이름'),\n"
                "];\n",
                encoding='utf-8')
            catalog = pathlib.Path(d) / 'ko.json'
            catalog.write_text('{"command.insert.captionTop.label": "위"}\n', encoding='utf-8')
            done = run(SCRIPTS / 'apply-i18n-ts.py', commands, catalog, '--write')
            self.assertEqual(done.returncode, 0, done.stderr)
            got = f.read_text(encoding='utf-8')
            self.assertIn("stub('insert:caption-top', t('dialog.insert.captionTop.registryLabel'), 'icon-a')", got)
            # label 을 표시 밖(record)에서도 쓰는 공장, 공장이 아닌 호출의 한글은 그대로
            self.assertIn("named('insert:x', '기록 이름')", got)
            self.assertIn("'되돌리기 이름'", got)


class PairArrayLabels(unittest.TestCase):
    """[값, 표시글] 짝 배열은 표시글만 옮기고, 값을 비교에도 쓰면 통째로 건드리지 않는다."""

    def convert(self, source):
        with tempfile.TemporaryDirectory() as d:
            src = pathlib.Path(d) / 'src'
            ui = src / 'ui'
            (src / 'i18n').mkdir(parents=True)
            (src / 'i18n' / 'index.ts').write_text('export const t = (k: string) => k;\n', encoding='utf-8')
            ui.mkdir()
            f = ui / 'sample-dialog.ts'
            f.write_text(source, encoding='utf-8')
            catalog = pathlib.Path(d) / 'ko.json'
            catalog.write_text('{}\n', encoding='utf-8')
            done = run(SCRIPTS / 'apply-i18n-ts.py', ui, catalog, '--write')
            self.assertEqual(done.returncode, 0, done.stderr)
            return f.read_text(encoding='utf-8')

    def test_display_slot_only(self):
        got = self.convert(
            "export function build(): void {\n"
            "  for (const [val, lbl] of [['0', '선 없음']] as const) {\n"
            "    const o = document.createElement('option');\n"
            "    o.value = val; o.textContent = lbl;\n"
            "  }\n"
            "}\n")
        self.assertIn("['0', t(", got)
        self.assertNotIn("'선 없음'", got)

    def test_named_tuple_array_through_variable(self):
        got = self.convert(
            "export function build(): void {\n"
            "  const presets: [string, string][] = [['\u25a1', '상자형']];\n"
            "  for (const [icon, title] of presets) {\n"
            "    const b = document.createElement('button');\n"
            "    b.textContent = icon; b.title = title;\n"
            "  }\n"
            "}\n")
        self.assertNotIn("'상자형'", got)

    def test_value_compared_elsewhere_is_left_alone(self):
        got = self.convert(
            "export function build(): void {\n"
            "  for (const [key, name] of [['a', '이름표']] as const) {\n"
            "    if (name === '이름표') document.body.dataset.x = key;\n"
            "  }\n"
            "}\n")
        self.assertIn("'이름표'", got)
        self.assertNotIn("t('", got)


class MarkupAssertionsAlreadyPatched(unittest.TestCase):
    def test_second_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            test = pathlib.Path(d) / 'shell.test.ts'
            test.write_text(
                "assert.match(html, /<h1 class=\"visually-hidden\">제목<\\/h1>/);\n"
                "assert.match(html, /<nav id=\"menu-bar\" aria-label=\"주 메뉴\">/);\n",
                encoding='utf-8')
            for _ in range(2):
                done = run(SCRIPTS / 'patch-markup-assertions.py', d, '--write')
                self.assertEqual(done.returncode, 0, done.stderr)
            got = test.read_text(encoding='utf-8')
            self.assertIn('class="visually-hidden"[^>]*>제목', got)
            self.assertIn('aria-label="주 메뉴"[^>]*>', got)
            self.assertNotIn('[^[^', got)


class RegistryRekeyIdempotent(unittest.TestCase):
    """이미 registryLabel 키인 명령을 다시 돌려도 이름이 바뀌지 않는다(바뀌면 카탈로그에서 지워졌다)."""

    def renames(self, source, catalog):
        spec = importlib.util.spec_from_file_location('apply_extras', SCRIPTS / 'apply-extras.py')
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as d:
            studio = pathlib.Path(d)
            (studio / 'src/command/commands').mkdir(parents=True)
            (studio / 'src/command/commands/insert.ts').write_text(source, encoding='utf-8')
            return mod.registry_renames(studio, catalog)

    def test_registry_label_key_stays(self):
        got = self.renames(
            "export const commands = [\n"
            "  { id: 'insert:caption-top', label: t('command.insert.captionTop.registryLabel') },\n"
            "];\n",
            {'command.insert.captionTop.registryLabel': '캡션 - 위', 'command.insert.captionTop.label': '위'})
        self.assertEqual(got, {})

    def test_markup_key_is_reused_when_text_matches(self):
        got = self.renames(
            "export const commands = [\n"
            "  { id: 'file:open', label: t('dialog.file.open.label') },\n"
            "];\n",
            {'dialog.file.open.label': '열기', 'command.file.open.label': '열기'})
        self.assertEqual(got, {'dialog.file.open.label': 'command.file.open.label'})


class SeedCheck(unittest.TestCase):
    def check(self, ko, seed):
        with tempfile.TemporaryDirectory() as d:
            k, s = pathlib.Path(d) / 'ko.json', pathlib.Path(d) / 'seed.json'
            k.write_text(json.dumps(ko), encoding='utf-8')
            s.write_text(json.dumps(seed), encoding='utf-8')
            return run(SCRIPTS / 'seed-catalog.py', '--check', k, s)

    def test_kept_passes(self):
        self.assertEqual(self.check({'a': '가', 'b': '나'}, {'a': '가'}).returncode, 0)

    def test_lost_or_changed_fails(self):
        self.assertNotEqual(self.check({'b': '나'}, {'a': '가'}).returncode, 0)
        self.assertNotEqual(self.check({'a': '다'}, {'a': '가'}).returncode, 0)


if __name__ == '__main__':
    unittest.main()
