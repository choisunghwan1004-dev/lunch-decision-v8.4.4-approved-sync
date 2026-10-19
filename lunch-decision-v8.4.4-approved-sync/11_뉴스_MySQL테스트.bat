@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 테스트 계정에 별도 news_test_* DB 생성·삭제 권한이 필요합니다.
if not exist .venv\Scripts\python.exe goto failed
.venv\Scripts\python.exe -m news_service.run_checks --mode mysql
if errorlevel 1 goto failed
echo test-results\checks-mysql.json 과 .log 에 결과를 저장했습니다.
pause
exit /b 0
:failed
echo 먼저 10_뉴스_무료테스트.bat 을 실행하고 MySQL 서버와 .env 설정을 확인하세요.
pause
exit /b 1
