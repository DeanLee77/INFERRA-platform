"""Generate or verify INFERRA's canonical OpenAPI release artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPOSITORY_ROOT / "openapi.json"


def _prepare_canonical_environment() -> None:
    """Prevent workstation or deployment settings from changing the schema."""
    for name in tuple(os.environ):
        if name.startswith("INFERRA_"):
            os.environ.pop(name)
    os.environ.update(
        {
            "INFERRA_AUTH_ENABLED": "false",
            "INFERRA_ENV": "openapi",
            "INFERRA_LOAD_DOTENV": "false",
            "INFERRA_LOG_LEVEL": "ERROR",
        }
    )


def build_openapi_document() -> dict[str, Any]:
    _prepare_canonical_environment()
    from src.main import app

    return app.openapi()


def serialize_openapi(document: dict[str, Any]) -> str:
    return json.dumps(
        document,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def write_openapi(output: Path) -> int:
    content = serialize_openapi(build_openapi_document())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8", newline="\n")
    print(f"Wrote {output} (sha256:{_sha256(content)})")
    return 0


def check_openapi(output: Path) -> int:
    expected = serialize_openapi(build_openapi_document())
    if not output.is_file():
        print(
            f"OpenAPI drift: {output} does not exist. "
            "Run scripts/generate_openapi.py and commit the result.",
            file=sys.stderr,
        )
        return 1

    actual = output.read_text(encoding="utf-8")
    if actual != expected:
        print(
            "OpenAPI drift detected. "
            f"committed=sha256:{_sha256(actual)} "
            f"generated=sha256:{_sha256(expected)}. "
            "Run scripts/generate_openapi.py and review the schema diff.",
            file=sys.stderr,
        )
        return 1

    print(f"OpenAPI artifact is current (sha256:{_sha256(actual)})")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="OpenAPI JSON path (default: repository-root openapi.json)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail instead of writing when the committed artifact differs",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output = args.output.resolve()
    if args.check:
        return check_openapi(output)
    return write_openapi(output)


if __name__ == "__main__":
    raise SystemExit(main())
