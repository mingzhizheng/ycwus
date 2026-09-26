# Memory Hub - 停止服务（开机自启仍保留，下次登录会再启动）
. (Join-Path $PSScriptRoot 'common.ps1')
$cfg = Get-HubConfig
$port = if ($cfg) { [int]$cfg.port } else { 8787 }
Stop-Hub $port
Start-Sleep -Seconds 1
if (Test-HubRunning $port) { Write-Host '服务仍在运行，可能是在另一个窗口前台启动的，请关掉那个窗口。' -ForegroundColor Yellow }
else { Write-Host 'Memory Hub 已停止。' -ForegroundColor Green }
