@echo off
cd /d "%~dp0"
REM Met a jour RetroBuddy en telechargeant la derniere version depuis GitHub.
REM Pas besoin de Git. Vos donnees (data\) et votre cle (config.local.yaml) sont preservees.
REM Tout le travail est fait par _maj.ps1 (charge en memoire -> insensible a son propre remplacement).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_maj.ps1"
