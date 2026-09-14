# rhwp Language Pack

[rhwp](https://github.com/edwardkim/rhwp) 편집기(rhwp-studio)의 UI 문자열을 로케일로 분리하고
영어 표시를 더하는 변경을, **다시 만들 수 있는 변환**으로 들고 있는 저장소다.
상류 논의: [edwardkim/rhwp#5852](https://github.com/edwardkim/rhwp/issues/5852).

A reproducible transform that adds an English UI to rhwp-studio. Instead of a hand-written patch,
it keeps translation data and converters, and regenerates the change on top of the latest upstream `devel`.

## 무엇이 들어 있나

```text
translations/   번역 정본 — 원문 값 → 영어(ko-en.json), 자리별 예외, 한국어로 두는 것과 그 이유,
                사람이 확정한 번역(reviewed.json)
overlay/        언어팩 런타임 — rhwp-studio/src/i18n, public/locale-init.js, i18n 테스트
scripts/        변환기·검사기·단계 가지 생성·번역 엑셀 왕복
tools/e2e/      한국어·영어 화면 비교 측정
docs/           실행 방법
```

## 빠른 시작

```sh
sh scripts/setup-work.sh     # work/rhwp 에 상류 devel 을 받고 기준을 뜬다
sh scripts/regenerate.sh     # 상류 원본에서 언어팩 적용 상태 전체를 다시 만든다
sh scripts/check-langpack.sh # 무회귀·번역 섞임·비교식 짝·번역률 검사
```

새 한국어 문구가 생기면 `regenerate.sh` 가 번역할 것만 모은 엑셀을 `review/` 에 만든다.
번역해서 `sh scripts/apply-translations.sh <엑셀>` 로 되돌리면 병합·검사 후 코드까지 다시 만든다.

자세한 절차는 [docs/regenerate.md](docs/regenerate.md).

## 설계 요점

- **기본은 한국어, 무회귀.** 기본 로케일은 `ko` 이고 `ko` 카탈로그는 원문 그대로다. 폴백은
  `현재 로케일 → ko → 키`. 표시를 떼면 상류 `index.html` 과 바이트 단위로 같다(도구가 확인).
- **언어는 고른 사람에게만.** `?lang=en` 이나 저장된 선택으로 바뀐다. 브라우저 언어는 기본으로 보지 않는다.
- **언어 변경은 다음 실행부터 적용.** 선택은 저장만 하고 지금 화면은 다시 그리지 않는다.
  정적 마크업 적용도 요소가 아직 원문을 보일 때만 바꿔, 앱이 써 넣은 현재 상태를 덮지 않는다.
- **옮기는 자리는 표시 자리뿐.** 비교식·`case`·선택자·타입 리터럴·`<option value>`·
  문서에 저장되는 입력칸 기본값·글꼴 이름은 옮기지 않는다.
- **번역은 원문 값에 묶인다.** 상류가 코드를 옮겨도 같은 문구면 번역이 따라온다.

## 라이선스

MIT — 상류 rhwp 와 같다. [LICENSE](LICENSE)
