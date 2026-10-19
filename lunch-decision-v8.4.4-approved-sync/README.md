> **최신 수정:** 화면 깨짐/길찾기/관리자와 지도 분리 사항은 [README_V8.4.3.md](README_V8.4.3.md)를 먼저 참고하세요.

# 점심·여행 자동 결정 V8.4 통합 — 보존형 전환 패키지

이 패키지는 **V8.2 계열 사용자/관리자 화면**을 유지하면서, 독립 검증을 통과한 **V8.3 정규화 MySQL DB**로 API를 연결한 것입니다. **이전에 사용하던 `lunch_decision` DB에 UPDATE/ALTER/DELETE/DROP를 보내지 않습니다.**

## 구성

- 사용자 화면 `http://localhost:3100/`: 국가 → 시도 → 시군구 → 읍면동 → 상권, 회원가입/로그인, 개인 조건, 점심 추천/피드백/이력, 여행코스
- 관리자 화면 `http://localhost:3100/admin`: 행정구역 선택/등록, 음식점·카페·관광지·숙박 등록, 목록, FK 진단
- 백업: 원본/새 DB를 각각 읽기 전용으로 `.ndjson.gz`에 저장하고 SHA-256 체크섬 기록
- 이관: 원본을 읽기 전용으로 조회하고 **새 DB의 한 트랜잭션**으로 옮김. 이관 ID 대응표 `migration_mappings`로 재실행 중복 방지
- 중간 경로가 없는 상권 또는 원본 FK가 불명확하면 **임의로 다른 동에 붙이지 않음**: JSON 오류 보고서에 보류 기록
- DB 검증: MySQL FK, UI 선택 옵션 부모 ID, 전국/일본 샘플 지역까지 검사
- 테스트: JavaScript 계약 검사, 서버 시작 후 실제 HTTP API 통신 검사

## 설치 전 주의

1. **기존 V8.2.8과 V8.3 서버를 종료**하세요 (PowerShell `Ctrl+C`).
2. V8.4를 **새 폴더**에 압축 해제하세요. 기존 폴더를 덮어쓰지 마세요.
3. 기존 DB를 삭제하거나 기존 `database.sql`을 실행하지 마세요.
4. 새 DB 이름 `lunch_decision_v83`, 이전 DB 이름 `lunch_decision`을 **서로 다르게 설정**하세요.
5. API 키와 `.env`·백업 파일에는 비밀번호/개인정보가 포함될 수 있으므로 공유하지 마세요.

## Windows 11 PowerShell — 실행 순서

압축 파일의 `v84_integrated` 폴더에서 실행합니다.

```powershell
npm install
Copy-Item .env.example .env
notepad .env
```

이미 `.env`를 만들었다면 `Copy-Item` 단계는 건너뛰세요. `.env` 예:

```env
PORT=3100
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=실제_MYSQL_암호
OLD_DB_NAME=lunch_decision
V83_DB_NAME=lunch_decision_v83
SESSION_SECRET=적어도32글자이상의_랜덤_비밀키
ADMIN_USERNAME=admin
ADMIN_PASSWORD=본인만_아는_새_관리자암호
OPENWEATHER_API_KEY=
GOOGLE_MAPS_API_KEY=
```

### 1단계. 백업 — **먼저 실행**

```powershell
npm run backup
```

출력: `backups/latest-backup-manifest.json`과 `.ndjson.gz`. 기존/새 DB 백업은 읽기 전용으로 실행하며 DB 변경 없음. 압축된 자료와 manifest는 **반드시 PC 안에 보관**하세요.

### 2단계. 새 DB 준비와 샘플 테스트

```powershell
npm run setup
npm run seed:demo
npm run verify
```

`setup`은 오직 `lunch_decision_v83`을 준비합니다. 새로운 컬럼은 별도의 설치 명령에서만 추가합니다. 로그인이나 페이지 조회 시 ALTER가 발생하지 않습니다.

샘플 경로: 한국 서울특별시 종로구 → 종로1·2·3·4가동 → 종각상권 등 6개. 관광/점심/카페/관광/저녁/숙박 **시연용 가상 장소**가 포함됩니다. 테스트 장소의 주소·가격·좌표·영업시간은 실제 영업 정보가 아닙니다.

### 3단계. **이관 미리보기 — DB 변경 없음**

```powershell
npm run migrate:plan
```

결과 `diagnostics/migration-plan-report.json`을 확인하세요.

`skipped`(보류) 항목이 있다면 **상권이 기존 DB에서 시·군·구 바로 아래에 연결되는 등 정확한 하위 읍·면·동을 찾을 수 없는 경우**입니다. 다른 읍·면·동에 임의로 붙이지 않습니다.

### 4단계. **실제 이관**

```powershell
npm run migrate:apply
```

`migration_mappings`에 원본 ID와 신규 ID를 저장합니다. 실제 이관에 오류가 나면 **트랜잭션을 롤백**하고 기존 DB는 그대로 유지합니다.

이관 보류가 1건이라도 있으면 **기본 설정은 실제 커밋을 거절**합니다. 보류 내역을 확인하고 승인한 경우에만 다음을 사용하세요.

```powershell
node scripts/migrate.js --apply --allow-skips
```

이 옵션은 매핑되지 않은 항목을 새 DB에 포함하지 않습니다. 원본 데이터는 삭제되지 않습니다. 새 DB에 이관되지 않은 행은 `diagnostics/migration-apply-report.json`에 이유와 함께 저장됩니다.

**같은 아이디인데 비밀번호 해시가 다르거나 Google Place ID가 충돌하면 임의로 병합하지 않고 이관을 중단**합니다.

### 5단계. FK 연결 검사

```powershell
npm run verify
```

`diagnostics/connection-report.json`에서 `ok: true`, `foreignKeyErrors`의 값이 모두 `0`, `selectorBroken`가 `[]`인지 확인합니다.

### 6단계. 서버 및 화면 테스트

PowerShell 창 1:

```powershell
npm start
```

브라우저 주소: `http://localhost:3100`, 관리자: `http://localhost:3100/admin`

PowerShell 창 2에서 같은 폴더로 이동한 후:

```powershell
npm run test:ui
npm run test:api
```

`test:api`는 **읽기와 게스트 추천만 수행**하고 회원가입/저장은 자동으로 실행하지 않습니다. `diagnostics/screen-api-report.json`에 결과를 저장합니다.

### 화면 수동 테스트 (필수)

1. `http://localhost:3100` → 대한민국 → 서울특별시 → 종로구 → 종로1·2·3·4가동 → 종각상권 확인
2. 오늘 점심 다시 결정하기 → 등록된 테스트 음식점이 표시되는지 확인
3. 회원가입 → `회원등록 OK` 표시 → 조건 저장 → 나의 기록 다시 조회
4. `/admin` → `.env`의 관리자 계정으로 로그인 (기본 비밀번호를 강제로 사용하지 않음)
5. 음식점·여행장소 등록 → 상권을 선택한 후 등록 OK → 조회 목록에 보이는지 확인
6. `지역 관리 > 하위 지역 연결 검사`에서 잘못된 FK 수가 0인지 확인
7. 여행코스 → 종로구 선택 → 등록된 **테스트용** 관광/식사/카페/숙박이 6단계로 나타나는지 확인

## 이전 버전으로 돌아가기

- 새 V8.4 서버를 `Ctrl+C`로 종료하고 **원래 V8.2.8 폴더에서 이전 서버를 실행**하면 됩니다.
- `lunch_decision` 데이터는 이관 중 쓰지 않기 때문에 변경되지 않습니다. `lunch_decision_v83`은 별도 DB이며, V8.4에서 새로 저장한 데이터는 자동으로 옛 버전에 반영되지 않습니다.
- 백업 데이터를 따로 **새로운 빈 DB로 복구**하려면 다음 명령을 사용합니다. 기존 이름을 지정하면 실행하지 않습니다.

```powershell
node scripts/restore-to-new-db.js lunch_restore_20261016 lunch_decision
```

이 복원 명령은 **데이터와 일반 테이블을 복구**하며 VIEW·트리거·프로시저는 대상 원본의 구성에 따라 별도로 확인해야 합니다. 원본 DB 덮어쓰기는 지원하지 않습니다.

## 알려진 범위와 제한

- **실제 MySQL/브라우저 통합 테스트는 사용자의 PC에서 실행해야** 합니다. 제공된 ZIP의 Node 문법/순수 테스트만 제공 환경에서 확인했습니다.
- V8.4의 Google Places 자동 수집은 지역이 잘못 매핑되는 것을 방지하기 위해 **일시 비활성화(HTTP 501)** 되어 있습니다. 기존 데이터 및 관리자 수동 장소 입력은 가능합니다.
- 이동시간은 OSRM API에 실제 좌표가 있고 경로 조회가 성공했을 때만 표시합니다. 좌표가 없는 시연 장소는 `미확인`으로 표시합니다.
- 지역 구조가 정상이어도 해당 읍·면·동에 **상권 데이터가 없으면 상권 선택지는 비어 있습니다**. 관리자에서 상권을 추가하세요.
- 관리자·회원 비밀번호를 테스트 계정 그대로 운영 환경에 배포하지 마세요. HTTPS·세션 저장소·CSRF 대응은 운영 배포 전에 별도 구성해야 합니다.

### 진단 파일

- `backups/latest-backup-manifest.json` — 백업 데이터/해시
- `diagnostics/migration-plan-report.json` — 이관 미리보기
- `diagnostics/migration-apply-report.json` — 실제 이관 결과 및 보류 항목
- `diagnostics/connection-report.json` — DB/FK 선택 관계
- `diagnostics/screen-api-report.json` — 사용자/관리자 HTTP 연결 점검

**절대 `sql/01_schema.sql` 파일을 기존 DB로 직접 실행하지 마세요.** DB 이름이 내장되어 있지만, SQL은 `npm run setup` 경로로만 실행하기를 권장합니다.


## V8.4.1 업데이트 — `fetch failed` 진단 및 자동 시작

이전 `npm run test:api`는 별도 터미널에서 `npm start`를 켜야 했고 `PORT`를 무시한 채 `localhost:3100`으로 요청했습니다.
Windows에서 localhost가 IPv6(::1)으로 선택되면 IPv4(127.0.0.1) 서버로 연결하지 못하는 경우도 있었습니다.

V8.4.1은 다음을 변경했습니다.

- `.env`의 `PORT`를 API 테스트가 직접 사용하고, 기본 목적지로 `http://127.0.0.1:PORT`를 사용합니다.
- 서버가 꺼져 있으면 테스트용 서버를 자동 시작하고 테스트 후 **자신이 띄운 서버만 종료**합니다. 이미 실행 중인 서버는 종료하지 않습니다.
- 같은 포트에 다른 버전의 서버가 실행 중이면 버전을 확인하여 분명한 오류를 출력합니다.
- MySQL 접속·스키마 오류는 `fetch failed` 대신 URL/HTTP 상태/서버 오류를 표시합니다.
- `npm run doctor`를 추가했습니다. DB 비밀번호는 표시하지 않고 실행 포트와 DB 상태를 확인합니다.

압축을 새 폴더에 풀고 기존 `.env`를 복사한 뒤 다음만 실행해도 됩니다.

```powershell
npm install
npm run doctor
npm run test:ui
npm run test:api
```

서버를 계속 실행한 채 웹 화면을 사용하려면 별도로 `npm start`를 실행하세요.

주의: 서버를 자동으로 시작하더라도 DB가 준비되지 않았다면 테스트는 실패합니다. 이 경우 `npm run setup`, `npm run seed:demo`, `npm run verify` 결과를 먼저 확인하세요.

`API_TEST_AUTOSTART=0`으로 설정하면 자동 서버 시작을 끌 수 있습니다. `TEST_BASE_URL`로 원격/별도 포트를 선택할 수도 있습니다.

## V8.4.4: 승인형 Google Places 동기화
자세한 지침은 **README_V8.4.4.md**를 참고하세요. 신규 설치가 아닌 기존 V8.4.3 업그레이드는 `npm run backup` → `npm run setup:sync` → `npm run test:ui` → `npm start` 순서이며, 기존 DB 초기화/이관을 다시 수행할 필요가 없습니다.
