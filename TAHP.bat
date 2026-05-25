@echo off
cd /d "%~dp0tahp-console"
if not exist node_modules (
    echo Installing dependencies...
    npm install
)
start http://localhost:5173
npm run dev
