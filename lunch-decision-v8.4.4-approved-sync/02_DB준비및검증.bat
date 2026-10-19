@echo off
chcp 65001 >nul
cd /d "%~dp0"
call npm run setup || goto error
call npm run seed:demo || goto error
call npm run verify || goto error
call npm run migrate:plan || goto error
echo 미리보기: diagnostics\migration-plan-report.json 을 검토하세요.
pause
exit /b 0
:error
echo 오류를 확인하고 이후 단계로 넘어가지 마세요.
pause
exit /b 1
