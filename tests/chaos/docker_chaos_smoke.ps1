param(
    [ValidateSet("redis", "fuseki", "worker", "api", "postgres", "otel-collector")]
    [string]$Service = "redis",

    [ValidateSet("pause", "unpause", "restart")]
    [string]$Action = "pause",

    [string]$BaseUrl = "http://localhost:8000",

    [int]$RecoveryTimeoutSeconds = 60,

    [int]$PollIntervalSeconds = 5
)

$ErrorActionPreference = "Stop"

function Invoke-HealthCheck {
    param([string]$Url)

    try {
        $response = Invoke-RestMethod -Uri "$Url/api/v1/health" -Method Get -TimeoutSec 10
        Write-Host "health status: $($response.status)"
        return $response
    }
    catch {
        Write-Host "health check failed: $($_.Exception.Message)"
        return $null
    }
}

function Wait-Healthy {
    param(
        [string]$Url,
        [int]$TimeoutSeconds,
        [int]$IntervalSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $response = Invoke-HealthCheck -Url $Url
        if ($null -ne $response -and $response.status -eq "ok") {
            return
        }
        Start-Sleep -Seconds $IntervalSeconds
    }

    throw "Service did not recover to health status ok within $TimeoutSeconds seconds."
}

Write-Host "Starting controlled Docker compose chaos smoke."
Write-Host "Service: $Service"
Write-Host "Action: $Action"
Write-Host "BaseUrl: $BaseUrl"

Invoke-HealthCheck -Url $BaseUrl | Out-Null

switch ($Action) {
    "pause" {
        docker compose pause $Service
        Start-Sleep -Seconds 5
        Invoke-HealthCheck -Url $BaseUrl | Out-Null
        Write-Host "Service paused. Run again with -Action unpause to restore."
    }
    "unpause" {
        docker compose unpause $Service
        Wait-Healthy -Url $BaseUrl -TimeoutSeconds $RecoveryTimeoutSeconds -IntervalSeconds $PollIntervalSeconds
    }
    "restart" {
        docker compose restart $Service
        Wait-Healthy -Url $BaseUrl -TimeoutSeconds $RecoveryTimeoutSeconds -IntervalSeconds $PollIntervalSeconds
    }
}

docker compose ps
