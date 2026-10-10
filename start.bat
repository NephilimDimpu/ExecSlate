@echo off
echo ========================================
echo Starting ExecSlate Application
echo ========================================
echo.

cd /d %~dp0

REM ── Configuration ──────────────────────────────────────────────────────────
REM Secrets are NOT stored in this file. Put them in a local .env file, which
REM is git-ignored, and they will be picked up automatically:
REM
REM   RAZORPAY_KEY_ID=...        from https://dashboard.razorpay.com/app/keys
REM   RAZORPAY_KEY_SECRET=...
REM   OPENAI_API_KEY=...         any one AI provider is enough; without any,
REM   GEMINI_API_KEY=...         ExecSlate falls back to statistical insights
REM   SESSION_SECRET=...         required when ENV=production
REM
REM See README.md for the full list.

echo Checking Python installation...
python --version
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    pause
    exit /b 1
)

echo.
echo Starting server on http://localhost:8000
echo Press Ctrl+C to stop the server
echo.

python app.py
pause
