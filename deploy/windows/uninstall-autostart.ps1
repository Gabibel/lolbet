<#
.SYNOPSIS
    Retire le demarrage automatique de LoLBet.

.DESCRIPTION
    Supprime la tache planifiee et arrete le bot s'il tourne. Ne touche ni au
    code, ni au fichier .env, ni a la base data\lolbet.db.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File deploy\windows\uninstall-autostart.ps1
#>

$ErrorActionPreference = "Stop"
$TaskName = "LoLBet"

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "Aucune tache '$TaskName' installee. Rien a faire."
    return
}

Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false

Write-Host "Demarrage automatique retire." -ForegroundColor Green
Write-Host "Ta base de donnees et ton .env sont intacts."
