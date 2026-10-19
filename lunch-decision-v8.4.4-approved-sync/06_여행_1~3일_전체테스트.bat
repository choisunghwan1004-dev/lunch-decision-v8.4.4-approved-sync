@echo off
chcp 65001 >nul
cd /d "%~dp0"
call npm run verify:travel
if errorlevel 1 goto err
call npm run test:ui
if errorlevel 1 goto err
call npm run test:api
if errorlevel 1 goto err
echo.
echo V8.4.2 여행 1/2/3일 전체 검사 OK
pause
exit /b 0
:err
echo.
echo 테스트 실패: 위쪽 오류 메시지를 복사해 주세요.
pause
exit /b 1
