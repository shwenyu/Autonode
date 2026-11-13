# 卸载：停止进程 + 删除自启/桌面快捷方式（配置和日志保留）
$ErrorActionPreference = "Continue"
$Dest = Join-Path $env:APPDATA "autonode"
$Startup = [Environment]::GetFolderPath("Startup")
$Desktop = [Environment]::GetFolderPath("Desktop")

Write-Host "==> 停止进程"
Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe'" |
    Where-Object { $_.CommandLine -like "*autonode.py*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Remove-Item (Join-Path $Startup "Autonode.lnk") -ErrorAction SilentlyContinue
Remove-Item (Join-Path $Desktop "Clash 节点控制台.url") -ErrorAction SilentlyContinue

Write-Host "已停止并移除快捷方式。"
Write-Host "配置与日志仍在：$Dest"
Write-Host "彻底删除：Remove-Item -Recurse -Force `"$Dest`""
