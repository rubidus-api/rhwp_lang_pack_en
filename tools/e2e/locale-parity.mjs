/**
 * 한국어·영어 UI 에서 같은 문서가 같은 결과를 내는지, 그리고 영어 UI 가 좁은 창·스킨에서
 * 잘리지 않는지 잰다 (이슈 #5852 검토 ②).
 *
 * rhwp-studio/e2e/ 에 복사해 상류 헬퍼로 돌린다:
 *   cp tools/e2e/locale-parity.mjs work/rhwp/rhwp-studio/e2e/
 *   cd work/rhwp/rhwp-studio && node e2e/run-with-vite.mjs -- node e2e/locale-parity.mjs --mode=headless
 * 결과는 표준 출력의 JSON 한 덩어리(LOCALE_PARITY_JSON 줄)다.
 *
 * 가르려는 질문
 *   A. 문서 조판이 언어에 따라 달라지나 — 샘플 열기·편집·저장·재열기의 쪽수와 저장 바이트
 *   B. 편집 결과가 달라진다면 원인이 UI 기하(편집 영역 크기·맞춤 배율·클릭 위치)인가
 *   C. 좁은 창과 스킨별로 UI 가 잘리거나 가로로 넘치나
 */
import { createHash } from 'node:crypto';
import {
  launchBrowser, createPage, closeBrowser, loadApp, createNewDocument, loadHwpFile,
  clickEditArea, typeText, getPageCount, getParagraphCount, getCursorPosition,
} from './helpers.mjs';

const SAMPLE = 'biz_plan.hwp';
const SKINS = ['default', 'flat', 'oldschool'];
const VIEWPORTS = [
  { width: 1280, height: 900 },
  { width: 1024, height: 700 },
  { width: 800, height: 600 },
];

const sha = (bytes) => createHash('sha256').update(Buffer.from(bytes)).digest('hex').slice(0, 16);

async function prepare(page, { locale, skin = 'default' }) {
  await page.evaluateOnNewDocument((loc, sk) => {
    try {
      localStorage.clear();
      localStorage.setItem('rhwp-locale', loc);
      localStorage.setItem('rhwp-settings', JSON.stringify({ theme: { mode: 'light', skin: sk, skinChosen: true } }));
    } catch { /* 저장소가 막힌 환경 */ }
  }, locale, skin);
  await loadApp(page);
}

async function geometry(page) {
  return page.evaluate(() => {
    const rect = (sel) => {
      const el = document.querySelector(sel);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { top: Math.round(r.top), height: Math.round(r.height), width: Math.round(r.width) };
    };
    const zoom = window.__canvasView?.viewportManager?.getZoom?.() ?? null;
    return {
      lang: document.documentElement.lang,
      menuBar: rect('#menu-bar'),
      iconToolbar: rect('#icon-toolbar'),
      styleBar: rect('#style-bar'),
      scrollContainer: rect('#scroll-container'),
      zoom,
    };
  });
}

async function clipping(page) {
  return page.evaluate(() => {
    const visible = (el) => {
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none';
    };
    // 글자가 자기 상자보다 넓어 잘리는 단추·라벨. 넘침을 의도한 스크롤 트랙 자체는 뺀다.
    const candidates = document.querySelectorAll(
      '#menu-bar [data-i18n], #icon-toolbar [data-i18n], #icon-toolbar [data-i18n-lines], #style-bar [data-i18n], #style-bar select, #status-bar [data-i18n], #status-bar span');
    const clipped = [];
    for (const el of candidates) {
      if (!visible(el)) continue;
      const cs = getComputedStyle(el);
      const hides = cs.overflow === 'hidden' || cs.overflowX === 'hidden' || cs.textOverflow === 'ellipsis';
      if (el.scrollWidth > el.clientWidth + 1 && (hides || el.tagName === 'SELECT')) {
        clipped.push({ id: el.id || null, key: el.getAttribute('data-i18n') || el.getAttribute('data-i18n-lines') || null,
          text: (el.textContent || '').trim().slice(0, 40), scrollWidth: el.scrollWidth, clientWidth: el.clientWidth });
      }
    }
    return {
      pageOverflowX: document.documentElement.scrollWidth > window.innerWidth + 1,
      clipped,
    };
  });
}

async function exportBytes(page) {
  return page.evaluate(() => Array.from(window.__wasm.exportHwp()));
}

async function reopen(page, bytes) {
  return page.evaluate(async (arr) => {
    const info = window.__wasm.loadDocument(new Uint8Array(arr), 'reopen.hwp');
    await window.__canvasView?.loadDocument?.();
    return { pageCount: info.pageCount, bytes: Array.from(window.__wasm.exportHwp()) };
  }, bytes);
}

/** A. 샘플 문서: 열기 → 쪽수·저장 바이트 */
async function sampleRun(browser, locale) {
  const page = await createPage(browser, 1280, 900);
  await prepare(page, { locale });
  const loaded = await loadHwpFile(page, SAMPLE);
  const bytes = await exportBytes(page);
  const again = await reopen(page, bytes);
  const result = {
    geometry: await geometry(page),
    pageCountOnOpen: loaded.pageCount,
    exportHash: sha(bytes),
    reopenPageCount: again.pageCount,
    reopenExportHash: sha(again.bytes),
  };
  await page.close();
  return result;
}

/** B. text-flow 와 같은 키보드 편집 — UI 기하가 끼어드는 경로 */
async function keyboardRun(browser, locale, viewport) {
  const page = await createPage(browser, viewport.width, viewport.height);
  await prepare(page, { locale });
  await createNewDocument(page);
  const geo = await geometry(page);
  await clickEditArea(page);
  const cursorAfterClick = await getCursorPosition(page);
  await typeText(page, 'Hello World');
  for (let i = 0; i < 5; i++) await typeText(page, 'The quick brown fox jumps over the lazy dog. ');
  await page.keyboard.press('Enter');
  for (let i = 0; i < 40; i++) {
    await typeText(page, `Line ${i + 1}`);
    await page.keyboard.press('Enter');
  }
  await page.evaluate(() => new Promise((r) => setTimeout(r, 1000)));
  const bytes = await exportBytes(page);
  const again = await reopen(page, bytes);
  const result = {
    viewport,
    geometry: geo,
    cursorAfterClick,
    pageCount: await getPageCount(page),
    paragraphCount: await getParagraphCount(page),
    exportHash: sha(bytes),
    reopenPageCount: again.pageCount,
  };
  await page.close();
  return result;
}

/** B'. 같은 편집을 UI 를 거치지 않고 문서 API 로 — 조판만 보는 경로 */
async function apiRun(browser, locale) {
  const page = await createPage(browser, 1280, 900);
  await prepare(page, { locale });
  await createNewDocument(page);
  const out = await page.evaluate(() => {
    const w = window.__wasm;
    let para = 0;
    let text = 'Hello World';
    for (let i = 0; i < 5; i++) text += 'The quick brown fox jumps over the lazy dog. ';
    w.insertText(0, para, 0, text);
    for (let i = 0; i < 40; i++) {
      const len = w.getTextRange(0, para, 0, 100000).length;
      w.splitParagraph(0, para, len);
      para += 1;
      w.insertText(0, para, 0, `Line ${i + 1}`);
    }
    return { pageCount: w.pageCount, paragraphCount: w.getParagraphCount(0), bytes: Array.from(w.exportHwp()) };
  });
  await page.close();
  return { pageCount: out.pageCount, paragraphCount: out.paragraphCount, exportHash: sha(out.bytes) };
}

/** C. 좁은 창·스킨별 잘림 */
async function layoutRun(browser, locale, skin, viewport) {
  const page = await createPage(browser, viewport.width, viewport.height);
  await prepare(page, { locale, skin });
  await createNewDocument(page);
  const result = { locale, skin, viewport, geometry: await geometry(page), ...(await clipping(page)) };
  await page.close();
  return result;
}

const browser = await launchBrowser();
const report = { sample: {}, keyboard: [], api: {}, layout: [] };
try {
  for (const locale of ['ko', 'en']) {
    report.sample[locale] = await sampleRun(browser, locale);
    report.api[locale] = await apiRun(browser, locale);
    for (const viewport of VIEWPORTS.slice(0, 2)) {
      report.keyboard.push({ locale, ...(await keyboardRun(browser, locale, viewport)) });
    }
    for (const skin of SKINS) {
      for (const viewport of VIEWPORTS) {
        report.layout.push(await layoutRun(browser, locale, skin, viewport));
      }
    }
  }
} finally {
  await closeBrowser(browser);
}
console.log('LOCALE_PARITY_JSON ' + JSON.stringify(report));
