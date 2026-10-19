# OpenAI 실제 호출 실행 안내

전체 예약까지 처음 설치하는 분은 [Windows 상세 실행 순서](README_AUTOMATION.md)를 보세요. **키 설정 → 실제 호출 확인만 먼저 하면 MySQL이 없어도 됩니다.**

## 1. 키 설정

`package.json`과 이 안내가 있는 폴더에서 `13_OpenAI_키설정.bat`을 더블클릭합니다. Python 가상환경과 의존성을 준비한 뒤 API 키를 입력받습니다. [OpenAI API Keys](https://platform.openai.com/api-keys)에서 발급한 본인의 키를 붙여 넣고 Enter를 누르세요. 입력 문자가 안 보이는 것이 정상입니다.

키와 `OPENAI_NEWS_MODEL=gpt-6-luna`를 프로젝트 루트 `.env`에 저장합니다. 기존 DB·관리자 설정은 보존합니다. 키를 채팅이나 GitHub에 올리지 마세요. 키를 변경했다면 실행 중인 FastAPI 창을 종료하고 `09_뉴스_서버시작.bat`을 다시 실행하세요. OS 환경 변수의 값이 있으면 `.env`보다 우선합니다.

## 2. 실제 API를 한 번 호출

`14_OpenAI_실제호출테스트.bat`을 실행합니다. 실제 OpenAI API 비용이 발생합니다. 고정된 수업용 가상 Fact 1건을 뉴스 운영과 같은 `generate_article` 함수에 보내며 자동 재시도하지 않습니다. MySQL 연결·기사 저장·승인·게시는 하지 않습니다.

성공한 경우 `test-results/openai-live.json`에 다음 값과 실제 초안·응답 ID·토큰 수·소요 시간이 저장됩니다.

```json
{"ok": true, "live_openai_succeeded": true, "model": "gpt-6-luna", "is_demo": true}
```

위 코드는 성공 결과의 형태를 설명하는 예입니다. 제공된 코드가 실제 호출에 성공했다는 실행 증거는 아닙니다. 응답 JSON 형식과 Fact Key 연결을 확인하는 검사이며 사실·기사 품질 검증은 사람의 별도 작업입니다.

PowerShell에서 직접 실행하려면:

```powershell
.\.venv\Scripts\python.exe -m news_service.openai_check --status
.\.venv\Scripts\python.exe -m news_service.openai_check --live
```

`--status`는 무료 설정 조회이며 실제 연결 성공을 판정하지 않습니다. `--live`만 실제 요청을 보냅니다. 무료 테스트 `10_뉴스_무료테스트.bat`은 계속 API를 호출하지 않습니다.

## 3. 관리자 화면에서 확인

서버를 시작하고 `http://127.0.0.1:3100/admin`에 로그인 → 지역 뉴스 → **OpenAI 연결 확인**을 누릅니다. 설정 안내에서 **실제 API 한 번 호출 (유료)**을 누르면 동일한 연결 검사를 실행합니다. 키가 없거나 모델 설정이 다르면 버튼이 비활성화됩니다.

이후 실제 운영 주제에 출처와 Fact를 등록하고 원문 대조를 완료한 뒤 **검증 Fact로 초안 생성**을 누릅니다. 운영 생성은 기존 `news_ai_usage`에 요청 ID·토큰 또는 안전한 오류 코드를 저장합니다. 테스트 초안은 운영 기사로 자동 게시하지 않습니다.

## 4. 오류 해결

| 코드 | 원인과 조치 |
|---|---|
| `missing_api_key` | 13번 파일로 키를 입력하고 FastAPI 재시작 |
| `invalid_api_key` | API 키 재발급, 프로젝트 선택 확인 |
| `model_configuration` | `.env`의 `OPENAI_NEWS_MODEL=gpt-6-luna` 확인 |
| `model_access` | API 프로젝트의 해당 모델·Responses 사용 권한 확인; 다른 모델로 자동 변경하지 않음 |
| `insufficient_quota` | OpenAI API Billing 잔액·예산·프로젝트 한도 확인 |
| `rate_limit` | 호출 한도에 도달했으므로 잠시 후 재실행 |
| `timeout` | 자동 재시도 없음; API 사용량 확인 후 재실행 |
| `connection` | 인터넷·방화벽·프록시 점검 |
| `incomplete_output` / `invalid_output` | 출력 미완료·JSON/Fact 연결 오류; 초안을 저장하지 않음 |

Windows 배치 자체, 실제 계정의 유료 OpenAI 호출은 이 개발 환경에서 실행하지 않았습니다. 실제 SDK의 HTTP 요청·응답·오류 처리는 네트워크 대역으로 검증했습니다.

참조: [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna) · [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) · [OpenAI 오류](https://developers.openai.com/api/docs/guides/error-codes).
