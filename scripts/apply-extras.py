#!/usr/bin/env python3
"""
변환기가 못 다루는 '손 조정' 네 가지를 한 곳에 모아 재생성 때마다 같은 결과가 나오게 한다.

  1. main.ts — 상태바·머리말/꼬리말·최근문서를 런타임에 한국어로 다시 쓰던 5곳을 t() 로
  2. 레지스트리 라벨 — 마크업이 같은 명령에 이미 만든 키(command.<grp>.<id>.label)를 재사용
  3. style-bar.css — html[lang='en'] 에만 글꼴 언어 선택 폭 보정
  4. index.html — locale-init.js 연결(번들 전 <html lang>)

이 파일이 없으면 사람이 매번 기억해서 다시 해야 하고, 그러다 빠뜨린 적이 있다.
"""
import json
import pathlib
import re
import sys


def slug(text):
    parts = [p for p in re.split(r'[^A-Za-z0-9]+', text) if p]
    return parts[0][:1].lower() + parts[0][1:] + ''.join(p[:1].upper() + p[1:] for p in parts[1:]) if parts else 'x'


def main():
    studio = pathlib.Path(sys.argv[1])
    catalog_path = pathlib.Path(sys.argv[2])
    ko = json.load(open(catalog_path, encoding='utf-8'))
    report = []

    # 1. main.ts
    p = studio / 'src/main.ts'
    s = p.read_text(encoding='utf-8')
    pairs = [
        ("document.getElementById('sb-mode')!.textContent = (insertMode as boolean) ? '삽입' : '수정';",
         "document.getElementById('sb-mode')!.textContent = (insertMode as boolean) ? t('ui.sbMode.label') : t('ui.sbMode.label.overwrite');"),
        # 상태 표시줄 메시지 — 파일 이름·쪽수와 편집 모드
        ("sbMessage().textContent = mode === 'form' ? '양식 모드' : '기본 편집 모드';",
         "sbMessage().textContent = mode === 'form' ? t('ui.sbMessage.formMode') : t('ui.sbMessage.editMode');"),
        ("sbMessage().textContent = `${wasm.fileName} — ${wasm.pageCount}페이지`;",
         "sbMessage().textContent = t('ui.sbMessage.filePages', { p1: wasm.fileName, p2: wasm.pageCount });"),
        ("await initializeDocument(docInfo, `${fileName} — ${docInfo.pageCount}페이지 (${elapsed.toFixed(1)}ms)`, {",
         "await initializeDocument(docInfo, t('ui.sbMessage.filePagesTimed', { p1: fileName, p2: docInfo.pageCount, p3: elapsed.toFixed(1) }), {"),
        ("await initializeDocument(docInfo, `새 문서.hwp — ${docInfo.pageCount}페이지`);",
         "await initializeDocument(docInfo, t('ui.sbMessage.newDocPages', { p1: docInfo.pageCount }));"),
        # 머리말/꼬리말 편집 표시 — 상류 #7000대에서 '종류 · 대상 편집 중' 과 화면낭독기 문구로 다시 쓰였다
        ("const kind = state === 'none' ? '' : state.mode === 'header' ? '머리말' : '꼬리말';",
         "const kind = state === 'none' ? '' : state.mode === 'header' ? t('ui.tbHfLabel.header') : t('ui.tbHfLabel.footer');"),
        ("hfLabel.textContent = state === 'none' ? '' : `${kind} · ${target} 편집 중`;",
         "hfLabel.textContent = state === 'none' ? '' : t('ui.tbHfLabel.editing', { p1: kind, p2: target });"),
        ("? '머리말 꼬리말 편집 종료'",
         "? t('ui.hfLiveStatus.ended')"),
        (": `${kind} ${target} 편집 중, 구역 ${state.sectionIdx + 1} 첫 페이지`;",
         ": t('ui.hfLiveStatus.editing', { p1: kind, p2: target, p3: state.sectionIdx + 1 });"),
        ("frag.append(makeItem({ label: '(최근 문서 없음)', disabled: true }));",
         "frag.append(makeItem({ label: t('menu.file.label.x46b91c'), disabled: true }));"),
        ("sbSection().textContent = `구역: ${pageInfo.sectionIndex + 1} / ${totalSections}`;",
         "sbSection().textContent = t('ui.sbSection.text', { p1: pageInfo.sectionIndex + 1, p2: totalSections });"),
        ("sbSection().textContent = `구역: 1 / ${totalSections}`;",
         "sbSection().textContent = t('ui.sbSection.text', { p1: 1, p2: totalSections });"),
    ]
    n = 0
    for old, new in pairs:
        # 못 찾으면 멈춘다. 조용히 지나가면 상류가 그 코드를 고친 순간 번역이 사라진다
        # (2026-09-14 머리말/꼬리말 표시가 그렇게 빠졌다 — LESSONS '단정 없는 치환').
        if s.count(old) != 1:
            raise SystemExit(f'apply-extras: main.ts 에서 기대한 코드가 {s.count(old)}번 나온다(1번이어야 함) — 상류가 바꿨다:\n  {old}')
        s = s.replace(old, new); n += 1
    if "import { initI18n } from '@/i18n/index.ts';" in s:
        s = s.replace("import { initI18n } from '@/i18n/index.ts';", "import { initI18n, t } from '@/i18n/index.ts';")
    elif "from '@/i18n/index.ts'" not in s:
        # 1단계 연결도 없으면 넣는다
        anchor = "import { DocumentAgentController } from '@/document-agent/controller';"
        s = s.replace(anchor, anchor + "\nimport { initI18n, t } from '@/i18n/index.ts';", 1)
        s = s.replace("const wasm = new WasmBridge();",
                      "// 언어팩 초기화 — 정적 마크업의 라벨을 결정된 로케일로 갱신한다. 카탈로그에 없는 키는\n// 원문(ko)으로 물러나므로 번역이 없는 상태에서도 화면은 도입 전과 같다.\ninitI18n();\n\nconst wasm = new WasmBridge();", 1)
    p.write_text(s, encoding='utf-8')
    ko.update({'ui.sbMode.label.overwrite': '수정', 'ui.tbHfLabel.header': '머리말',
               'ui.tbHfLabel.footer': '꼬리말', 'ui.sbSection.text': '구역: {p1} / {p2}',
               'ui.tbHfLabel.editing': '{p1} · {p2} 편집 중',
               'ui.hfLiveStatus.ended': '머리말 꼬리말 편집 종료',
               'ui.hfLiveStatus.editing': '{p1} {p2} 편집 중, 구역 {p3} 첫 페이지',
               'ui.hfApplyTo.even': '짝수 쪽', 'ui.hfApplyTo.odd': '홀수 쪽', 'ui.hfApplyTo.both': '양쪽',
               'ui.sbMessage.formMode': '양식 모드', 'ui.sbMessage.editMode': '기본 편집 모드',
               'ui.sbMessage.filePages': '{p1} — {p2}페이지', 'ui.sbMessage.filePagesTimed': '{p1} — {p2}페이지 ({p3}ms)',
               'ui.sbMessage.newDocPages': '새 문서.hwp — {p1}페이지'})
    report.append(f'main.ts {n}곳')

    # 1b. 머리말/꼬리말 표시를 함께 쓰는 엔진 도우미와 캔버스 배지.
    # 한쪽만 옮기면 영어 화면에 'Footer(짝수 쪽)' 처럼 섞인다. 상대 경로 import — 순수 node 테스트가 직접 읽는다.
    extra_files = {
        'src/engine/header-footer-mode.ts': (
            ("import type { CursorState } from './cursor';",
             "import type { CursorState } from './cursor';\nimport { t } from '../i18n/index.ts';"),
            ("if (applyTo === 1) return '짝수 쪽';", "if (applyTo === 1) return t('ui.hfApplyTo.even');"),
            ("if (applyTo === 2) return '홀수 쪽';", "if (applyTo === 2) return t('ui.hfApplyTo.odd');"),
            ("  return '양쪽';\n}", "  return t('ui.hfApplyTo.both');\n}"),
        ),
        'src/view/canvas-view.ts': (
            ("} from '@/engine/header-footer-mode.ts';",
             "} from '@/engine/header-footer-mode.ts';\nimport { t } from '../i18n/index.ts';"),
            ("const kind = state.mode === 'header' ? '머리말' : '꼬리말';",
             "const kind = state.mode === 'header' ? t('ui.tbHfLabel.header') : t('ui.tbHfLabel.footer');"),
        ),
    }
    for rel, file_pairs in extra_files.items():
        fp = studio / rel
        text = fp.read_text(encoding='utf-8')
        for old, new in file_pairs:
            if text.count(old) != 1:
                raise SystemExit(f'apply-extras: {rel} 에서 기대한 코드가 {text.count(old)}번 나온다(1번이어야 함):\n  {old}')
            text = text.replace(old, new)
        fp.write_text(text, encoding='utf-8')
    report.append('머리말/꼬리말 표시 2파일')

    # 2. 레지스트리 라벨 재키잉
    renames = {}
    for f in sorted((studio / 'src/command/commands').glob('*.ts')):
        src = f.read_text(encoding='utf-8')
        for m in re.finditer(r"id:\s*'([a-z]+):([a-z0-9-]+)'[\s\S]*?label:\s*t\('([^']+)'\)", src):
            grp, cid, old = m.groups()
            if src[m.start():m.end()].count("id: '") > 1:
                continue
            markup = f'command.{slug(grp)}.{slug(cid)}.label'
            if old == markup:
                continue
            if markup in ko and ko[markup] == ko.get(old):
                renames[old] = markup
            else:
                renames[old] = f'command.{slug(grp)}.{slug(cid)}.registryLabel'
    for f in sorted((studio / 'src/command/commands').glob('*.ts')):
        src = f.read_text(encoding='utf-8'); orig = src
        for old, new in renames.items():
            src = src.replace(f"t('{old}')", f"t('{new}')")
        # dialog.<file>.* 로 들어간 command 키는 command.<file>.* 로
        for k in [k for k in ko if re.match(r'dialog\.(file|edit|format|insert|page|table|tool|view)\.', k)]:
            src = src.replace(f"'{k}'", f"'command.{k[len('dialog.'):]}'")
        if src != orig:
            f.write_text(src, encoding='utf-8')
    for old, new in renames.items():
        if old in ko:
            ko.setdefault(new, ko[old]); del ko[old]
    for k in [k for k in list(ko) if re.match(r'dialog\.(file|edit|format|insert|page|table|tool|view)\.', k)]:
        ko['command.' + k[len('dialog.'):]] = ko.pop(k)
    reused = sum(1 for v in renames.values() if v.endswith('.label'))
    report.append(f'레지스트리 재키잉 {len(renames)}(마크업 키 재사용 {reused})')

    # 3. CSS — 영어 라벨이 넓어 잘리는 자리. 보정은 html[lang='en'] 에만 건다(한국어 화면은 1px 도 안 바뀐다).
    # 서식 도구 모음은 격자라 칸 폭이 선택 상자 폭을 정한다. 요소 폭(.sb-font-lang)만 넓히면
    # 격자 칸(64px)에 막혀 'Font S' 로 잘린다(2026-09-14 화면으로 확인). 칸을 넓힌다.
    p = studio / 'src/styles/style-bar.css'
    s = p.read_text(encoding='utf-8')
    anchor = ".sb-font-lang { width: 64px; font-size: var(--font-size-sm); }"
    grid_ko = """  grid-template-columns:
    minmax(68px, 88px)
    minmax(54px, 64px)
    136px
    minmax(72px, 86px)
    minmax(72px, 86px);
  gap: 4px;
  width: min(476px, 100%);"""
    ribbon_ko = """  .sb-field-grid {
    grid-template-columns: 88px 64px 136px 86px 86px;
    width: 100%;
  }"""
    marker = "html[lang='en'] .sb-field-grid"
    if marker not in s:
        for needle, what in ((anchor, '.sb-font-lang 규칙'), (grid_ko, '서식 도구 격자 열'), (ribbon_ko, '리본 격자 열'),
                             ("flex: 0 0 481px;", '리본 묶음 폭')):
            if s.count(needle) != 1:
                raise SystemExit(f'apply-extras: style-bar.css 의 {what}이 바뀌었다 — 영어 폭 보정을 다시 볼 것')
        s = s.rstrip('\n') + """

/* ── 언어팩: 영어 라벨 폭 보정 ──────────────────────────────────────────────
   글꼴 적용 언어 상자의 영어 값(Font Set·Japanese)은 한국어(대표·일어)보다 20px 가량 넓다.
   격자 둘째 칸이 상자 폭을 정하므로 그 칸만 넓힌다. html[lang='en'] 에만 걸어 한국어 배치는 그대로다. */
html[lang='en'] .sb-field-grid {
  grid-template-columns:
    minmax(68px, 88px)
    minmax(74px, 84px)
    136px
    minmax(72px, 86px)
    minmax(72px, 86px);
  width: min(496px, 100%);
}
@media (max-width: 459px) {
  html[lang='en'] .sb-field-grid {
    grid-template-columns:
      minmax(54px, 1fr)
      minmax(40px, 0.75fr)
      136px
      minmax(54px, 0.95fr)
      minmax(54px, 0.95fr);
  }
}
@media (min-width: 808px) {
  html[lang='en'] .sb-field-ribbon-group {
    flex-basis: 501px;
    width: 501px;
    min-width: 501px;
  }
  html[lang='en'] .sb-field-grid {
    grid-template-columns: 88px 84px 136px 86px 86px;
  }
}
"""
        p.write_text(s, encoding='utf-8')
        report.append('css 보정')

    # 3b. 상태 표시줄 — 쪽 표시(page-indicator)와 파일·쪽수·편집 모드 메시지. 문서가 열려 있는 동안 늘 보인다.
    status_files = {
        'src/view/page-indicator.ts': (
            ("/** 상태 표시줄 문자열 (`1 / 33 쪽`) */",
             "import { t } from '../i18n/index.ts';\n\n/** 상태 표시줄 문자열 (`1 / 33 쪽`) */"),
            ("return `${currentPageLabel(input)} / ${input.totalPages} 쪽`;",
             "return t('ui.sbPage.text', { p1: currentPageLabel(input), p2: input.totalPages });"),
        ),
    }
    for rel, file_pairs in status_files.items():
        fp = studio / rel
        text = fp.read_text(encoding='utf-8')
        for old, new in file_pairs:
            if text.count(old) != 1:
                raise SystemExit(f'apply-extras: {rel} 에서 기대한 코드가 {text.count(old)}번 나온다(1번이어야 함):\n  {old}')
            text = text.replace(old, new)
        fp.write_text(text, encoding='utf-8')
    ko.update({'ui.sbPage.text': '{p1} / {p2} 쪽'})
    report.append('쪽 표시')

    # 4a. 브라우저 확장 빌드 — vite publicDir:false 라 public/ 파일을 직접 복사한다. locale-init.js 를
    # 빠뜨리면 확장 viewer.html 이 없는 스크립트를 가리킨다(상류 메인테이너가 PR #7142 에서 보정, 0308b476b).
    repo = studio.parent
    theme_copy = "copy(resolve(ROOT, 'rhwp-studio', 'public', 'theme-init.js'), resolve(DIST, 'theme-init.js'));\n"
    locale_copy = ("// 언어 선택도 번들 전 동기 실행한다(publicDir:false이므로 직접 포함).\n"
                   "copy(resolve(ROOT, 'rhwp-studio', 'public', 'locale-init.js'), resolve(DIST, 'locale-init.js'));\n")
    ext_pairs = {
        'rhwp-chrome/build.mjs': ((theme_copy, theme_copy + locale_copy),
                                  ("  'theme-init.js',\n", "  'theme-init.js',\n  'locale-init.js',\n")),
        'rhwp-firefox/build.mjs': ((theme_copy, theme_copy + locale_copy),
                                   ("  'theme-init.js',\n", "  'theme-init.js',\n  'locale-init.js',\n")),
        'scripts/frontend-extension-dist.test.mjs': ((
            "    assertInlineScriptDetectorRejectsMalformedEndTags();\n\n",
            "    assertInlineScriptDetectorRejectsMalformedEndTags();\n\n"
            "    assert.match(viewerHtml, /<script\\s+src=\"(?:\\.\\/|\\/)?locale-init\\.js\"><\\/script>/);\n"
            "    assert.equal(\n"
            "      readFileSync(path.join(distDir, 'locale-init.js'), 'utf8'),\n"
            "      readFileSync(path.join(ROOT, 'rhwp-studio/public/locale-init.js'), 'utf8'),\n"
            "      'locale bootstrap must be copied unchanged into each extension',\n"
            "    );\n\n"),),
    }
    for rel, file_pairs in ext_pairs.items():
        fp = repo / rel
        text = fp.read_text(encoding='utf-8')
        if 'locale-init.js' in text:
            continue
        for old, new in file_pairs:
            if text.count(old) != 1:
                raise SystemExit(f'apply-extras: {rel} 에서 기대한 코드가 {text.count(old)}번 나온다(1번이어야 함):\n  {old}')
            text = text.replace(old, new)
        fp.write_text(text, encoding='utf-8')
    report.append('확장 빌드 locale-init 3파일')

    # 4. locale-init
    p = studio / 'index.html'
    s = p.read_text(encoding='utf-8')
    anchor = '  <script src="/theme-init.js"></script>\n'
    if '/locale-init.js' not in s:
        if anchor not in s:
            raise SystemExit('apply-extras: index.html 의 theme-init 스크립트 줄이 바뀌었다 — locale-init 자리를 다시 볼 것')
        s = s.replace(anchor, anchor + '  <!-- 언어팩: 번들 전에 <html lang> 을 고른 로케일로 — 영어 사용자의 첫 페인트 깜빡임 방지 -->\n  <script src="/locale-init.js"></script>\n', 1)
        p.write_text(s, encoding='utf-8')
        report.append('locale-init 연결')

    json.dump(ko, open(catalog_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2, sort_keys=True)
    open(catalog_path, 'a').write('\n')
    print('apply-extras: ' + ', '.join(report) + f' → 카탈로그 {len(ko)}')


if __name__ == '__main__':
    main()
