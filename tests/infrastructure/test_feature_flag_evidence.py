import json

from scripts.capture_feature_flag_evidence import (
    build_compose_evidence,
    main,
)


def _compose_config(api_environment=None, worker_environment=None):
    return {
        "services": {
            "api": {"environment": api_environment or {}},
            "worker": {"environment": worker_environment or {}},
        }
    }


def test_compose_evidence_matches_identical_process_profiles():
    profile = {
        "INFERRA_ENV": "local",
        "INFERRA_ASYNC_SYNC_ENABLED": "true",
    }

    evidence = build_compose_evidence(_compose_config(profile, profile))

    assert evidence["matched"] is True
    assert evidence["api"]["process_role"] == "api"
    assert evidence["worker"]["process_role"] == "worker"
    assert evidence["api"]["snapshot_hash"] == evidence["worker"]["snapshot_hash"]
    assert evidence["api"]["effective"]["async_sync_enabled"] is True


def test_compose_evidence_detects_api_worker_mismatch():
    evidence = build_compose_evidence(
        _compose_config(
            {"INFERRA_REASONING_ROUTER": "true"},
            {"INFERRA_REASONING_ROUTER": "false"},
        )
    )

    assert evidence["matched"] is False
    assert evidence["api"]["snapshot_hash"] != evidence["worker"]["snapshot_hash"]


def test_cli_writes_redaction_safe_evidence(tmp_path):
    compose_path = tmp_path / "compose.json"
    evidence_path = tmp_path / "evidence.json"
    compose_path.write_text(json.dumps(_compose_config()), encoding="utf-8")

    exit_code = main(
        [
            "--compose-config",
            str(compose_path),
            "--output",
            str(evidence_path),
        ]
    )

    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert evidence["matched"] is True
    assert set(evidence) == {"schema_version", "matched", "api", "worker"}
