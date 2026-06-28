@echo off
cd /d "%~dp0"
echo ============================================
echo    Mise a jour de RetroBuddy
echo ============================================
echo.

where git >nul 2>nul
if errorlevel 1 (
  echo Git n'est pas installe : la mise a jour automatique en a besoin.
  echo Je vais ouvrir la page de telechargement de Git.
  start "" "https://git-scm.com/download/win"
  pause
  exit /b 1
)

if not exist ".git" (
  echo Ce dossier n'est pas un depot Git ^(installe via ZIP ?^).
  echo Pour des mises a jour automatiques sans perte de donnees, reinstallez
  echo l'application via "git clone" ^(voir le README^).
  pause
  exit /b 1
)

echo [..] Recuperation de la derniere version...
git pull --ff-only
if errorlevel 1 (
  echo [ERREUR] Mise a jour impossible ^(modifications locales ou conflit^).
  echo Vos donnees ne sont PAS touchees. Demandez de l'aide si besoin.
  pause
  exit /b 1
)

echo [..] Mise a jour des composants...
".venv\Scripts\python.exe" -m pip install -r requirements.txt >nul 2>nul

echo.
echo ============================================
echo    A jour ! Vos donnees (base + cle) sont intactes.
echo ============================================
pause
