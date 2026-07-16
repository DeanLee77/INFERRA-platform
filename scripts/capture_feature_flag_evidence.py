"""Capture redaction-safe API/worker feature-flag release evidence."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.domain.state.feature_flags import (
    FeatureFlags,
    build_effective_feature_flag_report,
    validate_runtime_feature_flags,
)


def _service_environment(raw_environment: Any) -> dict[str, str]:
    if isinstance(raw_environment, Mapping):
        return {
            str(key): "" if value is None else str(value)
            for key, value in raw_environment.items()
        }
    if isinstance(raw_environment, list):
        environment: dict[str, str] = {}
        for item in raw_environment:
            key, separator, value = str(item).partition("=")
            if key:
                environment[key] = value if separator else ""
        return environment
    return {}


def report_for_environment(
    process_role: str,
    environment: Mapping[str, str],
) -> dict[str, Any]:
    """Resolve one isolated process environment into a canonical report."""
    normalized_environment = {
        str(key): str(value)
        for key, value in environment.items()
    }
    with patch.dict(os.environ, normalized_environment, clear=True):
        flags = validate_runtime_feature_flags(FeatureFlags())
        return build_effective_feature_flag_report(
            process_role,
            flags=flags,
            environment=normalized_environment,
        )


def build_compose_evidence(compose_config: Mapping[str, Any]) -> dict[str, Any]:
    """Build and compare API/worker reports from rendered Compose JSON."""
    services = compose_config.get("services")
    if not isinstance(services, Mapping):
        raise ValueError("Rendered Compose configuration has no services mapping")

    reports: dict[str, dict[str, Any]] = {}
    for role in ("api", "worker"):
        service = services.get(role)
        if not isinstance(service, Mapping):
            raise ValueError(f"Rendered Compose configuration has no {role} service")
        reports[role] = report_for_environment(
            role,
            _service_environment(service.get("environment")),
        )

    matched = reports["api"]["snapshot_hash"] == reports["worker"]["snapshot_hash"]
    return {
        "schema_version": 1,
        "matched": matched,
        "api": reports["api"],
        "worker": reports["worker"],
    }


def build_current_environment_evidence() -> dict[str, Any]:
    """Build local API/worker evidence from the caller's current environment."""
    environment = dict(os.environ)
    return build_compose_evidence(
        {
            "services": {
                "api": {"environment": environment},
                "worker": {"environment": environment},
            }
        }
    )


def _read_compose_config(path: str | None) -> Mapping[str, Any]:
    if path is None:
        return {}
    raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, Mapping):
        raise ValueError("Rendered Compose JSON must be an object")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--compose-config",
        help="Rendered `docker compose config --format json` path, or - for stdin.",
    )
    parser.add_argument(
        "--output",
        help="Optional JSON evidence output path.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Write only the output artifact; suppress stdout.",
    )
    args = parser.parse_args(argv)

    if args.compose_config:
        evidence = build_compose_evidence(_read_compose_config(args.compose_config))
    else:
        evidence = build_current_environment_evidence()

    payload = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload, encoding="utf-8")
    if not args.quiet:
        sys.stdout.write(payload)
    return 0 if evidence["matched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
