@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [V8.4.1] API 테스트는 서버가 없으면 임시 서버를 자동 시작합니다.
call npm run doctor
call npm run test:ui || goto error
call npm run test:api || goto error
echo API 테스트가 완료되었습니다.
pause
exit /b 0
:error
echo 테스트 오류가 발생했습니다. npm run doctor / npm run verify 결과를 확인하세요.
pause
exit /b 1
