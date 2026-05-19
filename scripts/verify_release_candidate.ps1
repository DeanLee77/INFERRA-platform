param(
    [string]$BaseUrl = "http://localhost:8000",
    [switch]$SkipFrontend,
    [switch]$SkipDockerSmoke,
    [switch]$SkipLoad,
    [switch]$SkipChaos,
    [switch]$EnforceProductionFlags
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

function Assert-LastExitCode {
    param([string]$CommandName)

    if ($LASTEXITCODE -ne 0) {
        throw "$CommandName failed with exit code $LASTEXITCODE"
    }
}

Set-Location $Root

Invoke-Step "Backend coverage gate" {
    pytest --cov=src --cov-fail-under=97
    Assert-LastExitCode -CommandName "pytest coverage"
}

Invoke-Step "Phase 5 dedicated acceptance" {
    pytest tests/integration/test_phase5_acceptance.py -q --run-integration
    Assert-LastExitCode -CommandName "pytest phase5 acceptance"
}

Invoke-Step "Benchmark regression gate" {
    pytest tests/benchmarks/ -q
    Assert-LastExitCode -CommandName "pytest benchmarks"
}

Invoke-Step "Infrastructure artifact and guardrail gate" {
    pytest tests/infrastructure/test_guardrails.py tests/infrastructure/test_phase_readiness_artifacts.py tests/infrastructure/test_monitoring_artifacts.py -q
    Assert-LastExitCode -CommandName "pytest infrastructure gates"
}

Invoke-Step "Import boundary gate" {
    lint-imports --config .importlinter
    Assert-LastExitCode -CommandName "lint-imports"
}

if ($EnforceProductionFlags) {
    Invoke-Step "Production flag retirement gate" {
        python -c "from src.domain.state.feature_flags import FeatureFlags; import json, sys; report=FeatureFlags().legacy_retirement_report(); print(json.dumps(report, indent=2)); bad=[name for name, item in report.items() if not item['ready']]; sys.exit(1 if bad else 0)"
        Assert-LastExitCode -CommandName "production flag retirement gate"
    }
}

if (-not $SkipFrontend) {
    Invoke-Step "Frontend checks" {
        Push-Location "frontends/inferra-rule-studio"
        try {
            npm.cmd test
            npm.cmd run check
        }
        finally {
            Pop-Location
        }

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
    Invoke-Step "Live stack smoke" {
        powershell -ExecutionPolicy Bypass -File scripts/verify_phase_readiness.ps1 -BaseUrl $BaseUrl -SkipUnitTests -SkipFrontend
        Assert-LastExitCode -CommandName "verify_phase_readiness"
    }
}

if (-not $SkipLoad) {
    Invoke-Step "Dockerized k6 smoke" {
        powershell -ExecutionPolicy Bypass -File tests/load/run_k6_docker.ps1 -BaseUrl $BaseUrl
        Assert-LastExitCode -CommandName "run_k6_docker"
    }

    Invoke-Step "Dockerized k6 production-load gate" {
        powershell -ExecutionPolicy Bypass -File tests/load/run_k6_production_gate.ps1 -Vus 500 -Duration 1m
        Assert-LastExitCode -CommandName "run_k6_production_gate"
    }
}

if (-not $SkipChaos) {
    Invoke-Step "Phase 4 restart chaos suite" {
        powershell -ExecutionPolicy Bypass -File tests/chaos/run_phase4_chaos_suite.ps1
        Assert-LastExitCode -CommandName "run_phase4_chaos_suite"
    }
}

Write-Host ""
Write-Host "INFERRA release-candidate verification completed."
