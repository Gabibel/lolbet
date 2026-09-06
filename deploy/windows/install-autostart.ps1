<#
.SYNOPSIS
    Lance LoLBet automatiquement a l'ouverture de session Windows.

.DESCRIPTION
    Cree une tache planifiee "LoLBet" qui demarre le bot sans fenetre, le
    relance s'il plante, et ecrit ses journaux dans data\lolbet.log.

    Aucun droit administrateur n'est necessaire : la tache appartient a ton
    compte et ne tourne que quand ta session est ouverte.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File deploy\windows\install-autostart.ps1
#>

$ErrorActionPreference = "Stop"

$TaskName = "LoLBet"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Launcher = Join-Path $PSScriptRoot "run-hidden.vbs"
$Venv = Join-Path $Root ".venv\Scripts\python.exe"
$EnvFile = Join-Path $Root ".env"

Write-Host "Projet : $Root"

if (-not (Test-Path $Venv)) {
    throw "Environnement virtuel introuvable : $Venv`nLance d'abord : python -m venv .venv puis .venv\Scripts\pip install -e ."
}
if (-not (Test-Path $EnvFile)) {
    throw "Fichier .env introuvable : $EnvFile`nCopie .env.example en .env et remplis les deux secrets."
}
if (-not (Test-Path $Launcher)) {
    throw "Lanceur introuvable : $Launcher"
}

# Une tache du meme nom existe deja : on la remplace proprement.
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Tache existante trouvee, remplacement..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$Launcher`"" -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Bot Discord LoLBet - suivi des parties League of Legends" | Out-Null

Write-Host ""
Write-Host "Installe. LoLBet demarrera a chaque ouverture de session." -ForegroundColor Green
Write-Host ""
Write-Host "Demarrer maintenant   : Start-ScheduledTask -TaskName $TaskName"
Write-Host "Arreter               : Stop-ScheduledTask -TaskName $TaskName"
Write-Host "Voir les journaux     : Get-Content '$Root\data\lolbet.log' -Tail 30 -Wait"
Write-Host "Desinstaller          : powershell -ExecutionPolicy Bypass -File deploy\windows\uninstall-autostart.ps1"
Write-Host ""
Write-Host "Pense a fermer la fenetre ou le bot tourne deja, sinon deux instances" -ForegroundColor Yellow
Write-Host "consommeront le quota Riot en double." -ForegroundColor Yellow
