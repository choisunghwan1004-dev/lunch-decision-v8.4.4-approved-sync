@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [V8.4] 1. npm install, 2. .env, 3. backup
where node >nul 2>nul || (echo Node.js 18 이상을 설치하세요.& pause& exit /b 1)
call npm install || (echo npm 설치 실패& pause& exit /b 1)
if not exist .env (copy .env.example .env >nul & notepad .env)
echo .env의 MySQL 비밀번호와 ADMIN_PASSWORD를 확인하세요.
pause
call npm run backup
pause
