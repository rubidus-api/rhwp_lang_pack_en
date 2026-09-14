# 재생성과 번역 반영 — 실행 방법

이 저장소는 rhwp-studio 에 영어 UI 를 입히는 변경을 **손으로 쓴 패치가 아니라 다시 만들 수 있는
변환**으로 들고 있다. 정본은 `translations/`(번역 데이터)와 `overlay/`(언어팩 런타임)와
`scripts/`(변환기)이고, 상류 트리에 들어가는 나머지는 전부 산출물이다.

상류가 움직이면 스크립트를 다시 돌려 같은 변경을 새 `devel` 위에 만든다.
손으로 고친 번역은 원문 값에 묶여 있어서 다시 만들어도 사라지지 않는다.

## 준비물

| 도구 | 쓰는 곳 |
|---|---|
| git, Node.js 24, npm | 상류 받기, rhwp-studio 테스트·빌드 |
| Python 3.11+ | 변환기·검사기 (표준 라이브러리만) |
| openpyxl (`pip install --user openpyxl`) | 번역 엑셀 내보내기·반영에만 |
| Rust + wasm-pack 0.15 | `verify-gates.sh` 의 빌드 관문에만 (상류 `rust-toolchain.toml` 이 버전을 정한다) |
| Chrome(puppeteer) | 브라우저 측정(`tools/e2e/`)에만 |

POSIX shell 기준이다(Linux 에서 확인).

## 1. 작업 사본 세우기

```sh
sh scripts/setup-work.sh              # edwardkim/rhwp 의 devel 최신
sh scripts/setup-work.sh 93ffc3dd5    # 또는 특정 상류 커밋에 고정 — 결과를 재현할 때
```

`work/rhwp` 에 상류를 받고, 트리를 그 커밋에 세우고(`tmp/full` 가지), 무회귀 검사 기준
(`work/index.baseline.html`, `work/ui.baseline/`)을 뜨고, `npm ci` 를 한다.
`work/` 는 이 저장소가 보관하지 않는다.

## 2. 한 번에 다시 만들기

```sh
sh scripts/regenerate.sh
```

순서는 늘 같다. **일부만 다시 돌리지 않는다** — 산출물을 부분적으로 다시 만들면 카탈로그를
덮어쓰는 사고가 난다.

| 단계 | 하는 일 |
|---|---|
| 0 | 대상 파일을 상류 원본으로 되돌리고 `overlay/` 를 얹는다 |
| 1 | 문자열을 받는 도우미 함수가 표시에만 쓰는지 **정의를 읽어** 판정한다 |
| 2 | 변환 4종: `index.html` 마크업 → `src/ui` 대화상자 → 모듈 최상위 표 → 명령 레지스트리 |
| 3 | 손 조정: main.ts 상태 표시줄, 머리말/꼬리말 표시, 레지스트리 재키잉, 영어 폭 CSS, `locale-init.js` 연결 |
| 4 | 번역 메모리로 `en` 카탈로그를 만들고 `src/i18n/locales/*.ts` 를 쓴다 |
| 5 | 테스트 파일을 그 단계에 맞는 상태로 만든다(`stage-tests.sh 4`) |

끝에 `regenerate: ok` 가 나오면 번역이 100% 다. 새 한국어 문구가 있으면 종료코드 2 로 멈추고
**번역할 것만 담은 엑셀**을 `review/` 에 만든다(아래 4).

손 조정 단계는 상류 코드가 기대와 다르면 **조용히 넘어가지 않고 멈춘다.** 상류가 그 코드를
고쳤다는 뜻이므로 `scripts/apply-extras.py` 의 해당 자리를 새 코드에 맞춰 고친다.

## 3. 검사

```sh
sh scripts/check-langpack.sh
```

- 마크업에서 `data-i18n*` 표시를 떼면 상류 `index.html` 과 바이트 단위로 같다
- 카탈로그 `ko` 값이 전부 상류 원본에 있다(한국어 화면 무회귀)
- 같은 요소에 번역과 한국어를 섞어 쓰는 코드가 없다(영어 화면에서 번역이 덮이는 결함)
- 비교식이 쓰는 문자열을 번역하지 않았다(생산자와 비교자의 짝)
- 모든 키에 영어가 있고, 한국어로 남긴 것은 `translations/keep-as-is.json` 에 이유가 있다

## 4. 새 문구가 생겼을 때 — 변경분 엑셀 왕복

### 이미 한 번역은 자동으로 찾는다

번역 메모리 `translations/ko-en.json` 은 **키가 아니라 원문 값**에 번역을 묶는다. 상류가 코드를
옮기거나 키가 바뀌어도, 같은 한국어 문구면 예전 번역이 그대로 들어간다. 사람에게 묻는 것은
처음 보는 문구와, 아직 사람이 확정하지 않은 번역뿐이다.

### 번역할 것만 엑셀로

```sh
python3 scripts/export-delta-xlsx.py          # review/delta-YYYYMMDD-HHMM.xlsx
python3 scripts/export-delta-xlsx.py --check  # 개수만 (변경분이 있으면 종료코드 3)
```

`regenerate.sh` 가 미번역을 만나면 이 명령을 알아서 돌린다. 엑셀에는 두 종류가 담긴다.

| 상태 | 뜻 |
|---|---|
| 새 문구 | 번역 메모리에 없는 한국어 — 새로 생겼거나 상류가 문구를 바꿨다 |
| 검토 필요 | 번역은 있지만 `translations/reviewed.json` 에 사람이 확정한 값과 다르다 |

한 행은 원문 한 개다. 같은 문구를 여러 자리가 쓰면 키와 화면 위치를 한 행에 모아 보여 준다.

### 엑셀에서 할 일

- 노란 **번역(영어)** 칸만 고친다. 지금 쓰이는 번역이 미리 들어 있으니 맞으면 그대로 둔다.
- 확정하지 않을 행은 번역 칸을 **비운다** — 다음 변경분에 다시 나온다.
- `{p1}` 같은 자리표시자는 코드가 채우는 값이라 번역에도 그대로 둔다.
- 원문 칸, 숨긴 '원문 지문' 열, 시트 이름은 건드리지 않는다.

### 번역본을 반영하기

```sh
sh scripts/apply-translations.sh review/delta-….xlsx
```

1. **검사만** 먼저 한다. 문제가 있는 행이 하나라도 있으면 아무것도 쓰지 않고 멈춘다.
2. 통과하면 `ko-en.json` 과 `reviewed.json` 에 **병합**한다. 시트에 없는 번역은 지우지 않는다.
3. `regenerate.sh` 로 코드까지 다시 만든다.
4. 남은 변경분 개수를 알려 준다.

반영 도구가 스스로 손보는 것과 거부하는 것:

| 경우 | 처리 |
|---|---|
| 엑셀 자동고침 `(C)`→`©`, `...`→`…` | 되돌린다 |
| 원문 끝의 접근키 `(X)` 가 번역에서 빠짐 | 붙인다 |
| 원문 칸이 실수로 고쳐짐 | 지문 열로 원래 원문을 찾는다 |
| 자리표시자가 원문과 다름 | **파일 전체 거부** — 화면에서 값이 사라진다 |
| 줄 수·앞뒤 공백이 다름 | 경고만 |

같은 원문이라도 자리마다 달라야 하는 번역(예: 머리말 배지의 `양쪽` = `Both pages`)은 값으로는
표현할 수 없으므로 `translations/ko-en-overrides.json` 에 **키**로 적는다.

## 5. 상류 제출용 단계 가지 만들기

```sh
sh scripts/build-stages.sh     # tmp/full → i18n/1-skeleton … i18n/4-commands
sh scripts/verify-gates.sh     # 단계마다 상류 CI 프론트 관문 + 빌드 경고 기준선 대조
```

| 가지 | 내용 |
|---|---|
| `i18n/1-skeleton` | `src/i18n` 런타임, `locale-init.js`, 상태 표시줄·머리말/꼬리말 표시 |
| `i18n/2-menus` | `index.html` 메뉴·툴바 표시, 영어 폭 CSS |
| `i18n/3-dialogs` | `src/ui` 대화상자 |
| `i18n/4-commands` | 명령 레지스트리 |

`build-stages.sh` 는 마지막에 **4단계 트리가 `regenerate.sh` 결과와 바이트 단위로 같은지** 확인한다.
커밋 메시지는 `docs/manual/stage-msgs/msg1..4.txt` 에서 읽는다.
`verify-gates.sh` 에는 새 WASM 이 필요하다: `(cd work/rhwp && sh scripts/wasm-pack-locked.sh --target web --dev)`.

## 6. 브라우저에서 한국어·영어 비교

```sh
cp tools/e2e/locale-parity.mjs work/rhwp/rhwp-studio/e2e/
cd work/rhwp/rhwp-studio
node e2e/run-with-vite.mjs -- node e2e/locale-parity.mjs --mode=headless
```

같은 문서를 한국어·영어로 열고 편집·저장·재열기해 쪽수와 저장 바이트를 비교하고,
창 폭 3가지 × 스킨 3가지에서 도구 모음이 잘리거나 가로로 넘치는지 잰다.
