@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 뉴스 연결 설정과 테이블을 점검합니다. OpenAI 유료 호출은 없습니다.
where node >nul 2>nul
if errorlevel 1 goto failed
call scripts\ensure-news-python.bat
if errorlevel 1 goto failed
if not exist node_modules\express (
 call npm ci
 if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -m pip install -r news_service\requirements.txt
if errorlevel 1 goto failed
rem 기존 DB 비밀번호와 API 키를 보존하고 뉴스 설정과 테이블만 준비합니다.
.venv\Scripts\python.exe -m news_service.setup --init-env %*
if errorlevel 1 goto failed
.venv\Scripts\python.exe -c "from news_service.service import NewsService;s=NewsService();print('Regions:',len(s.regions()));print('Topics:',len(s.topics()))"
if errorlevel 1 goto failed
echo 연결 복구 준비 완료. 기존 Node와 FastAPI 창에서 Ctrl+C를 누르고 종료하세요.
echo 09_뉴스_서버시작.bat 실행 후 브라우저에서 Ctrl+F5를 누르세요.
echo 시군구가 0개면 지역 관리에서 등록하거나 시연용으로 npm run seed:demo를 실행하세요.
pause
exit /b 0
:failed
echo 연결 복구를 중단했습니다. 화면의 오류와 README_NEWS_RECOVERY.md를 확인하세요.
echo DB_PASSWORD 설정과 MySQL 실행을 확인하세요. 기존 DB 업그레이드는 백업 후 --upgrade-existing으로 실행하세요.
pause
exit /b 1
