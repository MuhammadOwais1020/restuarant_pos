@echo off

cd /d "E:\donot-delete\restuarant_pos\restuarent_app"

start "" http://127.0.0.1:8000/

python manage.py runserver

pause
