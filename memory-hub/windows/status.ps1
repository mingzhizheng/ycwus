# Memory Hub - 查看运行状态和连接方式（同时写入 connect-info.txt，方便复制到其他电脑）
. (Join-Path $PSScriptRoot 'common.ps1')

$cfg = Get-HubConfig
if (-not $cfg) { Write-Host '还没有配置，请先双击 setup.bat。' -ForegroundColor Red; exit 1 }
$port = [int]$cfg.port
$running = Test-HubRunning $port
$ips = @(Get-LanIPs)
$node = Get-NodePath
$stdio = Join-Path $HubRoot 'bin\mcp-stdio.js'

$lines = New-Object System.Collections.Generic.List[string]
function Add([string]$s = '') { $lines.Add($s) }

Add "Memory Hub 状态：$(if ($running) { '运行中' } else { '未运行（双击 start.bat 或重新登录）' })"
Add "Obsidian 仓库：$($cfg.vault)"
Add ''
Add '【本机】'
Add "  观察台：http://localhost:$port/"

if ($cfg.lan -and $ips.Count) {
  $ip = $ips[0]
  $url = "http://${ip}:$port"
  Add ''
  Add '【同一 Wi-Fi / 局域网里的其他设备】'
  foreach ($i in $ips) { Add "  观察台（手机/平板/电脑浏览器）：http://${i}:$port/" }
  Add "  访问密钥：$($cfg.apiKey)"
  Add ''
  Add '  ▸ 其他电脑的 Claude Code（命令行里运行一次）：'
  Add "    claude mcp add --transport http memory-hub $url/mcp -s user --header `"Authorization: Bearer $($cfg.apiKey)`""
  Add ''
  Add '  ▸ 其他电脑的 Claude Desktop / Cursor：先把整个 memory-hub 文件夹复制过去（需要 Node.js 22.13+），'
  Add '    再把下面的内容合并进 claude_desktop_config.json（Cursor 是 %USERPROFILE%\.cursor\mcp.json），路径改成那台电脑上的实际路径：'
  $remote = [ordered]@{ mcpServers = [ordered]@{ 'memory-hub' = [ordered]@{
        command = 'node'
        args    = @('C:\路径\memory-hub\bin\mcp-stdio.js')
        env     = [ordered]@{ MEMORY_URL = $url; MEMORY_API_KEY = $cfg.apiKey }
      } } }
  ($remote | ConvertTo-Json -Depth 6) -split "`n" | ForEach-Object { Add "    $_" }
  Add ''
  Add '  提醒：局域网内走的是 HTTP，只在家里/公司等可信 Wi-Fi 使用；建议在路由器里给本机设置固定 IP。'
} elseif ($cfg.lan) {
  Add ''
  Add '【局域网】没有检测到已连接的网络，连上 Wi-Fi 后再运行 status.bat 查看地址。'
} else {
  Add ''
  Add '【局域网】未开启。需要的话重新运行 setup.bat 并选择开启。'
}

Add ''
Add '【本机的 Claude Desktop】（setup 可以自动写入；手动配置时用这段）'
$localCfg = [ordered]@{ mcpServers = [ordered]@{ 'memory-hub' = [ordered]@{
      command = if ($node) { $node } else { 'node' }
      args    = @($stdio)
      env     = [ordered]@{ MEMORY_URL = "http://127.0.0.1:$port"; MEMORY_API_KEY = [string]$cfg.apiKey }
    } } }
($localCfg | ConvertTo-Json -Depth 6) -split "`n" | ForEach-Object { Add "    $_" }
Add ''
Add '【本机的 Claude Code】'
$keyHeader = if ($cfg.apiKey) { " --header `"Authorization: Bearer $($cfg.apiKey)`"" } else { '' }
Add "    claude mcp add --transport http memory-hub http://127.0.0.1:$port/mcp -s user$keyHeader"

$text = $lines -join "`r`n"
Write-Host $text
Set-Content -Path (Join-Path $HubWinDir 'connect-info.txt') -Value $text -Encoding UTF8
Write-Host "`n(以上内容已保存到 $(Join-Path $HubWinDir 'connect-info.txt'))" -ForegroundColor DarkGray
