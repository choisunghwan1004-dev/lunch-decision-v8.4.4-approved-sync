# 지역 뉴스 README 자동 갱신

## 위치별 뉴스·행사일정 추가·변경 (2026-10-20)

| 변경 항목 | 변경 전 | 변경 후 |
| --- | --- | --- |
| 메인 조회 | 지역과 무관한 통합 목록 | 상단에서 선택한 실제 시군구의 검증 소식·기사 최신 30건 |
| 행사일정 | 본문에만 있던 날짜 | 검증된 날짜 Fact의 시작일·종료일을 카드·상세에 별도 표시 |
| 상태 변경·화면 적용 | 이전 파일/서버 여부를 수동 확인 | 상태 변경 항목 없음, 19번 진단으로 파일·제공 화면·Python 버전 비교 |
| DB·수집·예약 | 기존 MySQL·원문 수동/CSV/JSON·16시 초안 예약 | 구조·예약 유지, 추가 SQL 없음, 자동 수집·자동 검증·자동 게시 없음 |

[기능·화면·DB·수집·환경 1~5 보완 및 적용 순서](NEWS_LOCATION_2026-10-20.md). 아래의 과거 검증 기록과 이력은 당시 결과를 보존합니다.


## 추가·변경 내용 (2026-10-20)

| 변경 항목 | 변경 전 | 변경 후 |
| --- | --- | --- |
| 자동 요약 | 기사 중심 운영 흐름과 내부 API 31개 | 검증 Fact/기사·위치별 일정 흐름과 내부 API 34개 반영 |
| 문서 처리 | README 지정 구역 자동 갱신 | 자동 구역은 유지, 각 상세 자료에 변경 전·후 기록과 공통 보고서 연결 |

기능·화면·DB·수집·환경의 통합 기재와 실제 검증 결과는 [추가·변경 보고서](NEWS_CHANGE_2026-10-20.md)를 참고하세요.

## 자동으로 반영하는 내용

`scripts/update-news-readme.js`가 README의 `REGIONAL_NEWS_START/END`와 `DEMO_GIFS_START/END` 사이만 생성한다. 다른 기능 설명과 통합 전 기록은 보존한다.

| 원본 | README에 반영할 항목 |
| --- | --- |
| `news_service/setup.py` | 뉴스 스키마 버전 |
| `news_service/ai_runtime.py` | 코드가 지정한 운영 모델 이름 |
| `news_service/automation.py` | 예약 시각·시간대 |
| `news_service/app.py` | FastAPI 경로와 HTTP 메서드 목록 |
| `sql/04_news_v852.sql`, `sql/05_news_automation.sql` | 기본·선택 뉴스 테이블과 개수 |
| `data/news/**/*.json` 및 같은 이름의 CSV | 자료 링크·Fact 후보 행 수·서로 다른 출처 수 |
| `docs/news-readme.json` | 사람이 관리하는 기능 흐름·운영 조건 |
| `docs/assets/demo-recordings.json` 및 실제 GIF | 실제 실행 화면·녹화 환경·시연 범위 |

**새 기능의 의미와 이용 조건은 사람이 확인한다.** 코드 상수·경로·자료 목록은 자동 반영하지만 구현 의도나 원문 사실 여부를 생성기가 판단하지 않는다. 새로운 동작은 `docs/news-readme.json`과 관련 기능 문서에도 적는다. 실행 GIF는 다시 녹화한 파일과 기록을 함께 올릴 때만 갱신한다.

## PC에서 실행하기

`package.json`이 있는 프로젝트 폴더의 PowerShell에서 실행한다. Node.js만 필요하며 Python·DB·OpenAI·노션에 접속하지 않는다.

```powershell
npm run docs:news
npm run test:docs
npm run docs:news:check
```

`npm run check`도 `precheck`에서 자동 갱신한다. `docs:news:check`는 내용이 다르면 종료 코드 1로 실패하고 파일을 수정하지 않는다. 추출할 상수가 없어지거나 자료 형식·구역 표시·GIF가 잘못되면 README를 덮어쓰지 않고 오류를 알린다.

## GitHub에서 자동 커밋하기

저장소 **최상위** `.github/workflows/news-readme.yml`이 `main`의 뉴스 코드·SQL·자료·GIF·생성기 관련 변경을 감지한다. 다운로드 폴더 안의 애플리케이션 폴더와 저장소 루트의 위치를 구별한다.

1. `main`의 최신 파일을 체크아웃한다.
2. 생성기 → 문서 테스트 → 최신 상태 검사를 실행한다. DB 설치와 유료 API 호출은 없다.
3. README가 달라졌을 때 **README 한 파일만** `github-actions[bot]`이 커밋한다. 차이가 없으면 새 커밋 없이 성공한다.
4. README만 바뀐 자동 커밋은 다시 실행 조건에 포함하지 않아 반복을 막는다.

GitHub **Actions → Regional news README sync**에서 실행 결과를 볼 수 있고 **Run workflow**로 수동 실행할 수도 있다. 이 workflow는 별도 API 키·PAT 없이 저장소의 `GITHUB_TOKEN`을 사용한다. workflow에는 `contents: write`를 선언했다. 조직의 권한 제한·Actions 비활성화·보호 브랜치의 직접 푸시 제한이 있으면 해당 단계가 실패할 수 있다. 저장소 정책은 자동으로 바꾸지 않는다. 실행 로그의 원인을 해결하거나 위 PC 명령으로 갱신한 README를 일반 PR 절차로 반영한다. 다른 커밋과 경합해 푸시가 거절되면 최신 `main`에서 다시 실행한다. 강제 푸시는 하지 않는다.

이 자동화는 **GitHub에서 커밋된 관련 변경**을 처리한다. Windows 파일을 실시간 감시하거나 실행 화면을 자동으로 만들어내지 않는다. 녹화 재현 방법은 [SCREEN_RECORDING.md](SCREEN_RECORDING.md), 출처 입력 예시는 [NEWS_SOURCES.md](NEWS_SOURCES.md)를 따른다.

## 확인 항목

- 새 자료 JSON을 추가했을 때 파일 링크와 행·출처 개수가 반영되는가?
- 코드의 모델·버전·경로를 바꾸면 해당 자동 구역도 달라지는가?
- 두 번 실행해 두 번째에 차이가 없는가?
- 수동 README 내용과 기존 한국·일본 기능 설명이 보존되는가?
- 없는 GIF·외부 이미지 경로·잘못된 구역 표시를 거절하는가?
- `.env`와 API 키가 문서에 들어가지 않는가?
- GitHub 실행 결과가 성공이며 차이가 있을 때만 README 자동 커밋이 생기는가?

DB 스키마·SQL 적용 순서·사용자 서버 시작 방법은 이번 문서 자동화로 바뀌지 않는다.
