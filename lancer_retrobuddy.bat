@echo off
REM Lance RetroBuddy (serveur web local) et ouvre le navigateur.
cd /d "%~dp0"
echo Demarrage de RetroBuddy...
echo Le navigateur va s'ouvrir sur http://127.0.0.1:8000
echo Laissez cette fenetre ouverte. Fermez-la (ou Ctrl+C) pour arreter RetroBuddy.
start "" /min cmd /c "timeout /t 3 >nul & start "" http://127.0.0.1:8000"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
echo.
echo RetroBuddy s'est arrete.
pause
