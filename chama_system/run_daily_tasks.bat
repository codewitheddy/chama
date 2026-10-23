@echo off
REM Finance Wise TBM — Daily scheduled tasks
REM Runs every morning to keep loan statuses and reminders up to date.

set PYTHON=C:\Users\EddyDesigns\AppData\Local\Python\pythoncore-3.14-64\python.exe
set MANAGE=D:\DCWelfare\chama_system\manage.py
set LOG=D:\DCWelfare\chama_system\daily_tasks.log

echo. >> "%LOG%"
echo ========================================= >> "%LOG%"
echo %DATE% %TIME% — Daily tasks started >> "%LOG%"
echo ========================================= >> "%LOG%"

echo Marking late loans... >> "%LOG%"
"%PYTHON%" "%MANAGE%" mark_late_loans >> "%LOG%" 2>&1

echo Sending loan reminders... >> "%LOG%"
"%PYTHON%" "%MANAGE%" send_loan_reminders >> "%LOG%" 2>&1

echo %DATE% %TIME% — Daily tasks finished >> "%LOG%"
