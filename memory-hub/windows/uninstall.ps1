# Memory Hub - 卸载：停止服务、取消开机自启、删除防火墙规则。
# 不会动你的 Obsidian 仓库和 AI 记忆笔记；config.json 也保留，重新运行 setup.bat 即可恢复。
. (Join-Path $PSScriptRoot 'common.ps1')
$cfg = Get-HubConfig
$port = if ($cfg) { [int]$cfg.port } else { 8787 }

Write-Step '停止服务'
Stop-Hub $port
Write-Ok '已停止'

Write-Step '取消开机自启'
Unregister-ScheduledTask -TaskName $HubTaskName -Confirm:$false -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath('Startup')) 'Memory Hub.lnk') -Force -ErrorAction SilentlyContinue
Write-Ok '已取消'

if (Get-NetFirewallRule -DisplayName $HubRuleName -ErrorAction SilentlyContinue) {
  Write-Step '删除防火墙规则（需要管理员确认）'
  if (Invoke-Elevated "Remove-NetFirewallRule -DisplayName '$HubRuleName'") { Write-Ok '已删除' }
  else { Write-Warn2 '没有删除成功，可以在“高级安全 Windows Defender 防火墙”里手动删除“Memory Hub”规则。' }
}

Write-Host "`n如果把 Memory Hub 加进过 Claude Desktop，请在 %APPDATA%\Claude\claude_desktop_config.json 里删掉 memory-hub 那一项。" -ForegroundColor Yellow
