@echo off
cd /d C:\IT-Newsletter_automation
call venv\Scripts\activate.bat
python run_server.py >> logs\api.log 2>&1