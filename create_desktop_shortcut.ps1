$ErrorActionPreference = "Stop"

$appDirectory = [IO.Path]::GetFullPath($PSScriptRoot)
$python = Join-Path $appDirectory ".venv\Scripts\pythonw.exe"

if (-not (Test-Path -LiteralPath $python)) {
    $pythonCommand = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $python = $pythonCommand.Source
    } else {
        $pythonCommand = Get-Command python.exe -ErrorAction Stop
        $python = $pythonCommand.Source
    }
}

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "arkBrowse.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $python
$shortcut.Arguments = '"' + (Join-Path $appDirectory "arkbrowse.py") + '"'
$shortcut.WorkingDirectory = $appDirectory
$shortcut.Description = "arkBrowse privacy-first web browser"
$iconPath = Join-Path $appDirectory "icon.ico"
if (Test-Path -LiteralPath $iconPath) {
    $shortcut.IconLocation = "$iconPath,0"
}
$shortcut.Save()

Write-Host "Created desktop shortcut:"
Write-Host "  $shortcutPath"