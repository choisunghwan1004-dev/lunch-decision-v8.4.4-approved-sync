# V8.4.4 — 상권 확인·승인형 Google Places 자동 동기화

## 이번 버전에서 바뀐 점

V8.4.3의 점심 추천·1~7일 여행코스·길찾기·관리자 지역선택은 유지합니다.
V8.4.4는 **관리자가 선택한 국가 → 시·도 → 시·군·구 → 읍·면·동 → (선택) 법정동/리 → 상권**에 실제 Google Place ID를 연결합니다.

**중요: 이 기능은 관리자 승인형 동기화입니다.** 검색 결과를 바로 DB에 활성화하지 않습니다.

1. 상권까지 선택하고 음식점 / 카페 / 관광지 / 숙박 종류 선택
2. **미리보기**: Google Places Text Search (New) 조회; 기존 DB에 아직 기록하지 않음
3. 주소의 **국가·시도·시군구**를 서버에서 확인; 다른 지역은 승인 불가능
4. **읍면동·상권 소속**을 관리자 본인이 **장소마다 2개 체크박스**로 확인
5. **비활성 저장**: DB에 `google_place_id`, 선택 상권 `area_id`, 종류 및 승인 기록만 저장 (`places.active=0`)
6. **승인 장소 조회 → 최종 활성화**: 다시 Google 지역 검증 후 `places.active=1`. 이때부터 점심·여행 추천 대상

상권은 행정 경계처럼 Google API에서 확정해 주는 데이터가 아닙니다. 그러므로 프로그램은 **국가/시도/시군구를 자동 차단 검사하고, 읍면동/상권은 관리자 확인을 강제**합니다. 실제 상권의 지리적 소속을 API만으로 보장할 수 없으며 관리자의 확인이 필요합니다.

**위도·경도는 지역 승인에 전혀 사용하지 않습니다.** 기존 장소의 좌표나 Places 실시간 응답의 좌표가 있으면 길찾기와 이동시간 계산에서만 사용될 수 있습니다.

## 설치 — 기존 DB 보존

기존 V8.4.3 프로그램을 Ctrl+C로 종료한 뒤 **별도 폴더**에 새 ZIP을 풉니다. 이전 `.env`를 새 폴더에 복사하세요.

PowerShell (현재 프로젝트 폴더에서 실행):

```powershell
npm install
npm run backup
npm run setup:sync
npm run test:sync
npm run test:ui
npm start
```

- 이미 V8.4.3의 DB 이관이 완료된 상태라면 **`npm run setup` / `npm run migrate:apply` / `npm run seed:demo`는 다시 실행하지 않아도 됩니다.**
- `setup:sync`는 **새 V8.3 DB**에 승인 기록 테이블 `google_sync_reviews`를 생성할 뿐 기존 회원·음식점·여행 기록을 삭제하지 않습니다.
- 외부 DB로 옮기기 전에는 백업 파일과 체크섬이 생성됐는지 꼭 확인하세요.
- `.env`: `V83_DB_NAME=lunch_decision_v83`, `OLD_DB_NAME=lunch_decision`, `GOOGLE_MAPS_API_KEY=본인_키`, `ADMIN_PASSWORD=관리자_비밀번호`.
- Google Cloud에서 **Places API (New)** 활성화, 청구 계정 및 API Key 서버 사용 제한(해당 API/서버 IP)을 확인하세요.
- 관리자: http://localhost:3100/admin → **🌐 실제 데이터 동기화**.
- 진단: http://localhost:3100/api/system/check (응답의 `sync.schemaReady`, `sync.enabled`).

## 지역 확인 규칙

| 상황 | 처리 |
|---|---|
| Google 주소 국가가 선택 국가와 다름/없음 | 검색 결과 승인 차단 |
| 시·도, 시·군·구 주소가 선택값과 다름/확인 불가 | 승인 차단 |
| 같은 시·군·구이지만 다른 읍면동이 주소에 명확히 나타남 | 승인 차단 |
| 읍면동 정보가 구체적으로 나오지 않음 | 장소별 관리자의 읍면동 확인 체크 요구 |
| Google에는 정확한 상권 경계 데이터가 없음 | 장소별 상권 확인 체크 필수 |
| 같은 Google Place ID가 다른 상권에 이미 등록됨 | 자동 이전/중복 저장 금지, 전체 승인 트랜잭션 중단 |
| 미리보기 생성 후 상권 FK 변경 또는 10분 경과 | 저장 차단, 다시 검색 |
| 저장만 완료 | 비활성, 추천과 여행코스에서 제외 |
| 관리자가 최종 활성화 | Google 주소를 다시 조회해 지역 검증 후 활성화 |

### 동기화 유형
- restaurant: 음식점
- cafe: 카페
- attraction: 관광 명소
- lodging: 숙박

국가별 번역명이 다른 경우 코드가 임의로 다른 지역에 연결하지 않도록 **일본 도쿄·신주쿠 등 주요 명칭의 명시적 별칭**을 제공합니다. 추가 행정구역의 별칭은 `lib/google-sync.js`의 `aliases`에 추가할 수 있습니다.

## 라이선스·API 요금

Places API(New) 검색, 승인시 Place Details 재검증, 활성화 재검증, 화면 최신 정보 조회는 **API 사용 요금이 발생할 수 있습니다**. 한 번의 미리보기는 최대 12곳입니다. 승인 장소 이름·주소·좌표 등 Google 콘텐츠는 영구 DB에 복제하지 않고 필요할 때 실시간 조회합니다. Place ID만 영구 저장합니다. Google Places 공식 저장/표시 정책과 Google 로고·저작권 표시를 확인하세요.

- Places 검색 문서: https://developers.google.com/maps/documentation/places/web-service/text-search
- Places 데이터 정책: https://developers.google.com/maps/documentation/places/web-service/policies
- Place ID 정책: https://developers.google.com/maps/documentation/places/web-service/place-id

## 서버 API

`POST /api/admin/sync-google-places/preview` `{area_id,place_type}` → `{token,results}`

`POST /api/admin/sync-google-places/approve` `{token,area_id,selected:[{id,confirmTown:true,confirmArea:true}]}` → 비활성 저장

`GET /api/admin/sync-google-places/pending?area_id=N` → 승인 기록/활성 상태

`POST /api/admin/sync-google-places/activate` `{area_id,place_ids:[1,2],confirmation:"ACTIVATE"}` → 활성화

모든 API에는 **관리자 세션**이 필요합니다. 오래된 단일 호출 `/api/admin/sync-google-places`는 안전하게 409 오류로 안내합니다.

## 검증과 제한사항

`npm run test:ui`는 순수 규칙 테스트이며 실 API에 과금하지 않습니다. Chrome 모의 API 브라우저 테스트로 지역 선택 → 미리보기 → 비활성 저장 → 활성화 흐름을 점검했습니다.

현재 배포 환경에는 사용자의 실제 MySQL·Google API 키가 없으므로 **실제 유료 Google API 호출, 실제 DB 트랜잭션 성공 및 실 주소 검증은 사용자 PC에서 확인해야 합니다**. 동기화 미리보기 정보는 서버 메모리에 최대 10분간만 남으므로, 서버 재시작 시 다시 검색해야 합니다. 복수 서버 운영에는 별도 세션 공유/일회성 저장소가 필요합니다.

## 장애 확인

1. `npm run setup:sync` 실패: MySQL 권한·DB 이름·잠금 확인.
2. 미리보기 `API_KEY_INVALID`: `.env`의 Google Maps Platform API 키/청구 계정/Places(New) 활성화 확인.
3. 상권이 비어 있음: 관리자 **지역 관리**에서 읍면동·상권 관계 등록 및 연결 검사를 먼저 진행.
4. 올바른 일본 주소가 차단됨: 해당 지역에 한국어/일본어 별칭 추가 검토; 다른 지역으로 임의 연결하지 말 것.
5. `Google 장소 정보 확인 필요`: 사용 시 최신 Place Details 조회 실패, 키/할당량 확인. 좌표를 임의로 생성하지 않습니다.
