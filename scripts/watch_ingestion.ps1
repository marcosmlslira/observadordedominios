param(
    [string]$BaseUrl = "https://api.observadordedominios.com.br",
    [string]$Email = $env:OBS_ADMIN_EMAIL,
    [string]$Password = $env:OBS_ADMIN_PASSWORD,
    [int]$IntervalSeconds = 15,
    [switch]$Once
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-AccessToken {
    param(
        [string]$ApiBaseUrl,
        [string]$UserEmail,
        [string]$UserPassword
    )

    if (-not $UserEmail) {
        throw "Defina -Email ou a env OBS_ADMIN_EMAIL."
    }

    if (-not $UserPassword) {
        throw "Defina -Password ou a env OBS_ADMIN_PASSWORD."
    }

    $body = @{
        email = $UserEmail
        password = $UserPassword
    } | ConvertTo-Json -Compress

    return (
        Invoke-RestMethod `
            -Method Post `
            -Uri "$ApiBaseUrl/v1/auth/login" `
            -ContentType "application/json" `
            -Body $body
    ).access_token
}

function Get-Json {
    param(
        [string]$Uri,
        [string]$Token
    )

    return Invoke-RestMethod -Headers @{ Authorization = "Bearer $Token" } -Uri $Uri
}

function Format-IsoDate {
    param([object]$Value)

    if (-not $Value) {
        return "-"
    }

    try {
        return ([DateTimeOffset]::Parse($Value.ToString())).ToString("yyyy-MM-dd HH:mm:ss zzz")
    }
    catch {
        return $Value.ToString()
    }
}

function Or-Dash {
    param([object]$Value)

    if ($null -eq $Value -or $Value -eq "") {
        return "-"
    }

    return $Value
}

while ($true) {
    Clear-Host
    $token = Get-AccessToken -ApiBaseUrl $BaseUrl -UserEmail $Email -UserPassword $Password

    $health = Invoke-RestMethod -Uri "$BaseUrl/health"
    $cycleStatus = Get-Json -Uri "$BaseUrl/v1/ingestion/cycle-status" -Token $token
    $summary = Get-Json -Uri "$BaseUrl/v1/ingestion/summary" -Token $token
    $cycles = Get-Json -Uri "$BaseUrl/v1/ingestion/cycles?limit=1" -Token $token
    $runningRuns = Get-Json -Uri "$BaseUrl/v1/ingestion/runs?status=running&limit=20" -Token $token

    $lastCycle = $health.last_cycle
    $activeCycle = $cycleStatus.czds_cycle
    $latestCycle = $cycles.items | Select-Object -First 1
    $czds = $summary | Where-Object { $_.source -eq "czds" } | Select-Object -First 1
    $openintel = $summary | Where-Object { $_.source -eq "openintel" } | Select-Object -First 1
    $runningCount = @($runningRuns).Count
    $runningLabels = @($runningRuns | ForEach-Object { "$($_.source):$($_.tld)" })
    $progress = "-"

    if ($activeCycle.total_tlds) {
        $done = ($activeCycle.completed_tlds + $activeCycle.failed_tlds + $activeCycle.skipped_tlds)
        $percent = [math]::Round(($done / $activeCycle.total_tlds) * 100, 2)
        $progress = "$done/$($activeCycle.total_tlds) ($percent%)"
    }

    Write-Host "Observador de Dominios - Ingestion Monitor"
    Write-Host "Atualizado em: $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss zzz'))"
    Write-Host ""

    Write-Host "Health"
    Write-Host "  status:            $($health.status)"
    Write-Host "  last_cycle_id:     $($lastCycle.cycle_id)"
    Write-Host "  last_cycle_status: $($lastCycle.status)"
    Write-Host "  started_at:        $(Format-IsoDate $lastCycle.started_at)"
    Write-Host "  heartbeat_at:      $(Format-IsoDate $lastCycle.last_heartbeat_at)"
    Write-Host ""

    Write-Host "Cycle Status"
    Write-Host "  is_active:         $($activeCycle.is_active)"
    Write-Host "  current_tld:       $(Or-Dash $activeCycle.current_tld)"
    Write-Host "  progress:          $progress"
    Write-Host "  avg_tld_seconds:   $(Or-Dash $activeCycle.avg_tld_duration_seconds)"
    Write-Host "  eta:               $(Format-IsoDate $activeCycle.estimated_completion_at)"
    Write-Host ""

    Write-Host "Latest Cycle"
    Write-Host "  cycle_id:          $($latestCycle.cycle_id)"
    Write-Host "  status:            $($latestCycle.status)"
    Write-Host "  triggered_by:      $($latestCycle.triggered_by)"
    Write-Host "  started_at:        $(Format-IsoDate $latestCycle.started_at)"
    Write-Host "  finished_at:       $(Format-IsoDate $latestCycle.finished_at)"
    if ($latestCycle.active_databricks) {
        Write-Host "  dbx_source:        $($latestCycle.active_databricks.source)"
        Write-Host "  dbx_run_id:        $($latestCycle.active_databricks.databricks_run_id)"
        Write-Host "  dbx_state:         $(Or-Dash $latestCycle.active_databricks.databricks_result_state)"
        Write-Host "  dbx_tld_count:     $($latestCycle.active_databricks.tld_count)"
        Write-Host "  dbx_tlds_preview:  $(if (@($latestCycle.active_databricks.tlds_preview).Count) { $latestCycle.active_databricks.tlds_preview -join ', ' } else { '-' })"
        Write-Host "  dbx_url:           $(Or-Dash $latestCycle.active_databricks.databricks_run_url)"
    }
    Write-Host ""

    Write-Host "Sources"
    Write-Host "  czds:              running_now=$($czds.running_now) last_status=$($czds.last_status) last_run_at=$(Format-IsoDate $czds.last_run_at)"
    Write-Host "  openintel:         running_now=$($openintel.running_now) last_status=$($openintel.last_status) last_run_at=$(Format-IsoDate $openintel.last_run_at)"
    Write-Host "  running_runs:      $runningCount"
    Write-Host "  active_runs:       $(if ($runningLabels.Count) { $runningLabels -join ', ' } else { '-' })"

    if ($Once) {
        break
    }

    Start-Sleep -Seconds $IntervalSeconds
}
