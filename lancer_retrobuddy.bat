@echo off
cd /d "%~dp0"

REM --- Auto-reparation : si pas encore installe, lancer l'installeur ---
if not exist ".venv\Scripts\python.exe" (
  echo Premiere utilisation : installation necessaire...
  call "%~dp0installer.bat"
  if not exist ".venv\Scripts\python.exe" ( echo Installation incomplete. & pause & exit /b 1 )
)

echo Demarrage de RetroBuddy...
echo Laissez CETTE fenetre ouverte. Pour arreter : fermez-la (ou Ctrl+C).

REM --- Ouvrir le navigateur SEULEMENT quand le serveur repond (evite "site inaccessible") ---
start "" /min powershell -NoProfile -Command "for($i=0;$i -lt 60;$i++){ try{ $c=New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1',8000); $c.Close(); Start-Process 'http://127.0.0.1:8000'; break } catch { Start-Sleep -Milliseconds 500 } }"

".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo.
echo RetroBuddy s'est arrete.
pause
