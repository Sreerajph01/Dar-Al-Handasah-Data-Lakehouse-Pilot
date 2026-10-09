[CmdletBinding()]
param(
    [Parameter(Position = 0)][string]$Target = 'help',
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$script:Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$script:EvidenceDay = Join-Path $script:Root ('evidence/' + (Get-Date -Format 'yyyy-MM-dd'))
$script:ComposeFull = @('-f','docker-compose.yml','-f','docker-compose.uc1.yml','-f','docker-compose.uc2.yml','-f','docker-compose.governance.yml','-f','docker-compose.observability.yml','-f','docker-compose.cicd.yml')
$script:ComposeLite = @('-f','docker-compose.yml','-f','docker-compose.uc1.yml','-f','docker-compose.uc2.yml')

function Invoke-Logged {
    param([string]$Name,[string]$Command,[scriptblock]$Action)
    New-Item -ItemType Directory -Force -Path $script:EvidenceDay | Out-Null
    $path = Join-Path $script:EvidenceDay ($Name + '.log')
    $stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss.fff zzz')
    $commit = (& git -C $script:Root rev-parse HEAD 2>$null | Select-Object -First 1)
    if (-not $commit) { $commit = 'NO_GIT' }
    $script:LastExitCode = 0
    $output = @()
    try {
        $output = @(& $Action 2>&1 | ForEach-Object { $_.ToString() })
        if ($global:LASTEXITCODE -is [int]) { $script:LastExitCode = $global:LASTEXITCODE }
    } catch {
        $output += $_.ToString()
        $script:LastExitCode = 1
    }
    $content = @('---',"Command: $Command","Timestamp: $stamp","Git Commit: $commit",'---') + $output + "Exit code: $($script:LastExitCode)"
    Set-Content -LiteralPath $path -Value $content -Encoding UTF8
    $output | ForEach-Object { Write-Host $_ }
    Write-Host "Exit code: $($script:LastExitCode)"
    if ($script:LastExitCode -ne 0) { throw "Command failed with exit code $($script:LastExitCode); see $path" }
}

function Invoke-Docker {
    param([string]$Name,[string[]]$Arguments)
    $line = 'docker ' + ($Arguments -join ' ')
    Invoke-Logged -Name $Name -Command $line -Action { & docker @Arguments }
}

function Read-DotEnv {
    $file = Join-Path $script:Root '.env'
    if (-not (Test-Path $file)) { throw '.env is absent; run .\dar.ps1 up to generate it.' }
    foreach ($line in Get-Content -LiteralPath $file) {
        if ($line -match '^\s*([^#=\s]+)\s*=(.*)$') {
            $value = $Matches[2].Trim()
            if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            Set-Item -Path ('Env:' + $Matches[1]) -Value $value
        }
    }
}

function Ensure-Configs {
    if (-not (Test-Path (Join-Path $script:Root '.env'))) {
        Invoke-Docker -Name 'generate-secrets' -Arguments @('run','--rm','-v',"${script:Root}:/repo",'-w','/repo','python:3.11-slim','bash','scripts/generate-secrets.sh')
    }
    Invoke-Docker -Name 'generate-configs' -Arguments @('run','--rm','--env-file','.env','-v',"${script:Root}:/repo",'-w','/repo','python:3.11-slim','bash','-lc','apt-get update -qq && apt-get install -y -qq gettext-base && bash scripts/generate-configs.sh')
}

function Invoke-Compose {
    param([string]$Name,[string[]]$Compose,[string[]]$Arguments)
    $all = @('compose','--env-file','.env','--profile','*') + $Compose + $Arguments
    Invoke-Docker -Name $Name -Arguments $all
}

function Test-ComposeEnvFile {
    param([string[]]$Compose)
    $all = @('compose','--env-file','.env','--profile','*') + $Compose + @('config','--format','json')
    $config = (& docker @all | ConvertFrom-Json)
    $actual = [string]$config.services.opensearch.environment.OPENSEARCH_JAVA_OPTS
    if ($actual -ne '-Xms1g -Xmx1g') {
        throw "Compose did not parse quoted OPENSEARCH_JAVA_OPTS correctly. Actual value: [$actual]"
    }
    Write-Output 'Compose --env-file parsed quoted OPENSEARCH_JAVA_OPTS correctly.'
}

function Test-HostPortConflicts {
    param([string[]]$Compose)
    $all = @('compose','--env-file','.env','--profile','*') + $Compose + @('config','--format','json')
    $config = (& docker @all | ConvertFrom-Json)
    $projectIds = @(& docker ps -aq --filter 'label=com.docker.compose.project=dar-lakehouse')
    $rows = New-Object System.Collections.Generic.List[object]
    foreach ($property in $config.services.psobject.Properties) {
        $service = $property.Name
        foreach ($port in @($property.Value.ports)) {
            if ($null -eq $port) { continue }
            $published = [string]$port.published
            if ([string]::IsNullOrWhiteSpace($published)) { continue }
            $owners = @(& docker ps -q --filter "publish=$published")
            $external = @($owners | Where-Object { $_ -notin $projectIds })
            $state = 'AVAILABLE'; $owner = ''
            if ($external.Count -gt 0) {
                $state = 'CONFLICT'
                $owner = (& docker ps --filter "publish=$published" --format '{{.Names}} ({{.Image}})' | Where-Object { $_ }) -join '; '
            } elseif ($owners.Count -gt 0) {
                $state = 'OWNED_BY_PROJECT'
                $owner = (& docker ps --filter "publish=$published" --format '{{.Names}}' | Where-Object { $_ }) -join '; '
            } else {
                $listener = Get-NetTCPConnection -State Listen -LocalPort ([int]$published) -ErrorAction SilentlyContinue | Select-Object -First 1
                if ($listener) {
                    $state = 'CONFLICT'
                    $process = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
                    $owner = if ($process) { "$($process.ProcessName) (PID $($listener.OwningProcess))" } else { "PID $($listener.OwningProcess)" }
                }
            }
            $rows.Add([pscustomobject]@{Service=$service;HostPort=$published;ContainerPort=$port.target;Status=$state;Owner=$owner})
        }
    }
    $table = $rows | Sort-Object HostPort, Service | Format-Table -AutoSize | Out-String -Width 240
    Write-Host $table
    Write-Output $table
    $conflicts = @($rows | Where-Object { $_.Status -eq 'CONFLICT' })
    if ($conflicts.Count -gt 0) {
        throw 'Host port conflict detected. No container was stopped; resolve the listed conflict and retry.'
    }
}

function Invoke-Seed {
    Read-DotEnv
    $environment = if ($env:ENVIRONMENT) { $env:ENVIRONMENT } else { 'dev' }
    Invoke-Docker -Name 'seed-opentofu' -Arguments @('run','--rm','--network','dar-lakehouse_default','-e',"AWS_ACCESS_KEY_ID=$env:S3_ACCESS_KEY",'-e',"AWS_SECRET_ACCESS_KEY=$env:S3_SECRET_KEY",'-e',"TF_VAR_s3_access_key=$env:S3_ACCESS_KEY",'-e',"TF_VAR_s3_secret_key=$env:S3_SECRET_KEY",'-v',"${script:Root}\tofu\envs\$environment`:/workspace",'-w','/workspace','--entrypoint','sh',"ghcr.io/opentofu/opentofu:$($env:TOFU_VERSION)",'-c','tofu init && tofu apply -auto-approve')
    try {
        Invoke-Logged -Name 'seed-lakekeeper-bootstrap' -Command 'POST http://localhost:8181/management/v1/bootstrap' -Action { Invoke-RestMethod -Uri 'http://localhost:8181/management/v1/bootstrap' -Method Post -Body '{"accept-terms-of-use":true}' -ContentType 'application/json' | ConvertTo-Json -Depth 12 }
    } catch { Write-Host 'Lakekeeper bootstrap request returned an error; checking catalog creation next.' }
    Invoke-Docker -Name 'seed-iceberg-catalog' -Arguments @('run','--rm','--network','dar-lakehouse_default','--env-file','.env','-e','S3_ENDPOINT=http://seaweedfs-s3:8333','-e','LAKEKEEPER_CATALOG_URI=http://lakekeeper:8181','-v',"${script:Root}:/repo",'-w','/repo','python:3.11-slim','bash','-lc','pip install --disable-pip-version-check boto3==1.35.44 requests==2.32.3 && python init_all.py && python scripts/setup-iceberg-catalog.py')
    Invoke-Docker -Name 'seed-airflow-connections' -Arguments @('exec','dar-airflow-webserver','bash','-lc','airflow connections list')
    Invoke-Docker -Name 'seed-dw' -Arguments @('run','--rm','--network','dar-lakehouse_default','--env-file','.env','-v',"${script:Root}:/repo",'-w','/repo','python:3.11-slim','bash','-lc','pip install --disable-pip-version-check psycopg2-binary==2.9.9 && python uc2-warehouse-migration/sources/dar_dw/seed.py --scale small')
}

function Test-Http {
    param([string]$Name,[string]$Url,[string]$Method='GET',[hashtable]$Headers=@{},[string]$Username,[string]$Password,[int]$Expected=200)
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $state = 'FAIL'; $detail = ''
    try {
        $params = @{ Uri=$Url; Method=$Method; TimeoutSec=15; UseBasicParsing=$true; Headers=$Headers; ErrorAction='Stop' }
        if ($Username) { $params.Credential = New-Object Management.Automation.PSCredential($Username,(ConvertTo-SecureString $Password -AsPlainText -Force)) }
        $response = Invoke-WebRequest @params
        $code = [int]$response.StatusCode
        if ($code -eq $Expected) { $state='PASS'; $detail="HTTP $code" } else { $detail="HTTP $code, expected $Expected" }
    } catch {
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) { $detail = 'HTTP ' + [int]$_.Exception.Response.StatusCode } else { $detail=$_.Exception.Message }
    }
    $watch.Stop()
    [pscustomobject]@{Service=$Name;Check=$Url;Result=$state;Time=('{0} ms' -f $watch.ElapsedMilliseconds);Detail=$detail}
}

function Test-ContainerRunning {
    param([string]$Name,[string]$Container)
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $result = (& docker inspect --format '{{.State.Status}}' $Container 2>$null | Select-Object -First 1)
    $code = $LASTEXITCODE
    $state = if ($code -eq 0 -and $result -eq 'running') { 'PASS' } else { 'FAIL' }
    $watch.Stop()
    [pscustomobject]@{Service=$Name;Check='container running';Result=$state;Time=('{0} ms' -f $watch.ElapsedMilliseconds);Detail=[string]$result}
}

function Invoke-Health {
    Read-DotEnv
    $rows = New-Object System.Collections.Generic.List[object]
    $checks = @(
        @('SeaweedFS master','http://localhost:9333/cluster/status'),@('SeaweedFS volume','http://localhost:8080/status'),@('SeaweedFS filer','http://localhost:8888/'),
        @('SeaweedFS S3 gateway','http://localhost:8333/'),@('Lakekeeper','http://localhost:8181/health'),@('Trino','http://localhost:18080/v1/info'),
        @('OPA','http://localhost:8282/health'),@('Keycloak','http://localhost:8444/health/ready'),@('Airflow webserver','http://localhost:8079/health'),
        @('D365 mock','http://localhost:8090/health'),@('SharePoint mock','http://localhost:8091/health'),@('Data API','http://localhost:8092/health'),
        @('Search API','http://localhost:8093/health'),@('NL2SQL','http://localhost:8095/health'),@('Tika','http://localhost:9998/version'),
        @('Ollama',"http://localhost:$($env:OLLAMA_PORT)/api/tags"),@('OpenSearch Dashboards','http://localhost:5601/api/status'),@('OpenMetadata','http://localhost:8585/api/v1/system/status'),
        @('Kong Admin','http://localhost:8001/status'),@('Superset','http://localhost:8088/health'),@('Mailpit','http://localhost:8025/api/v1/info'),
        @('Prometheus','http://localhost:9090/-/ready'),@('Grafana','http://localhost:3002/api/health'),@('cAdvisor','http://localhost:8094/healthz'),@('Gitea','http://localhost:3001/api/healthz')
    )
    foreach ($entry in $checks) { $rows.Add((Test-Http -Name $entry[0] -Url $entry[1])) }
    foreach ($entry in @(@('Postgres metadata','dar-postgres-meta'),@('Postgres Airflow','dar-postgres-airflow'),@('Postgres warehouse','dar-postgres-dw'))) {
        $start=Get-Date; $out=& docker exec $entry[1] pg_isready -h 127.0.0.1 2>&1; $code=$LASTEXITCODE
        $rows.Add([pscustomobject]@{Service=$entry[0];Check='pg_isready';Result=$(if($code -eq 0){'PASS'}else{'FAIL'});Time=('{0} ms' -f ((Get-Date)-$start).TotalMilliseconds);Detail=($out -join ' ')})
    }
    $rows.Add((Test-ContainerRunning -Name 'OpenMetadata ingestion' -Container 'dar-openmetadata-ingestion'))
    $rows.Add((Test-ContainerRunning -Name 'Fluent Bit' -Container 'dar-fluent-bit'))
    $rows.Add((Test-ContainerRunning -Name 'Gitea runner' -Container 'dar-gitea-runner'))
    $rows.Add((Test-ContainerRunning -Name 'Samba' -Container 'dar-samba'))
    $table = $rows | Format-Table -AutoSize | Out-String -Width 220
    Invoke-Logged -Name 'health' -Command '.\dar.ps1 health (HTTP readiness and Postgres application probes)' -Action { Write-Output $table; if (($rows | Where-Object Result -eq 'FAIL').Count -gt 0) { $global:LASTEXITCODE=1 } else { $global:LASTEXITCODE=0 } }
}

function Show-Help {
    @('help','up','up-lite','down','reset -Force','seed','health','verify','simulate-day','backup','restore','licenses','lint-branding','lint-code','lint','venv','generate-secrets','tofu-init','tofu-plan','tofu-apply','s3-conformance','smoke-m1','verify-opensearch','verify-opa','traceability','smoke-m2','smoke-m3','benchmark','demo','clean') | ForEach-Object { Write-Host ('.\dar.ps1 ' + $_) }
}

Push-Location $script:Root
try {
    switch ($Target.ToLowerInvariant()) {
        'help' { Show-Help }
        'up' { Ensure-Configs; Invoke-Logged -Name 'preflight-ports-full' -Command 'docker compose --env-file .env config + host port conflict check' -Action { Test-ComposeEnvFile -Compose $script:ComposeFull; Test-HostPortConflicts -Compose $script:ComposeFull }; Invoke-Compose -Name 'up-full' -Compose $script:ComposeFull -Arguments @('up','-d','--build') }
        'up-lite' { Ensure-Configs; Invoke-Logged -Name 'preflight-ports-lite' -Command 'docker compose --env-file .env config + host port conflict check' -Action { Test-ComposeEnvFile -Compose $script:ComposeLite; Test-HostPortConflicts -Compose $script:ComposeLite }; Invoke-Compose -Name 'up-lite' -Compose $script:ComposeLite -Arguments @('up','-d','--build') }
        'down' { Invoke-Compose -Name 'down' -Compose $script:ComposeFull -Arguments @('down','--remove-orphans') }
        'reset' {
            if (-not $Force) { throw 'Reset deletes named volumes. Review the list and rerun with .\dar.ps1 reset -Force.' }
            Invoke-Docker -Name 'reset-volumes-preview' -Arguments @('volume','ls','--filter','label=com.docker.compose.project=dar-lakehouse')
            Invoke-Compose -Name 'reset-delete-volumes' -Compose $script:ComposeFull -Arguments @('down','-v','--remove-orphans')
        }
        'seed' { Invoke-Seed }
        'health' { Invoke-Health }
        'verify' { Invoke-Health; Invoke-Docker -Name 'verify-opa' -Arguments @('run','--rm','-v',"${script:Root}\infra\opa:/policies:ro",'openpolicyagent/opa:0.68.0','test','/policies','-v') }
        'simulate-day' { Read-DotEnv; Invoke-Docker -Name 'simulate-day' -Arguments @('run','--rm','--network','dar-lakehouse_default','--env-file','.env','-v',"${script:Root}:/repo",'-w','/repo','python:3.11-slim','bash','-lc','pip install --disable-pip-version-check psycopg2-binary==2.9.9 && python data-gen/uc2/simulate_day.py') }
        'backup' { Invoke-Docker -Name 'backup' -Arguments @('run','--rm','-v',"${script:Root}:/repo",'-w','/repo','python:3.11-slim','bash','-lc','echo Backup implementation required: scripts/backup.sh is absent; exit 2') }
        'restore' { Invoke-Docker -Name 'restore' -Arguments @('run','--rm','-v',"${script:Root}:/repo",'-w','/repo','python:3.11-slim','bash','-lc','echo Restore implementation required: scripts/restore.sh is absent; exit 2') }
        'licenses' { Invoke-Docker -Name 'licenses' -Arguments @('run','--rm','-v',"${script:Root}:/repo",'-w','/repo','python:3.11-slim','bash','-lc','pip install --disable-pip-version-check pip-licenses==5.0.0 requests==2.32.3 && python tests/licence_gate/check_licences.py') }
        'lint-branding' { Invoke-Docker -Name 'lint-branding' -Arguments @('run','--rm','-v',"${script:Root}:/repo",'-w','/repo','python:3.11-slim','bash','-lc','bash tests/branding_lint/check_branding.sh') }
        'lint-code' { Invoke-Docker -Name 'lint-code' -Arguments @('run','--rm','-v',"${script:Root}:/repo",'-w','/repo','ghcr.io/astral-sh/ruff:0.7.0','check','--select=E,W,F','--ignore=E501','.') }
        'lint' { & $MyInvocation.MyCommand.Path lint-branding; & $MyInvocation.MyCommand.Path lint-code }
        'generate-secrets' { if (Test-Path '.env') { Write-Host '.env already exists; preserved.' } else { Invoke-Docker -Name 'generate-secrets' -Arguments @('run','--rm','-v',"${script:Root}:/repo",'-w','/repo','python:3.11-slim','bash','scripts/generate-secrets.sh') } }
        'rotate-s3-identity' { Invoke-Docker -Name 'rotate-s3-identity' -Arguments @('run','--rm','-v',"${script:Root}:/repo",'-w','/repo','python:3.11-slim','bash','scripts/generate-secrets.sh','--rotate-s3'); Ensure-Configs }
        'test-env-file' { Invoke-Logged -Name 'test-env-file' -Command 'docker compose --env-file .env config confirms quoted OpenSearch heap setting' -Action { Test-ComposeEnvFile -Compose $script:ComposeFull } }
        'venv' { Write-Host 'Tooling runs in pinned containers; no host virtualenv is required.' }
        'tofu-init' { Read-DotEnv; Invoke-Docker -Name 'tofu-init' -Arguments @('run','--rm','-v',"${script:Root}\tofu\envs\dev:/workspace",'-w','/workspace',"ghcr.io/opentofu/opentofu:$($env:TOFU_VERSION)",'init') }
        'tofu-plan' { Read-DotEnv; Invoke-Docker -Name 'tofu-plan' -Arguments @('run','--rm','-v',"${script:Root}\tofu\envs\dev:/workspace",'-w','/workspace',"ghcr.io/opentofu/opentofu:$($env:TOFU_VERSION)",'plan') }
        'tofu-apply' { Invoke-Seed }
        's3-conformance' { Read-DotEnv; Invoke-Docker -Name 's3-conformance' -Arguments @('run','--rm','--network','dar-lakehouse_default','--env-file','.env','-e','AWS_ENDPOINT_URL=http://seaweedfs-s3:8333','-v',"${script:Root}:/repo",'-w','/repo','python:3.11-slim','bash','-lc','pip install --disable-pip-version-check -r tests/s3_conformance/requirements.txt && python tests/s3_conformance/test_s3_conformance.py') }
        'smoke-m1' { Read-DotEnv; Invoke-Docker -Name 'smoke-m1' -Arguments @('run','--rm','--network','dar-lakehouse_default','--env-file','.env','-v',"${script:Root}:/repo",'-w','/repo','python:3.11-slim','bash','-lc','pip install --disable-pip-version-check trino==0.329.0 requests==2.32.3 && python tests/smoke/test_m1_iceberg.py') }
        'verify-opensearch' { Invoke-Docker -Name 'verify-opensearch' -Arguments @('run','--rm','-v',"${script:Root}:/repo",'-w','/repo','python:3.11-slim','bash','-lc','pip install --disable-pip-version-check requests==2.32.3 && python tests/smoke/test_opensearch_knn.py') }
        'verify-opa' { Invoke-Docker -Name 'verify-opa' -Arguments @('run','--rm','-v',"${script:Root}\infra\opa:/policies:ro",'openpolicyagent/opa:0.68.0','test','/policies','-v') }
        'traceability' { Invoke-Docker -Name 'traceability' -Arguments @('run','--rm','-v',"${script:Root}:/repo",'-w','/repo','python:3.11-slim','python','tests/traceability/check_traceability.py') }
        'smoke-m2' { Invoke-Docker -Name 'smoke-m2' -Arguments @('run','--rm','--network','dar-lakehouse_default','--env-file','.env','-e','PG_DW_HOST=postgres-dw','-e','TRINO_HOST=trino','-v',"${script:Root}:/repo",'-w','/repo','python:3.11-slim','bash','-lc','pip install --disable-pip-version-check pytest==8.3.3 trino==0.329.0 requests==2.32.3 psycopg2-binary==2.9.9 && pytest -q tests/uc2/test_lakekeeper_contract.py && python tests/uc2/test_m2_gate.py') }
        'smoke-m3' { Invoke-Docker -Name 'smoke-m3' -Arguments @('run','--rm','--network','dar-lakehouse_default','--env-file','.env','-e','PG_DW_HOST=postgres-dw','-e','TRINO_HOST=trino','-v',"${script:Root}:/repo",'-w','/repo','python:3.11-slim','bash','-lc','pip install --disable-pip-version-check pytest==8.3.3 trino==0.329.0 requests==2.32.3 psycopg2-binary==2.9.9 && python tests/uc2/test_m3_gate.py') }
        'benchmark' { Invoke-Compose -Name 'benchmark-up' -Compose (@('-f','docker-compose.yml','-f','docker-compose.benchmark.yml')) -Arguments @('up','-d'); Invoke-Docker -Name 'benchmark-report' -Arguments @('run','--rm','-v',"${script:Root}:/repo",'-w','/repo','python:3.11-slim','python','benchmark/report_generator.py') }
        'smoke-uc1' { Invoke-Docker -Name 'smoke-uc1' -Arguments @('run','--rm','--network','dar-lakehouse_default','--env-file','.env','-e','OPENSEARCH_HOST=http://opensearch:9200','-v',"${script:Root}:/repo",'-w','/repo','python:3.11-slim','bash','-lc','pip install --disable-pip-version-check pytest==8.3.3 opensearch-py==2.7.1 httpx==0.27.2 ezdxf==1.3.4 && pytest -v tests/uc1/test_uc1_search_gate.py') }
        'smoke-uc2' { Invoke-Docker -Name 'smoke-uc2' -Arguments @('run','--rm','--network','dar-lakehouse_default','--env-file','.env','-e','TRINO_HOST=trino','-e','TRINO_PORT=8080','-e','DATA_API_URL=http://dar-data-api:8000','-e','NL2SQL_URL=http://dar-nl2sql:8000','-v',"${script:Root}:/repo",'-w','/repo','python:3.11-slim','bash','-lc','pip install --disable-pip-version-check pytest==8.3.3 trino==0.329.0 requests==2.32.3 sqlglot==25.19.0 && pytest -v tests/uc2/test_uc2_migration_gate.py') }
        'demo' { Invoke-Docker -Name 'demo' -Arguments @('run','--rm','--network','dar-lakehouse_default','--env-file','.env','-e','SEARCH_API_URL=http://dar-search-api:8000','-e','DATA_API_URL=http://dar-data-api:8000','-e','NL2SQL_URL=http://dar-nl2sql:8000','-e','TRINO_HOST=trino','-e','TRINO_PORT=8080','-v',"${script:Root}:/repo",'-w','/repo','python:3.11-slim','bash','-lc','pip install --disable-pip-version-check requests==2.32.3 trino==0.329.0 && python scripts/demo_runner.py') }
        'clean' { if (Test-Path '.venv') { Remove-Item -Recurse -Force '.venv' }; if (Test-Path '.pytest_cache') { Remove-Item -Recurse -Force '.pytest_cache' }; Write-Host 'Cleaned local test artifacts.' }
        default { throw "Unknown target '$Target'. Run .\dar.ps1 help." }
    }
} finally { Pop-Location }
