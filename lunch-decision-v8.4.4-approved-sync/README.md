# 점심 선택 시스템 · 점심/여행 자동 결정 V8.4.4

한국·일본의 지역과 상권을 선택하고, 등록된 음식점·관광지·카페·숙박으로 점심과 여행 일정을 구성하는 Node.js / Express / MySQL 시스템입니다.

**문서 기준일: 2026-10-19**  
**이 저장소의 실행 버전: V8.4.4 — 관리자 확인·승인형 Google Places 동기화**  
**「점심 선택 시스템」의 최신 확장 작업: V8.5.1 AI 지역 뉴스 제작 센터**

이 README는 현재 저장소의 코드, 별도 브랜치의 뉴스 코드, 최신 대화에서 보고된 실행 결과를 구분합니다. 이번 커밋은 지정 폴더의 README만 갱신합니다.

## 1. 현재 코드와 최신 작업 상태

| 항목 | 상태와 근거 |
| --- | --- |
| 현재 저장소 `main` | V8.4.4 점심·여행·지도·Google 장소 승인형 동기화 코드 |
| Google 동기화 | 미리보기 → 개별 확인 → 비활성 저장 → 최종 활성화 API 구현. 아래에 검색 인수 구조 오류를 명시 |
| 현재 저장소의 AI 뉴스 | 뉴스 서비스·테이블 생성 스크립트·관리자 뉴스 메뉴가 아직 포함되지 않음 |
| 별도 V8.5.1 뉴스 작업 | 기존 V8.4.1 저장소의 두 기능 브랜치에 코드 존재. 이 저장소에 병합된 상태는 아님 |
| 뉴스 MySQL 실행 | 최신 대화 보고 기준, 사용자 PC에서 독립형의 `news_*` 10개 테이블 생성·조회와 기존 지역 4건 확인 |
| 실제 OpenAI 호출 | 최신 확인 기록에서 성공이 확인되지 않음. MySQL 점검만으로 OpenAI 성공을 판단하지 않음 |
| 뉴스 최종 승인·사용자 공개 | V8.5.2 후속 작업. V8.5.1 초안 생성 후 자동 게시하지 않음 |

뉴스용 테이블이 사용자 PC에 생성되어 있어도 이 저장소에 뉴스 화면/API가 자동으로 추가되지는 않습니다.

## 2. 현재 제공하는 기능

| 구분 | 기능 |
| --- | --- |
| 지역 | 국가 → 시·도 → 시·군·구 → 읍·면·동 → 상권, 법정동/리 연결 구조 |
| 사용자 | 회원가입·로그인, 개인 조건 저장, 점심 추천, 회원 방문/거부 피드백과 이력 |
| 점심 추천 | 예산·평점·선호/기피 음식·최근 회원 이력에 따른 규칙 기반 점수 |
| 관리자 | 지역·상권·음식점·카페·관광지·숙박 등록/조회, FK 연결 진단 |
| 여행 | 1~7일, 날짜별 관광 → 점심 → 카페 → 관광 → 저녁 → 숙박 |
| 장소 분산 | 종류별 순환 배분, 등록 장소가 충분하면 중복 회피 |
| 지도 | Google 지도 검색·길찾기, 장소명/주소 직접 입력, 출발 기준 선택 |
| 날씨 | OpenWeather 키 설정 시 현재 날씨 조회 |
| 이동시간 | 실제 장소의 좌표와 OSRM 자동차 경로 응답을 확인한 구간만 합산 |
| 시연 데이터 | 종로구 음식점·카페·관광지·숙박 각 14곳, 총 56곳 등록 스크립트 |
| 데이터 관리 | 원본 DB 백업, 별도 DB 이관, ID 대응표, 지역 연결 검사 |

56곳은 **가상 테스트 장소**입니다. 실제 매장·호텔로 안내하지 않으며, 지도는 해당 지역까지만 연결합니다. 실제 장소명·주소 또는 확인된 좌표를 등록해야 개별 장소의 경로를 안내할 수 있습니다.

현재 여행 엔진은 장소 분산과 연결 확인용입니다. 실제 영업시간·예약·날씨·예산·교통을 동시에 최적화하는 완성형 여행 예약 시스템으로 검증되지는 않았습니다.

## 3. V8.4.4 Google Places 승인형 동기화

관리자 화면의 **「🌐 실제 데이터 동기화」**에서 진행하도록 구성되어 있습니다.

1. 국가부터 읍·면·동과 상권까지 선택하고 장소 종류를 고릅니다.
2. 미리보기로 최대 12개 후보를 검색합니다. 이 단계에서는 DB에 장소를 저장하지 않습니다.
3. 서버가 주소의 국가·시도·시군구를 검사하고, 식별되는 다른 읍·면·동을 차단합니다.
4. 관리자가 장소별로 **읍·면·동 소속**과 **상권 소속** 두 항목을 확인합니다.
5. 승인한 신규 장소를 `places.active=0`으로 저장하고 승인 기록을 남깁니다.
6. 승인 장소 목록에서 최종 활성화를 요청하면 Google 주소를 다시 검증합니다.
7. `places.active=1`이 된 장소부터 점심·여행 추천 대상에 포함합니다.

같은 Google Place ID가 다른 상권이나 다른 장소 종류에 등록되어 있으면 자동 이전하지 않고 승인 트랜잭션을 중단합니다. 이미 활성 상태인 동일 장소를 재확인한 경우에는 기존 활성 상태를 유지합니다.

- **지역 확인:** 좌표로 상권 소속을 추정하지 않습니다. 상권 소속은 관리자 확인이 필요합니다.
- **미리보기:** 관리자 세션·선택 상권과 연결하며 최대 10분간 메모리에 유지합니다. 서버 재시작·만료·지역 연결 변경 시 다시 검색해야 합니다.
- **저장 범위:** 이 동기화 경로는 Place ID·상권 FK·종류·승인 기록과 식별용 이름을 저장합니다. Google에서 받은 이름·주소·좌표는 필요할 때 다시 조회하는 구조입니다.
- **공유 운영:** 여러 서버에서 운영하려면 세션과 미리보기 상태 공유 구성이 추가로 필요합니다.

상세 안내: [README_V8.4.4.md](README_V8.4.4.md)

### 코드 검토에서 확인한 검색 오류

현재 `routes/api.js`는 `sync.textSearch({path, siblings}, type)`을 호출하지만, `lib/google-sync.js`의 `textSearch`는 전달 객체에서 `country_code`·지역명을 직접 읽습니다.

그 결과 실제 네트워크를 사용하지 않는 모의 호출에서 다음 요청 값이 재현되었습니다.

```json
{
  "textQuery": "     음식점",
  "regionCode": "UNDEFINED"
}
```

**Google 미리보기 기능을 실사용하기 전에 이 인수 구조를 수정하고 실제 응답으로 검증해야 합니다.** 현재 순수 규칙 테스트만으로 검색 API 연결 성공을 보장할 수 없습니다. 이번 README 커밋에서는 프로그램 코드를 수정하지 않았습니다.

### 관리자 API

모든 경로에는 기존 관리자 세션이 필요합니다.

| 메서드·경로 | 역할 |
| --- | --- |
| `POST /api/admin/sync-google-places/preview` | `area_id`, `place_type`으로 후보와 미리보기 토큰 조회 |
| `POST /api/admin/sync-google-places/approve` | 토큰과 장소별 `confirmTown`·`confirmArea` 확인 후 비활성 저장 |
| `GET /api/admin/sync-google-places/pending?area_id=N` | 승인 장소와 활성 상태 조회 |
| `POST /api/admin/sync-google-places/activate` | 장소 ID 목록과 `confirmation: "ACTIVATE"`로 최종 활성화 |
| `POST /api/admin/sync-google-places` | 기존 단일 호출은 HTTP 409로 단계별 처리 안내 |

이전 README의 Google 수집 HTTP 501 비활성 안내는 V8.4.3까지의 설명입니다. V8.4.4에는 위 단계별 API가 추가되었으며, 현재 검색 오류와 실통합 검증 상태를 함께 확인해야 합니다.

## 4. Windows PowerShell 설치·실행

저장소 폴더와 실행 폴더 이름이 같습니다. `package.json`이 있는 **안쪽 폴더**에서 실행합니다.

```powershell
git clone https://github.com/choisunghwan1004-dev/lunch-decision-v8.4.4-approved-sync.git
cd lunch-decision-v8.4.4-approved-sync
cd lunch-decision-v8.4.4-approved-sync
npm install
```

현재 `package.json`에 명시된 Node.js 최소 버전은 18.18이며 DB는 MySQL 8.x를 기준으로 합니다.

### 처음 설치하는 경우

`.env`가 없을 때만 예제를 복사합니다.

```powershell
Copy-Item .env.example .env
notepad .env
```

```dotenv
PORT=3100
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=YOUR_MYSQL_PASSWORD
OLD_DB_NAME=lunch_decision
V83_DB_NAME=lunch_decision_v83
SESSION_SECRET=replace-with-a-long-random-secret-at-least-32-characters
ADMIN_USERNAME=admin
ADMIN_PASSWORD=CHANGE_TO_YOUR_OWN_PASSWORD
OPENWEATHER_API_KEY=
GOOGLE_MAPS_API_KEY=
```

기존 데이터가 있으면 먼저 `npm run backup`의 성공과 백업 파일을 확인합니다. 신규 DB 준비가 필요한 경우에만 다음을 실행합니다.

```powershell
npm run setup
npm run seed:demo
npm run setup:sync
npm run verify
npm run verify:travel
npm start
```

- `setup`은 안전 장치상 `lunch_decision_v83`을 준비합니다. `OLD_DB_NAME`과 달라야 합니다.
- `setup:sync`는 신규 DB에 `google_sync_reviews` 승인 기록 테이블을 추가합니다.
- `seed:demo`는 56개 여행 샘플 등록도 포함합니다.
- Google 동기화를 사용하려면 서버용 키, Places API (New) 활성화·청구 설정을 확인하고 위 검색 오류를 먼저 해결합니다.

### 기존 V8.4.3에서 업데이트하는 경우

기존 서버를 `Ctrl+C`로 종료하고 새 폴더에 코드를 준비합니다. 기존 `.env`를 복사한 뒤 실행합니다.

```powershell
npm install
npm run backup
npm run setup:sync
npm run test:sync
npm run test:ui
npm start
```

이미 준비된 DB를 초기화하거나 `migrate:apply`·`seed:demo`를 반복할 필요는 없습니다.

### 접속과 상태 확인

- 사용자: http://127.0.0.1:3100/
- 관리자: http://127.0.0.1:3100/admin
- 서버/DB 상태: http://127.0.0.1:3100/health
- 연결 진단: http://127.0.0.1:3100/api/system/check

`PORT=3100` 기준이며 실제 설정에 맞춥니다. `sync.schemaReady`는 승인 테이블 존재 여부이고, `sync.enabled`는 테이블과 키 설정 여부입니다. **이 값이 true여도 실제 Google 요청 성공을 뜻하지 않습니다.**

V8.4.3의 지도 URL과 화면 구성은 유지됩니다. Google 지도 링크는 관리자 로그인이나 API 키 없이 사용할 수 있으며, OSRM 이동시간 계산과는 별도입니다. 이전 화면이 남으면 `Ctrl+Shift+R`로 새로고침합니다.

## 5. DB 구조·백업·이관·복원

주요 연결은 `countries → provinces → districts → admin_towns → commercial_areas → places`입니다. 법정구역은 `legal_units`·`town_legal_links`로 연결합니다.

| 테이블 | 역할 |
| --- | --- |
| `users`, `user_preferences` | 회원·개인 조건 |
| `lunch_history` | 추천·방문·거부 기록 |
| `migration_mappings` | 구 DB와 신규 DB의 ID 대응, 이관 중복 방지 |
| `google_sync_reviews` | 장소/상권 FK, 검토 관리자, 지역 확인, 승인·활성 시각 |

상세 관계: [ERD-V8.4.md](ERD-V8.4.md), [ERD-V8.3.md](ERD-V8.3.md)

기존 `lunch_decision`은 백업·이관에서 읽기 용도로 사용하며 신규 `lunch_decision_v83`에 쓰는 구조입니다. 부모 지역이 불명확한 항목은 보류하고 임의로 다른 읍·면·동에 연결하지 않습니다.

```powershell
npm run backup
npm run migrate:plan
```

`backups/latest-backup-manifest.json`, 압축 백업과 체크섬, `diagnostics/migration-plan-report.json`을 확인한 뒤 실제 이관이 필요한 경우 실행합니다.

```powershell
npm run migrate:apply
npm run verify
```

이관 오류는 신규 DB 트랜잭션을 롤백합니다. 보류 항목이 있으면 기본적으로 커밋을 거절합니다. 보류 내역을 검토해 일부만 이관하기로 결정한 경우에만 `node scripts/migrate.js --apply --allow-skips`를 사용합니다. 제외된 원본 행은 삭제하지 않으며 결과 보고서에 남깁니다.

아이디의 비밀번호 해시 또는 Google Place ID가 충돌하면 임의로 병합하지 않습니다. SQL 파일을 기존 DB에 직접 실행하지 않습니다.

백업을 별도 빈 DB로 복원하는 예:

```powershell
node scripts/restore-to-new-db.js lunch_restore_20261019 lunch_decision
```

복원 대상은 새로운 DB 이름을 사용합니다. 테이블·데이터 외 VIEW·트리거·프로시저는 별도로 확인합니다. 구버전 서버로 돌아가려면 새 서버를 종료하고 구버전 폴더에서 실행합니다. 신규 DB에 저장한 데이터는 구버전 DB로 자동 반영되지 않습니다.

## 6. 「점심 선택 시스템」 최신 확장 — V8.5.1 AI 지역 뉴스

최종 순서는 **지역·주제/출처 → Fact Sheet 입력·검증 → 검증된 사실만 초안 생성 → 관리자 검수 → 후속 최종 승인·사용자 게시**입니다.

- 종로구 등 기존 `districts.id`와 뉴스 주제를 연결합니다.
- 출처 URL·기관·발행일과 사실별 근거를 기록합니다.
- 관리자가 출처와 대조한 사실만 `verified`로 처리합니다.
- 검증된 Fact만 OpenAI Responses API의 `gpt-4.1-mini`에 전달합니다.
- 초안의 수치·지역/시각·인과·출처를 검수하고 수정·반려 기록을 보관합니다.
- 확인되지 않은 인터뷰·원인·통계를 만들지 않고 생성 직후 자동 게시하지 않습니다.
- 최종 승인과 사용자 공개는 V8.5.2에서 연결합니다.

### 현재 코드는 별도 저장소의 기능 브랜치에 있음

| 구분 | 코드 위치·실행 구조 |
| --- | --- |
| 독립형 | [feature/v8.5.1-ai-local-news](https://github.com/choisunghwan1004-dev/lunch-decision-v8.4.1-api-fixed/tree/feature/v8.5.1-ai-local-news/v84_integrated/news-service) — `news-service`, FastAPI 8000, 별도 개발용 관리자 인증 |
| 통합형 | [feature/v8.5.1-news-center](https://github.com/choisunghwan1004-dev/lunch-decision-v8.4.1-api-fixed/blob/feature/v8.5.1-news-center/v84_integrated/README_V8.5.1.md) — 기존 관리자 세션 → Node 내부 프록시 → FastAPI 8001 |

두 브랜치는 뉴스 DB 컬럼과 인증 구조가 다르므로 테이블 생성 SQL을 서로 호환된다고 가정해 함께 실행하지 않습니다. V8.4.4에 통합할 때는 적용할 구조를 정하고 기존 UI·기능·DB를 보존하는 변경분만 이관해야 합니다.

### 최신 실행 확인 범위

최신 대화 보고 기준으로 **독립형**에서 MySQL 뉴스 테이블 10개 생성·조회와 기존 지역 4건이 확인되었습니다.

`news_topics`, `news_sources`, `news_facts`, `news_fact_evidence`, `news_drafts`, `news_reviews`, `news_claims`, `news_claim_facts`, `news_publications`, `news_ai_usage`

`news_publications` 테이블이 존재해도 최종 승인·게시 기능이 완성되었다는 뜻은 아닙니다.

독립형 뉴스 폴더의 `live_check.py`는 기본 실행 시 MySQL만 확인합니다. 해당 브랜치의 `news-service` 폴더에서, 키와 환경을 준비한 뒤 다음을 실행하면 OpenAI 호출도 요청합니다. 실제 API 사용 비용이 발생할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe live_check.py --openai
```

`diagnostics/news-live-check.json`의 `mysql.ok`, `openai.attempted`, `openai.ok`를 구분해 확인합니다. OpenAI 점검의 짧은 응답 성공과 실제 Fact Sheet 기반 기사 생성·저장은 별도 검증입니다.

**이 명령과 뉴스 폴더는 현재 V8.4.4 저장소에는 없습니다.** 뉴스용 환경변수도 별도 모듈 설정을 따라야 하며, 현재 Node 앱의 `.env`에 키만 추가해 뉴스 기능이 생기지는 않습니다.

### 다음 작업

- [ ] Google 미리보기 인수 구조 수정 및 실제 검색·승인·활성화 검증
- [ ] 적용할 뉴스 모듈을 V8.4.4 관리자 화면에 통합
- [ ] 실제 OpenAI 요청과 Fact Sheet → 초안 → DB 저장 통합 검증
- [ ] V8.5.2 관리자 최종 승인·사용자 공개 연결
- [ ] Notion 「AI사업계획서」 작업 기록에 구현·검증 결과와 ERD/흐름도 갱신

이번 README 변경은 뉴스 모듈 병합이나 Notion 수정을 수행하지 않습니다.

## 7. 검증 명령과 결과 해석

실행 폴더에서 사용합니다.

```powershell
npm run check
npm run test:ui
npm run doctor
npm run verify
npm run verify:travel
npm run test:api
```

| 명령 | 확인 범위 |
| --- | --- |
| `check` | 주요 JavaScript 문법 |
| `test:ui` | 지역·지도·여행·동기화 규칙의 Node 테스트 |
| `test:map` / `test:sync` | 지도 또는 동기화 테스트만 선택 실행 |
| `doctor` / `verify` | DB 접속·FK·지역 선택 연결 |
| `verify:travel` | 종류별 장소 수와 3일 일정 연결 |
| `test:api` | 실제 HTTP 화면/API와 여행 1·2·3일의 6·12·18단계 응답 |

`test:api`는 DB가 준비되어 있어야 하며, 서버가 없으면 임시 서버를 시작해 검사 후 자신이 시작한 서버만 종료합니다. 이 테스트는 실제 Google 유료 검색이나 OpenAI 기사를 검증하지 않습니다.

브라우저에서는 지역 연쇄 선택·회원 조건/이력·관리자 장소 등록·여행 일정·길찾기를 확인합니다. 검색 오류 수정 후 실제 상권으로 미리보기→비활성 저장→최종 활성화를 별도로 점검합니다.

진단 파일:

- `diagnostics/connection-report.json` — DB/FK/지역 선택 관계
- `diagnostics/screen-api-report.json` — HTTP 화면/API 검사
- `diagnostics/migration-plan-report.json` / `migration-apply-report.json` — 이관 검토/결과

**이번 문서 작업에서 확인한 것:** 저장소 코드·문서, 별도 뉴스 브랜치 코드, Google 검색 인수 불일치의 네트워크 없는 모의 재현.  
**이번 환경에서 실행하지 않은 것:** 실제 MySQL, 유료 Google API, OpenAI, 브라우저 통합 테스트. 사용자 PC의 최신 대화 보고와 이번 검증을 구분합니다.

## 8. 변경 관리와 참고 문서

기존 사용자·관리자 화면, 스타일, 상태와 세부 기능을 유지하며 필요한 코드·DB 변경 스크립트·문서만 커밋합니다. `.env`, API 키, DB 비밀번호, 실제 사용자 데이터와 백업은 올리지 않습니다.

기술 구성은 Node.js / Express 5 / express-session / bcryptjs / mysql2와 HTML·CSS·JavaScript입니다.

| 파일 | 역할 |
| --- | --- |
| [server.js](server.js), [routes/api.js](routes/api.js) | 서버·세션·지역·회원·추천·여행·동기화 API |
| [public/index.html](public/index.html), [public/admin.html](public/admin.html) | 사용자·관리자 화면 |
| [lib/google-sync.js](lib/google-sync.js) | Google 검색·지역 확인·미리보기 상태 |
| [lib/travel-plan.js](lib/travel-plan.js), [public/map-links.js](public/map-links.js) | 일정 구성·지도 링크 |
| [sql/03_v844_google_sync.sql](sql/03_v844_google_sync.sql) | 승인 기록 테이블 |
| [README_V8.4.4.md](README_V8.4.4.md) | 승인형 동기화 상세 안내 |
| [README_V8.4.3.md](README_V8.4.3.md), [README_V8.4.2.md](README_V8.4.2.md) | 지도·여행 개선 이력 |

기존 버전 문서의 과거 테스트 기록은 이번 환경의 실행 결과로 간주하지 않습니다.
