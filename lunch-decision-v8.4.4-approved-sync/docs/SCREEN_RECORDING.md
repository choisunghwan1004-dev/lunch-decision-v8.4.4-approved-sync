# Windows 화면 녹화와 README GIF 등록

[프로젝트 README로 돌아가기](../README.md#demo)

예시 README처럼 동작하는 화면을 보여주려면 프로그램 실행 화면을 녹화한 **GIF 파일**을 README에 이미지로 넣습니다. GIF는 움직이는 이미지이며 음성을 담지 않습니다. 현재 저장소에는 본인 실행 GIF가 아직 없고, README의 시연 영역은 녹화·업로드 대기 상태입니다.

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

아래는 녹화 계획이며 실제 촬영 또는 기능 성공 기록이 아닙니다. 현재 화면에서 정상 작동하는 기능만 담습니다.

| GIF 파일명 | 녹화할 화면과 순서 |
| --- | --- |
| `lunch-demo.gif` | 메인 → 국가·지역·상권 선택 → 점심 추천 또는 다시 결정 → 음식점 결과 |
| `travel-demo.gif` | 여행 일정 → 등록된 지역·일수 선택 → 일정 생성 → 날짜별 장소 |
| `news-demo.gif` | 사용자 메인의 지역 소식 → 지역 선택 → 이미 게시된 기사 → 원자료 출처 |

먼저 `lunch-demo.gif` 한 개만 만들어도 됩니다. 뉴스는 게시된 기사가 있을 때 조회 화면을 녹화합니다. 실제 기사 생성·승인·게시는 기존 운영 절차를 따릅니다.

## 4. GitHub에 GIF 파일 올리기

README가 있는 **프로젝트 폴더**를 기준으로 설명합니다. 이 저장소는 바깥 저장소와 안쪽 프로젝트 폴더의 이름이 같습니다.

1. GitHub에서 [프로젝트 이미지 폴더](https://github.com/choisunghwan1004-dev/lunch-decision-v8.4.4-approved-sync/tree/main/lunch-decision-v8.4.4-approved-sync/docs/assets)를 엽니다.
2. **Add file → Upload files**를 누릅니다.
3. 녹화한 `lunch-demo.gif`를 끌어 넣습니다.
4. 변경 설명을 입력하고 커밋합니다. PR로 올리는 경우 병합 후 README를 활성화합니다.
5. 파일이 프로젝트의 `docs/assets/lunch-demo.gif`에 등록되었는지 확인합니다.

GitHub의 **저장소 파일 업로드**는 브라우저에서 파일당 25 MiB 제한입니다. 이와 별개로 **이슈·댓글의 이미지/GIF 첨부**는 10 MB 제한입니다. 이 안내는 저장소 폴더 업로드 방식을 사용하며, 빠른 표시를 위해 GIF 한 개를 가능하면 5 MB 안팎으로 줄이는 것을 권장합니다.

## 5. README의 시연 이미지 활성화

프로젝트의 [README.md](../README.md)를 열고 연필 버튼으로 편집합니다. **실행 화면 GIF**의 해당 기능에서 대기 문구와 파일명 안내를 정리하고, 이미지 앞뒤의 `<!--`와 `-->`를 지웁니다. 점심 GIF를 올렸다면 해당 접기 영역을 다음처럼 만듭니다.

```html
<details>
<summary>점심 추천 — 지역 선택부터 추천 결과까지</summary>

<img src="docs/assets/lunch-demo.gif" alt="지역과 상권을 선택하고 점심 추천 결과를 확인하는 실제 실행 화면" width="900">

</details>
```

- 이미지 경로는 README 기준 상대 경로입니다. PC의 `C:\\...` 경로를 넣지 않습니다.
- `width="900"`은 README 표시 폭입니다. GIF 용량을 줄이려면 저장할 때 실제 해상도·프레임 수·길이도 줄여야 합니다.
- 업로드한 영역만 활성화합니다. 한 개만 준비했다면 상단 상태를 “점심 GIF 등록 완료 · 여행/뉴스 GIF 녹화 대기”로 바꾸고, 모든 시연이 완료된 것으로 표시하지 않습니다.
- 준비가 끝난 영역의 녹화 계획 문구를 실제 녹화 날짜와 보여주는 동작에 맞게 고칩니다.
- 마지막 GIF까지 등록한 후에 “현재 상태: 녹화·업로드 대기”와 하단의 등록 대기 안내를 정리합니다.
- **Preview**에서 확인한 뒤 커밋합니다.

가장 간단한 Markdown 형태는 다음과 같습니다. 접기·펼치기가 필요 없을 때 사용할 수 있습니다.

```markdown
![점심 추천 실행 화면](docs/assets/lunch-demo.gif)
```

녹화한 GIF를 이 대화에 첨부하면 실제 파일을 저장소에 추가하고 README의 해당 이미지를 연결할 수 있습니다. 아직 받지 않은 GIF를 녹화 완료로 표시하지 않습니다.

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

이번 변경은 문서와 시연 영역 준비입니다. 실제 Windows 녹화, GIF 업로드·재생 확인, 애플리케이션 재시험은 수행하지 않았습니다.
