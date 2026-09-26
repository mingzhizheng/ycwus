# Memory Hub - Windows 一键安装 / 重新配置（双击 setup.bat 运行，可重复运行）
# 做的事：检查 Node.js → 选择 Obsidian 仓库 → 是否开放给局域网（生成密钥、放行防火墙）
#         → 开机自启 → 立即启动 → 可选写入本机 Claude Desktop 配置 → 打印其他设备的连接方式
. (Join-Path $PSScriptRoot 'common.ps1')

Write-Host 'Memory Hub 安装向导（Obsidian 共享记忆）' -ForegroundColor Cyan
Get-ChildItem -Path $HubRoot -Recurse -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue

# ---------- 1. Node.js ----------
Write-Step '检查 Node.js'
$ver = Get-NodeVersion
if (-not $ver -or $ver -lt $HubMinNode) {
  $have = if ($ver) { "当前版本 $ver" } else { '未安装' }
  Write-Warn2 "需要 Node.js $HubMinNode 或更新版本（$have）。"
  if ((Get-Command winget -ErrorAction SilentlyContinue) -and (Read-YesNo '现在用 winget 自动安装 Node.js LTS？')) {
    winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
    Update-SessionPath
    $ver = Get-NodeVersion
  }
  if (-not $ver -or $ver -lt $HubMinNode) {
    Write-Host '    请从 https://nodejs.org 下载安装 LTS 版本，装好后重新运行 setup.bat。' -ForegroundColor Red
    exit 1
  }
}
Write-Ok "Node.js $ver ($(Get-NodePath))"

# ---------- 2. 配置 ----------
$cfg = Get-HubConfig
if (-not $cfg) { $cfg = [pscustomobject]@{ vault = ''; vaultName = ''; port = 8787; lan = $true; apiKey = '' } }

Write-Step '选择 Obsidian 仓库'
$vault = $null
while (-not $vault) {
  $prompt = if ($cfg.vault) { "    仓库路径（回车沿用 $($cfg.vault)；输入 ? 打开选择窗口）" } else { '    粘贴仓库文件夹路径（回车打开选择窗口）' }
  $ans = (Read-Host $prompt).Trim().Trim('"')
  if (-not $ans -and $cfg.vault) { $ans = $cfg.vault }
  if (-not $ans -or $ans -eq '?') {
    Add-Type -AssemblyName System.Windows.Forms
    $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
    $dlg.Description = '选择你的 Obsidian 仓库文件夹（里面有 .obsidian 文件夹的那个）'
    if ($dlg.ShowDialog() -ne 'OK') { continue }
    $ans = $dlg.SelectedPath
  }
  if (-not (Test-Path -LiteralPath $ans -PathType Container)) { Write-Warn2 "文件夹不存在：$ans"; continue }
  if (-not (Test-Path -LiteralPath (Join-Path $ans '.obsidian'))) {
    if (-not (Read-YesNo "这个文件夹里没有 .obsidian，看起来不是 Obsidian 仓库，仍然使用？" $false)) { continue }
  }
  $vault = (Resolve-Path -LiteralPath $ans).Path
}
$cfg.vault = $vault
Write-Ok $vault

Write-Step '局域网访问'
Write-Host '    开启后，同一 Wi-Fi 下的手机和其他电脑也能使用这份记忆（需要密钥）。'
$cfg.lan = Read-YesNo '开放给局域网？' ([bool]$cfg.lan)
if ($cfg.lan -and -not $cfg.apiKey) { $cfg.apiKey = New-ApiKey }
Save-HubConfig $cfg
Write-Ok "配置已保存到 $HubConfig"

# ---------- 3. 防火墙 + 网络类型 ----------
if ($cfg.lan) {
  Write-Step '放行防火墙端口'
  $rule = Get-NetFirewallRule -DisplayName $HubRuleName -ErrorAction SilentlyContinue
  if ($rule) {
    Write-Ok "防火墙规则“$HubRuleName”已存在"
  } else {
    Write-Host '    将弹出管理员确认窗口（UAC），用来添加一条只对“专用/域网络”生效的入站规则。'
    $cmd = "New-NetFirewallRule -DisplayName '$HubRuleName' -Direction Inbound -Protocol TCP -LocalPort $($cfg.port) -Action Allow -Profile Private,Domain | Out-Null"
    if (Invoke-Elevated $cmd) { Write-Ok "已放行 TCP $($cfg.port)（专用/域网络）" }
    else { Write-Warn2 '没有添加成功（可能取消了 UAC）。其他设备可能连不上，可以稍后重新运行 setup.bat。' }
  }
  try {
    $public = @(Get-NetConnectionProfile -ErrorAction Stop | Where-Object { $_.NetworkCategory -eq 'Public' -and $_.IPv4Connectivity -ne 'Disconnected' })
  } catch { $public = @() }
  foreach ($prof in $public) {
    Write-Warn2 "当前网络“$($prof.Name)”是“公用网络”，防火墙会拦住局域网访问。"
    if (Read-YesNo "这是你自己家里/公司的可信网络吗？是的话改为“专用网络”" $false) {
      if (Invoke-Elevated "Set-NetConnectionProfile -InterfaceIndex $($prof.InterfaceIndex) -NetworkCategory Private") { Write-Ok '已改为专用网络' }
      else { Write-Warn2 '修改失败，可以在 Windows 设置 → 网络 → 属性里手动改成“专用”。' }
    }
  }
}

# ---------- 4. 开机自启 ----------
Write-Step '开机自启'
$startPs1 = Join-Path $HubWinDir 'start.ps1'
$psArgs = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$startPs1`" -Background"
$autostart = $false
if (Read-YesNo '登录 Windows 时自动在后台启动 Memory Hub？') {
  try {
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $psArgs -WorkingDirectory $HubRoot
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero)
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $HubTaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
    Write-Ok "已创建计划任务“$HubTaskName”"
    $autostart = $true
  } catch {
    # 某些受管电脑不允许普通用户建计划任务，退回到“启动”文件夹快捷方式
    $lnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'Memory Hub.lnk'
    $sh = New-Object -ComObject WScript.Shell
    $s = $sh.CreateShortcut($lnk)
    $s.TargetPath = 'powershell.exe'
    $s.Arguments = $psArgs
    $s.WorkingDirectory = $HubRoot
    $s.WindowStyle = 7
    $s.Save()
    Write-Ok "已添加到启动文件夹：$lnk"
    $autostart = $true
  }
}

# ---------- 5. 启动 ----------
Write-Step '启动服务'
Stop-Hub ([int]$cfg.port)
Start-Sleep -Seconds 1
Start-Process powershell.exe -ArgumentList $psArgs -WindowStyle Hidden -WorkingDirectory $HubRoot
$ok = $false
for ($i = 0; $i -lt 20 -and -not $ok; $i++) { Start-Sleep -Milliseconds 500; $ok = Test-HubRunning ([int]$cfg.port) }
if ($ok) { Write-Ok "已启动：http://localhost:$($cfg.port)/" }
else {
  Write-Warn2 "启动失败，请查看 $(Join-Path $HubLogDir 'server-error.log')，或双击 start.bat 在前台运行看报错。"
}

# ---------- 6. 本机 Claude Desktop ----------
$claudeDir = Join-Path $env:APPDATA 'Claude'
if (Test-Path $claudeDir) {
  Write-Step '本机 Claude Desktop'
  if (Read-YesNo '把 Memory Hub 加到本机 Claude Desktop 的配置里？（会先备份原文件）') {
    $file = Join-Path $claudeDir 'claude_desktop_config.json'
    $conf = if (Test-Path $file) { Get-Content $file -Raw -Encoding UTF8 | ConvertFrom-Json } else { [pscustomobject]@{} }
    if (Test-Path $file) { Copy-Item $file "$file.bak-$(Get-Date -Format yyyyMMddHHmmss)" }
    if (-not $conf.PSObject.Properties['mcpServers']) { $conf | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{}) }
    $entry = [pscustomobject]@{
      command = Get-NodePath
      args    = @(Join-Path $HubRoot 'bin\mcp-stdio.js')
      env     = [pscustomobject]@{ MEMORY_URL = "http://127.0.0.1:$($cfg.port)"; MEMORY_API_KEY = [string]$cfg.apiKey }
    }
    $conf.mcpServers | Add-Member -NotePropertyName 'memory-hub' -NotePropertyValue $entry -Force
    # 不带 BOM 写回，Claude Desktop 读带 BOM 的 JSON 可能出错
    [IO.File]::WriteAllText($file, ($conf | ConvertTo-Json -Depth 20), (New-Object Text.UTF8Encoding $false))
    Write-Ok '已写入。完全退出 Claude Desktop（托盘图标 → Quit）后重新打开即可生效。'
  }
}

# ---------- 7. 连接信息 ----------
Write-Step '完成'
& (Join-Path $HubWinDir 'status.ps1')
if (-not $autostart) { Write-Host "`n没有开启开机自启：以后需要时双击 start.bat 启动。" -ForegroundColor Yellow }
