@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 파일/실행 서버만 비교합니다. DB, 키, 프로세스, 예약 작업을 변경하지 않습니다.
node scripts\news-ui-doctor.js
set "NEWS_UI_RESULT=%ERRORLEVEL%"
pause
exit /b %NEWS_UI_RESULT%
