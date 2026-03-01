@echo off
echo ========================================
echo Starting ExecSlate Application
echo ========================================
echo.

cd /d C:\ExecSlate

REM ── Razorpay Payment Keys (get from https://dashboard.razorpay.com/app/keys) ──
REM Replace these with your actual keys:
set RAZORPAY_KEY_ID="rzp_test_SLKIYez2nFSNzJ"
set RAZORPAY_KEY_SECRET="NBiKtxOmrEBp3G0Q1UN4qOOg"

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

