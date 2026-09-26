# Memory Hub - Windows 脚本共用函数（被 setup / start / stop / status / uninstall 引用）
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}

$HubWinDir    = $PSScriptRoot
$HubRoot      = Split-Path $HubWinDir -Parent
$HubConfig    = Join-Path $HubWinDir 'config.json'
$HubLogDir    = Join-Path $HubWinDir 'logs'
$HubPidFile   = Join-Path $HubWinDir 'logs\supervisor.pid'
$HubTaskName  = 'Memory Hub'
$HubRuleName  = 'Memory Hub'
$HubMinNode   = [version]'22.13.0'   # node:sqlite 从 22.13 起无需实验参数

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    [OK] $msg" -ForegroundColor Green }
function Write-Warn2($msg){ Write-Host "    [!] $msg" -ForegroundColor Yellow }

function Read-YesNo([string]$question, [bool]$default = $true) {
  $hint = if ($default) { '[Y/n]' } else { '[y/N]' }
  $ans = Read-Host "    $question $hint"
  if ([string]::IsNullOrWhiteSpace($ans)) { return $default }
  return $ans.Trim().ToLower().StartsWith('y')
}

function Get-HubConfig {
  if (-not (Test-Path $HubConfig)) { return $null }
  return Get-Content $HubConfig -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Save-HubConfig($cfg) {
  $cfg | ConvertTo-Json -Depth 5 | Set-Content -Path $HubConfig -Encoding UTF8
}

function Get-NodePath {
  $cmd = Get-Command node -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  return $null
}

function Get-NodeVersion {
  $node = Get-NodePath
  if (-not $node) { return $null }
  $v = (& $node -v) -replace '^v', ''
  try { return [version]$v } catch { return $null }
}

function Update-SessionPath {
  $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
  $user = [Environment]::GetEnvironmentVariable('Path', 'User')
  $env:Path = "$machine;$user"
}

# 有默认网关、已连接的网卡的 IPv4 地址 = 同一 Wi-Fi / 局域网里别人能访问的地址
function Get-LanIPs {
  try {
    return @(Get-NetIPConfiguration -ErrorAction Stop |
      Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } |
      ForEach-Object { $_.IPv4Address } | ForEach-Object { $_.IPAddress } |
      Where-Object { $_ -and $_ -notlike '169.254.*' })
  } catch { return @() }
}

function Test-HubRunning([int]$port) {
  try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/health" -UseBasicParsing -TimeoutSec 2
    return $r.StatusCode -eq 200
  } catch { return $false }
}

function Set-HubEnv($cfg) {
  $lan = [bool]$cfg.lan
  $ip = @(Get-LanIPs) | Select-Object -First 1
  $env:OBSIDIAN_VAULT = $cfg.vault
  $env:PORT = [string]$cfg.port
  $env:HOST = if ($lan) { '0.0.0.0' } else { '127.0.0.1' }
  $env:MEMORY_API_KEY = if ($cfg.apiKey) { $cfg.apiKey } else { '' }
  $env:PUBLIC_URL = if ($lan -and $ip) { "http://${ip}:$($cfg.port)" } else { "http://localhost:$($cfg.port)" }
  if ($cfg.vaultName) { $env:OBSIDIAN_VAULT_NAME = $cfg.vaultName }
}

function New-ApiKey {
  $bytes = New-Object byte[] 24
  [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  return (($bytes | ForEach-Object { $_.ToString('x2') }) -join '')
}

# 以管理员身份执行一段命令（会弹出 UAC 确认）；成功返回 $true
function Invoke-Elevated([string]$command) {
  # -EncodedCommand 避免 Start-Process 在 PowerShell 5.1 下拆散带空格/引号的参数
  $script = "`$ErrorActionPreference = 'Stop'; try { $command } catch { exit 1 }"
  $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($script))
  try {
    $p = Start-Process powershell.exe -Verb RunAs -Wait -PassThru -WindowStyle Hidden `
      -ArgumentList "-NoProfile -ExecutionPolicy Bypass -EncodedCommand $encoded"
    return $p.ExitCode -eq 0
  } catch {
    return $false
  }
}

function Stop-Hub([int]$port) {
  if (Test-Path $HubPidFile) {
    $supervisor = Get-Content $HubPidFile -ErrorAction SilentlyContinue
    if ($supervisor) { Stop-Process -Id ([int]$supervisor) -Force -ErrorAction SilentlyContinue }
    Remove-Item $HubPidFile -Force -ErrorAction SilentlyContinue
  }
  try {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop |
      ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
  } catch {}
}
