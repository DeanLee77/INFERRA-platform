param(
    [string]$BaseUrl = "http://localhost:8000",
    [switch]$SkipUnitTests,
    [switch]$SkipFrontend,
    [switch]$SkipDockerSmoke
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Command
    )

    Write-Host ""
    Write-Host "== $Name =="
    & $Command
}

Set-Location $Root

function Assert-LastExitCode {
    param([string]$CommandName)

    if ($LASTEXITCODE -ne 0) {
        throw "$CommandName failed with exit code $LASTEXITCODE"
    }
}

if (-not $SkipUnitTests) {
    Invoke-Step "Backend tests with coverage" {
        pytest --cov=src --cov-fail-under=97
    }
}

if (-not $SkipFrontend) {
    Invoke-Step "Rule Studio frontend checks" {
        Push-Location "frontends/inferra-rule-studio"
        try {
            npm.cmd test
            npm.cmd run check
        }
        finally {
            Pop-Location
        }
    }

    Invoke-Step "AI Harness frontend checks" {
        Push-Location "frontends/inferra-ai-harness"
        try {
            npm.cmd test
            npm.cmd run check
        }
        finally {
            Pop-Location
        }
    }
}

if (-not $SkipDockerSmoke) {
    Invoke-Step "Docker service status" {
        docker compose ps
        Assert-LastExitCode -CommandName "docker compose ps"
    }

    Invoke-Step "Live health endpoint" {
        $health = Invoke-RestMethod -Uri "$BaseUrl/api/v1/health" -Method Get -TimeoutSec 15
        if ($health.status -ne "ok") {
            throw "Health endpoint did not return ok: $($health | ConvertTo-Json -Depth 8)"
        }
        $health | ConvertTo-Json -Depth 8
    }

    Invoke-Step "Live metrics endpoint" {
        $metrics = Invoke-WebRequest -Uri "$BaseUrl/metrics" -Method Get -TimeoutSec 15 -UseBasicParsing
        if ($metrics.Content -notmatch "inferra_abduction_total") {
            throw "Expected inferra_abduction_total metric was not present."
        }
        Write-Host "metrics include inferra_abduction_total"
    }

    Invoke-Step "Reasoning endpoint smoke" {
        $goalPayload = @{
            user_query = "Can I claim this benefit?"
            rule_name = "benefit_rule"
            enabled = $false
        } | ConvertTo-Json

        $goal = Invoke-RestMethod `
            -Uri "$BaseUrl/api/v1/reasoning/goal" `
            -Method Post `
            -ContentType "application/json" `
            -Body $goalPayload `
            -TimeoutSec 15

        if ($goal.fallback -ne $true) {
            throw "Expected disabled goal mapping to use fallback."
        }

        $abductPayload = '{
          "target": "goal",
          "working_memory": {"known": true},
          "graph_snapshot": {"child_groups": {"goal": [[1, ["known", "missing"]]]}},
          "enabled": true
        }'

        $abduct = Invoke-RestMethod `
            -Uri "$BaseUrl/api/v1/reasoning/abduct" `
            -Method Post `
            -ContentType "application/json" `
            -Body $abductPayload `
            -TimeoutSec 15

        if ($abduct.hypotheses.Count -lt 1 -or $abduct.hypotheses[0].fact_name -ne "missing") {
            throw "Expected abduction smoke to return the missing fact hypothesis."
        }

        Write-Host "reasoning smoke passed"
    }

    Invoke-Step "Local Grafana endpoint" {
        $grafana = Invoke-WebRequest -Uri "http://localhost:3000/api/health" -Method Get -TimeoutSec 15 -UseBasicParsing
        if ($grafana.StatusCode -ne 200) {
            throw "Grafana health endpoint did not return 200."
        }
        Write-Host "grafana health endpoint is reachable"
    }
}

Write-Host ""
Write-Host "INFERRA phase readiness verification completed."
