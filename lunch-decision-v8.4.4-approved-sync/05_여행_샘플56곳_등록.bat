@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [V8.4.2] 기존 DB 백업 후 56개 테스트 장소를 추가합니다.
call npm install
if errorlevel 1 goto err
call npm run backup
if errorlevel 1 goto err
call npm run seed:travel
if errorlevel 1 goto err
call npm run verify:travel
if errorlevel 1 goto err
echo.
echo 샘플 등록 및 FK 검증 OK
pause
exit /b 0
:err
echo.
echo 오류 발생: 위쪽 메시지를 복사해서 전달해 주세요.
pause
exit /b 1
