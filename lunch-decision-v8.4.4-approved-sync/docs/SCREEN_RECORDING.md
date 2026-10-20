# Windows 화면 녹화와 README GIF 등록

[프로젝트 README로 돌아가기](../README.md#demo)

실제 실행 단계의 화면을 **GIF 파일**로 묶어 README에 표시합니다. GIF는 움직이는 이미지이며 음성을 담지 않습니다. 2026-10-20에 Linux Chromium 134.0.6998.35 · 실제 Node/FastAPI · MySQL 8.0.36의 격리 테스트 DB에서 아래 4개 GIF를 만들었습니다. 연속 영상 대신 실제 UI를 조작한 주요 단계의 캡처를 보여줍니다. 사용자 Windows PC의 실행 성공 기록과 구분합니다.

| 파일 | 확인한 실제 동작 | 길이·크기 |
| --- | --- | --- |
| [lunch-demo.gif](assets/lunch-demo.gif) | 한국 종로구·일본 신주쿠구 선택과 점심 추천 결과 | 5단계 · 10.8초 · 약 1.10 MiB |
| [travel-demo.gif](assets/travel-demo.gif) | 종로구 2일 일정, 하루 6단계·총 12단계 | 4단계 · 8.8초 · 약 0.84 MiB |
| [news-demo.gif](assets/news-demo.gif) | 종로 주제·CSV 가져오기, 출처 3건·Fact 후보 8건·근거 연결 8건, 출처 편집 입력 항목 | 7단계 · 17.2초 · 약 1.24 MiB |
| [news-publication-demo.gif](assets/news-publication-demo.gif) | **모의 AI 응답**의 원문 비교·확인 체크 하나·빈 메모 검증 저장·지역 소식·출처 확인 | 5단계 · 14초 |

점심·여행 장소는 **가상 테스트 데이터**이고 `news-demo.gif`는 기존 공개 행사 자료의 **검증 대기 후보**입니다. 처음 3개 GIF의 DB에서는 기사 초안·게시·AI 사용 기록 모두 0건을 확인했습니다. 별도 `news-publication-demo.gif`는 AI 응답만 테스트 대역으로 대체하고 실제 DB·화면에서 간편 검증 저장·지역 소식 반영을 검증했습니다. 실제 OpenAI·노션 호출과 운영 기사 게시가 아닙니다. 처음 3개 녹화에서 브라우저의 외부 정적 이미지 요청 2건도 차단했습니다. 한글·지역 선택·UTC 입력·검증 대기·게시 카드 표시를 GIF 프레임에서 확인했습니다. Windows에서 직접 다시 녹화하려면 아래 절차를 따릅니다.

## 1. ScreenToGif 준비

Windows 10·11에서 화면 일부를 녹화하고 GIF로 저장하는 방법입니다.

1. [ScreenToGif 공식 배포 페이지](https://github.com/NickeManarin/ScreenToGif/releases/latest)를 엽니다.
2. **Assets**에서 일반적인 Intel·AMD 64비트 PC는 `Portable.x64.zip`이 들어간 파일을 고릅니다. ARM PC는 `Portable.Arm64.zip`을 고릅니다.
3. **2026-10-20 확인 버전은 2.43.2**입니다. 해당 x64 파일은 [ScreenToGif.2.43.2.Portable.x64.zip](https://github.com/NickeManarin/ScreenToGif/releases/download/2.43.2/ScreenToGif.2.43.2.Portable.x64.zip)입니다. 버전이 바뀌면 최신 배포 페이지의 파일명을 확인합니다.
4. ZIP을 내려받아 탐색기에서 마우스 오른쪽 버튼 → **모두 압축 풀기**를 누릅니다.
5. 압축을 푼 폴더에서 `ScreenToGif.exe`를 실행합니다. 실행용 구성이 포함된 일반 Portable 파일을 선택하며, `Light`판에는 별도 .NET Desktop Runtime이 필요합니다.

## 2. 프로그램 화면 녹화

1. 기존 실행 안내에 따라 서버를 시작하고, 브라우저에 본인의 시스템을 엽니다. 기본 주소는 `http://127.0.0.1:3100/`이며 실제 PORT 설정에 맞춥니다.
2. ScreenToGif 시작 화면에서 **녹화 / Recorder**를 선택합니다.
3. 녹화 테두리를 브라우저의 필요한 화면에 맞춥니다. 전체 바탕화면보다 기능이 보이는 부분만 담습니다.
4. 처음에는 **10 FPS, 가로 약 960~1200px, 10~20초**를 권장합니다. 이는 README 가독성과 용량을 위한 권장값이며 필수 규격은 아닙니다.
5. **녹화 / Record**를 누르고 기능 한 가지를 천천히 실행합니다. 결과 화면은 2초 정도 보여줍니다.
6. **정지 / Stop**를 누르면 편집기가 열립니다.
7. 앞뒤의 불필요한 프레임을 선택해 삭제하고 **파일 → 다른 이름으로 저장 / Save as** 또는 `Ctrl+S`를 누릅니다.
8. 출력 형식을 **GIF**로 선택하고 파일명을 정한 뒤 저장합니다. 반복 재생 옵션을 사용하면 README에서 반복되는 시연을 만들 수 있습니다.
9. 저장한 GIF를 브라우저에 끌어 놓아 움직임과 글자 크기를 확인합니다.

비밀번호·API 키·토큰이 표시되는 설정 화면은 녹화 영역에 넣지 않습니다.

## 3. 이 프로젝트의 녹화 순서

아래는 GIF를 교체할 때의 녹화 순서입니다. 현재 화면에서 정상 작동하는 기능만 담고 녹화 환경·실제 시연 범위를 함께 기록합니다.

| GIF 파일명 | 녹화할 화면과 순서 |
| --- | --- |
| `lunch-demo.gif` | 메인 → 국가·지역·상권 선택 → 점심 추천 또는 다시 결정 → 음식점 결과 |
| `travel-demo.gif` | 여행 일정 → 등록된 지역·일수 선택 → 일정 생성 → 날짜별 장소 |
| `news-demo.gif` | 관리자 지역 뉴스 → 종로 주제 → CSV 가져오기 → 출처·검증 대기 Fact → 출처 편집 항목 확인 |

사용자 공개 기사 조회를 추가로 녹화하려면 이미 게시된 기사가 있을 때 해당 화면을 담습니다. 실제 기사 생성·승인·게시는 기존 운영 절차를 따릅니다. 현재 뉴스 GIF는 가져오기와 출처 확인만 보여줍니다.

## 4. GitHub에 GIF 파일 올리기

README가 있는 **프로젝트 폴더**를 기준으로 설명합니다. 이 저장소는 바깥 저장소와 안쪽 프로젝트 폴더의 이름이 같습니다.

1. GitHub에서 [프로젝트 이미지 폴더](https://github.com/choisunghwan1004-dev/lunch-decision-v8.4.4-approved-sync/tree/main/lunch-decision-v8.4.4-approved-sync/docs/assets)를 엽니다.
2. **Add file → Upload files**를 누릅니다.
3. 녹화한 `lunch-demo.gif`를 끌어 넣습니다.
4. `docs/assets/demo-recordings.json`의 날짜·환경·파일·설명도 실제 녹화에 맞게 고치고 함께 커밋합니다.
5. 파일이 프로젝트의 `docs/assets/lunch-demo.gif`에 등록되었는지 확인합니다.

GitHub의 **저장소 파일 업로드**는 브라우저에서 파일당 25 MiB 제한입니다. 이와 별개로 **이슈·댓글의 이미지/GIF 첨부**는 10 MB 제한입니다. 이 안내는 저장소 폴더 업로드 방식을 사용하며, 빠른 표시를 위해 GIF 한 개를 가능하면 5 MB 안팎으로 줄이는 것을 권장합니다.

## 5. README의 시연 이미지 활성화

README의 실행 화면 구역은 [자동 갱신](NEWS_README_AUTOMATION.md)하므로 직접 편집하지 않습니다. `docs/assets/demo-recordings.json`에 실제 파일과 시연 범위를 기록하고 `npm run docs:news`로 반영합니다. `main`에 파일·기록을 올리면 GitHub Actions도 같은 작업을 수행합니다. 생성되는 접기 영역은 다음 형태입니다.

```html
<details>
<summary>점심 추천 — 지역 선택부터 추천 결과까지</summary>

<img src="docs/assets/lunch-demo.gif" alt="지역과 상권을 선택하고 점심 추천 결과를 확인하는 실제 실행 화면" width="1000">

</details>
```

- 이미지 경로는 README 기준 상대 경로입니다. PC의 `C:\\...` 경로를 넣지 않습니다.
- `width="1000"`은 README 표시 폭입니다. GIF 용량을 줄이려면 저장할 때 실제 해상도·프레임 수·길이도 줄여야 합니다.
- 실제로 준비한 파일만 기록에 넣습니다. 없는 파일·GIF가 아닌 파일·외부 URL은 생성기가 거절합니다.
- 녹화 날짜와 보여주는 동작을 `demo-recordings.json`에 적고, 실행하지 않은 AI·게시 기능이 완료된 것처럼 설명하지 않습니다.
- 생성 후 **Preview**와 `npm run docs:news:check`를 확인하고 커밋합니다.

가장 간단한 Markdown 형태는 다음과 같습니다. 접기·펼치기가 필요 없을 때 사용할 수 있습니다.

```markdown
![점심 추천 실행 화면](docs/assets/lunch-demo.gif)
```

기존 GIF를 그대로 두면 원래 녹화 날짜도 유지합니다. 코드 변경만으로 실행 화면을 새로 시험한 것으로 표시하지 않습니다.

## 6. 확인과 용량 줄이기

1. 커밋 후 GitHub README를 새로고침하고 해당 기능 제목을 눌러 펼칩니다. GIF가 움직이고 글자를 읽을 수 있어야 합니다.
2. 이미지가 보이지 않으면 업로드 경로·파일명·대소문자와 `main` 반영 여부를 확인합니다.
3. 너무 느리면 녹화 길이를 줄이고, ScreenToGif 편집기에서 실제 가로 크기를 줄인 뒤 다시 GIF로 저장합니다.

## 공식 참고 자료

- [ScreenToGif 공식 저장소](https://github.com/NickeManarin/ScreenToGif)
- [녹화 도구 사용법](https://github.com/NickeManarin/ScreenToGif/wiki/Help-%E2%96%AA-Recording-%F0%9F%93%B9)
- [GIF 등 파일로 저장하는 방법](https://github.com/NickeManarin/ScreenToGif/wiki/Help-%E2%96%AA-Editor-%E2%9C%8F%EF%B8%8F-%E2%96%AA-Exporting-your-project-%F0%9F%92%BE)
- [GitHub 저장소 파일 업로드](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository)
- [GitHub 첨부파일 유형과 용량](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/attaching-files)

## 7. 개발자가 동일한 실행 화면을 다시 만들기

실행 중인 MySQL과 임시 DB 생성·삭제 권한이 필요합니다. 도구는 `news_test_ui_`로 시작하는 새 DB 하나를 만들고 가상 장소·뉴스 자료를 넣어 실제 Node/FastAPI를 실행한 후 해당 DB를 삭제합니다. 운영 DB 이름을 받아 재사용하지 않습니다. OpenAI 등 외부 키는 자식 프로세스에서 비웁니다. 기존 GIF와 녹화 기록은 새 실행 결과로 교체됩니다.

프로젝트 폴더의 PowerShell에서 실행합니다. DB 비밀번호는 명령줄에 직접 쓰지 않고 보안 입력으로 받습니다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r news_service\requirements-demo.txt
.\.venv\Scripts\python.exe -m playwright install chromium
npm ci

$env:DB_HOST = '127.0.0.1'
$env:DB_PORT = '3306'
$env:DB_USER = 'root'
$dbCredential = Get-Credential -UserName $env:DB_USER -Message '임시 녹화 DB 생성 계정의 비밀번호'
try {
    $env:DB_PASSWORD = $dbCredential.GetNetworkCredential().Password
    .\.venv\Scripts\python.exe scripts\record-readme-demo.py --font 'C:\Windows\Fonts\malgun.ttf'
} finally {
    Remove-Item Env:DB_PASSWORD -ErrorAction SilentlyContinue
}
npm run docs:news
npm run test:docs
npm run docs:news:check
```

자세한 서버 로그·검사 수치는 커밋하지 않는 `test-results/readme-demo`에 남깁니다. 공개할 파일은 검토한 GIF와 녹화 기록뿐입니다. Linux에서는 설치된 한글 TTF의 실제 경로를 `--font`에 전달하고 브라우저에서도 한글 글꼴을 사용할 수 있게 준비합니다. Windows의 위 재현 명령은 제공한 절차이며 이번 검증은 Linux에서 수행했습니다.

게시·자동 갱신 GIF는 별도 통합 테스트에서 만든다. MySQL 접속 환경은 위와 같고, PowerShell에서 `$env:NEWS_RECORD_PUBLICATION='1'`, `$env:NEWS_DEMO_FONT='C:\Windows\Fonts\malgun.ttf'`를 설정한 뒤 `.\.venv\Scripts\python.exe tests\news\browser_smoke.py`를 실행한다. 테스트는 임시 DB에서만 모의 AI 응답을 허용하고 운영 DB에서는 시작을 거절한다. 성공하면 `news-publication-demo.gif`와 해당 녹화 기록을 갱신한다. 기본 3개 녹화 도구는 다른 시연 기록을 보존하고, 간편 검증 통합 테스트는 해당 GIF만 교체한다. 마지막으로 `npm run docs:news`를 실행한다.
