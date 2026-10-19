@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [1/4] Node packages...
call npm install
if errorlevel 1 goto error
echo [2/4] Back up current databases...
call npm run backup
if errorlevel 1 goto error
echo [3/4] Create approval table in V8.3 DB (safe migration)...
call npm run setup:sync
if errorlevel 1 goto error
echo [4/4] Run sync rules tests...
call npm run test:sync
if errorlevel 1 goto error
echo Done. Start with: npm start
pause
exit /b 0
:error
echo Installation stopped. Check logs above. No automatic database reset was run.
pause
exit /b 1
