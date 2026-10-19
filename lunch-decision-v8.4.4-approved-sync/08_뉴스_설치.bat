@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
 py -3 -m venv .venv
 if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -m pip install -r news_service\requirements.txt
if errorlevel 1 goto failed
call npm run backup
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m news_service.setup --init-env %*
if errorlevel 1 goto failed
echo .env의 OPENAI_API_KEY와 OPENAI_NEWS_MODEL=gpt-6-luna를 확인하세요.
echo 09_뉴스_서버시작.bat으로 Node와 FastAPI를 실행하세요.
pause
exit /b 0
:failed
echo 설치를 중단했습니다. 오류와 README_NEWS_V8.5.2.md를 확인하세요.
echo 기존 뉴스 테이블이 있으면 백업 후 이 파일을 --upgrade-existing 인수로 실행하세요.
pause
exit /b 1
