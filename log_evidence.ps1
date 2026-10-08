param(
    [string]$step,
    [string]$command
)
$date = Get-Date -Format "yyyy-MM-dd"
$dir = "evidence/$date"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$logFile = "$dir/$step.log"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$gitHash = git rev-parse HEAD 2>$null
if (-not $gitHash) { $gitHash = "NO_GIT" }
"---" | Out-File -FilePath $logFile -Encoding utf8
"Command: $command" | Out-File -FilePath $logFile -Encoding utf8 -Append
"Timestamp: $timestamp" | Out-File -FilePath $logFile -Encoding utf8 -Append
"Git Commit: $gitHash" | Out-File -FilePath $logFile -Encoding utf8 -Append
"---" | Out-File -FilePath $logFile -Encoding utf8 -Append
Invoke-Expression $command 2>&1 | Tee-Object -FilePath $logFile -Append
