@echo off
REM 1) Activate virtualenv (adjust path if your venv folder is named differently)
call "%~dp0venv\Scripts\activate.bat"

REM 2) cd into project folder (if batch is in root, this is optional)
cd /d "%~dp0"

REM 3) Export DJANGO_SETTINGS_MODULE (on Windows):
set DJANGO_SETTINGS_MODULE=restuarent_app.settings

REM 4) Run Django on port 8000
python manage.py runserver 0.0.0.0:8000
