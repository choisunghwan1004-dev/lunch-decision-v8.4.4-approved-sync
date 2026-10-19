@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 무료 테스트는 MySQL·OpenAI 키 없이도 실행합니다. 운영 AI 호출은 하지 않습니다.
where node >nul 2>nul
if errorlevel 1 goto missingnode
if not exist .venv\Scripts\python.exe (
 py -3 -m venv .venv
 if errorlevel 1 goto failed
)
if not exist node_modules\express (
 call npm ci
 if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -m pip install -r news_service\requirements-dev.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m news_service.run_checks --mode offline
if errorlevel 1 goto failed
echo test-results\checks-offline.json 과 .log 에 결과를 저장했습니다.
pause
exit /b 0
:missingnode
echo Node.js를 설치한 뒤 다시 실행하세요.
:failed
echo 실패 항목을 확인하세요. README 8절에 점검 방법이 있습니다.
pause
exit /b 1
