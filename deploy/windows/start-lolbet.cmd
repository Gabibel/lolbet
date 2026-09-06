@echo off
rem Lance le bot et ecrit toute la sortie dans data\lolbet.log.
rem Ce script est appele par la tache planifiee, pas directement.

setlocal
cd /d "%~dp0..\.."

if not exist ".venv\Scripts\python.exe" (
    echo [%date% %time%] .venv introuvable - lance d'abord: python -m venv .venv >> "data\lolbet.log"
    exit /b 1
)

if not exist "data" mkdir "data"

rem Rotation simple : on garde le journal de la session precedente.
if exist "data\lolbet.log" (
    if exist "data\lolbet.log.1" del "data\lolbet.log.1"
    ren "data\lolbet.log" "lolbet.log.1"
)

echo [%date% %time%] demarrage de LoLBet >> "data\lolbet.log"
".venv\Scripts\python.exe" -m lolbet >> "data\lolbet.log" 2>&1
echo [%date% %time%] LoLBet s'est arrete (code %errorlevel%) >> "data\lolbet.log"
endlocal
