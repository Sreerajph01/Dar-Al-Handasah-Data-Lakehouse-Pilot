param(
    [string]$step,
    [string]$command
)
$ErrorActionPreference = 'Continue'
$date = Get-Date -Format "yyyy-MM-dd"
$dir = "evidence/$date"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$logFile = "$dir/$step.log"
$timestamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss.fff zzz')
$gitHash = git rev-parse HEAD 2>$null
if (-not $gitHash) { $gitHash = "NO_GIT" }
"---" | Out-File -FilePath $logFile -Encoding utf8
"Command: $command" | Out-File -FilePath $logFile -Encoding utf8 -Append
"Timestamp: $timestamp" | Out-File -FilePath $logFile -Encoding utf8 -Append
"Git Commit: $gitHash" | Out-File -FilePath $logFile -Encoding utf8 -Append
"---" | Out-File -FilePath $logFile -Encoding utf8 -Append
$Error.Clear()
$global:LASTEXITCODE = 0
$output = @(& { Invoke-Expression $command } 2>&1)
$exitCode = 0
if ($LASTEXITCODE -is [int] -and $LASTEXITCODE -ne 0) { $exitCode = $LASTEXITCODE }
elseif ($Error.Count -gt 0) { $exitCode = 1 }
$output | ForEach-Object { $_.ToString() } | Tee-Object -FilePath $logFile -Append
"Exit code: $exitCode" | Tee-Object -FilePath $logFile -Append
exit $exitCode
