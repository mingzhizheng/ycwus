# Memory Hub - 启动服务
#   start.bat                 前台运行（窗口里看日志，Ctrl+C 停止）
#   start.ps1 -Background     后台运行并在崩溃后自动重启（开机自启用的就是这个）
param([switch]$Background)
. (Join-Path $PSScriptRoot 'common.ps1')

$cfg = Get-HubConfig
if (-not $cfg) { Write-Host '还没有配置，请先双击 setup.bat。' -ForegroundColor Red; exit 1 }
if (-not (Test-Path $cfg.vault)) { Write-Host "找不到 Obsidian 仓库：$($cfg.vault)，请重新运行 setup.bat。" -ForegroundColor Red; exit 1 }
$node = Get-NodePath
if (-not $node) { Write-Host '找不到 Node.js，请重新运行 setup.bat。' -ForegroundColor Red; exit 1 }

$port = [int]$cfg.port
if (Test-HubRunning $port) {
  Write-Host "Memory Hub 已经在运行：http://localhost:$port/"
  exit 0
}
Set-HubEnv $cfg
$server = Join-Path $HubRoot 'bin\server.js'

if (-not $Background) {
  & $node $server
  exit $LASTEXITCODE
}

# 后台守护：node 退出后 5 秒重启；连续快速崩溃 5 次则放弃（多半是配置问题，看 logs\server-error.log）
New-Item -ItemType Directory -Force -Path $HubLogDir | Out-Null
Set-Content -Path $HubPidFile -Value $PID
$fastCrashes = 0
while ($true) {
  $started = Get-Date
  $p = Start-Process -FilePath $node -ArgumentList "`"$server`"" -WorkingDirectory $HubRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $HubLogDir 'server.log') -RedirectStandardError (Join-Path $HubLogDir 'server-error.log')
  $p.WaitForExit()
  if (((Get-Date) - $started).TotalSeconds -lt 30) { $fastCrashes++ } else { $fastCrashes = 0 }
  Add-Content -Path (Join-Path $HubLogDir 'supervisor.log') -Value "$(Get-Date -Format s) node exited with code $($p.ExitCode)"
  if ($fastCrashes -ge 5) {
    Add-Content -Path (Join-Path $HubLogDir 'supervisor.log') -Value "$(Get-Date -Format s) crashed 5 times in a row, giving up"
    break
  }
  Start-Sleep -Seconds 5
}
Remove-Item $HubPidFile -Force -ErrorAction SilentlyContinue
