' Lance start-lolbet.cmd sans aucune fenetre console.
' Sans ce wrapper, une fenetre noire resterait ouverte en permanence.
Option Explicit

Dim shell, fso, here, target
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

here = fso.GetParentFolderName(WScript.ScriptFullName)
target = fso.BuildPath(here, "start-lolbet.cmd")

' 0 = fenetre masquee, False = ne pas attendre la fin du processus.
shell.Run """" & target & """", 0, False
