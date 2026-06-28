@echo off
setlocal
cd /d "%~dp0"
echo ============================================
echo    Installation de RetroBuddy
echo ============================================
echo.

REM --- 1) Trouver Python ---
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
  echo Python n'est pas installe sur cet ordinateur.
  echo.
  echo Je vais ouvrir la page de telechargement de Python.
  echo   IMPORTANT : pendant l'installation, COCHEZ la case
  echo   "Add python.exe to PATH" ^(tout en bas de la 1ere fenetre^).
  echo.
  echo Quand Python est installe, relancez ce fichier "installer.bat".
  echo.
  start "" "https://www.python.org/downloads/"
  pause
  exit /b 1
)
echo [OK] Python detecte : %PY%

REM --- 2) Creer l'environnement isole ---
if not exist ".venv\Scripts\python.exe" (
  echo [..] Creation de l'environnement...
  %PY% -m venv .venv
  if errorlevel 1 ( echo [ERREUR] Creation de l'environnement impossible. & pause & exit /b 1 )
)
echo [OK] Environnement pret.

REM --- 3) Installer les composants ---
echo [..] Installation des composants ^(1 a 2 minutes, connexion Internet requise^)...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 ( echo [ERREUR] Installation des composants impossible. & pause & exit /b 1 )
echo [OK] Composants installes.

REM --- 4) Raccourci sur le bureau ---
echo [..] Creation du raccourci sur le bureau...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$w=New-Object -ComObject WScript.Shell; $d=[Environment]::GetFolderPath('Desktop'); $s=$w.CreateShortcut((Join-Path $d 'RetroBuddy.lnk')); $s.TargetPath=(Join-Path '%~dp0' 'lancer_retrobuddy.bat'); $s.WorkingDirectory='%~dp0'; $ico=(Join-Path '%~dp0' 'app\ui\static\retrobuddy.ico'); if(Test-Path $ico){ $s.IconLocation=$ico+',0' }; $s.Save()"
echo [OK] Raccourci "RetroBuddy" cree sur le bureau.

echo.
echo ============================================
echo    Installation terminee !
echo    Double-cliquez sur "RetroBuddy" (bureau).
echo ============================================
pause
