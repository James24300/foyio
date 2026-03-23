$ws = New-Object -ComObject WScript.Shell
$shortcut = $ws.CreateShortcut("C:\Users\James-William\Desktop\Foyio.lnk")
$shortcut.TargetPath = "pythonw.exe"
$shortcut.Arguments = "`"C:\Users\James-William\Desktop\Foyio\main.py`""
$shortcut.WorkingDirectory = "C:\Users\James-William\Desktop\Foyio"
$shortcut.Description = "Foyio - Gestion financiere"
$shortcut.IconLocation = "C:\Users\James-William\Desktop\Foyio\icons\foyio_logo.ico,0"
$shortcut.Save()
Write-Host "Raccourci mis a jour avec le logo !"
