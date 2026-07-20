"""Build and verify inferra-core without repository-root import leakage."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPOSITORY_ROOT / "packages" / "inferra-core"
_VERSION_SOURCE = PACKAGE_ROOT / "src" / "inferra_core" / "_version.py"
_VERSION_MATCH = re.search(
    r'^__version__\s*=\s*["\']([^"\']+)["\']',
    _VERSION_SOURCE.read_text(encoding="utf-8"),
    flags=re.MULTILINE,
)
if _VERSION_MATCH is None:
    raise RuntimeError(f"could not read Core version from {_VERSION_SOURCE}")
CORE_VERSION = _VERSION_MATCH.group(1)


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "Core distribution verification command failed"
            f"\nstdout:\n{exc.stdout or '<empty>'}"
            f"\nstderr:\n{exc.stderr or '<empty>'}"
        ) from exc
    return completed.stdout.strip()


def _venv_python(environment: Path) -> Path:
    if os.name == "nt":
        return environment / "Scripts" / "python.exe"
    return environment / "bin" / "python"


def _assert_wheel_contents(wheel_path: Path) -> None:
    with zipfile.ZipFile(wheel_path) as archive:
        names = archive.namelist()

    forbidden = [
        name
        for name in names
        if name.startswith(("src/", "tests/", "adapters/", "infrastructure/"))
    ]
    unexpected = [
        name
        for name in names
        if not name.startswith(
            ("inferra_core/", f"inferra_core-{CORE_VERSION}.dist-info/")
        )
    ]
    if forbidden or unexpected:
        raise RuntimeError(
            f"invalid wheel contents: forbidden={forbidden}, unexpected={unexpected}"
        )


def _assert_sdist_contents(sdist_path: Path) -> None:
    expected_root = f"inferra_core-{CORE_VERSION}"
    with tarfile.open(sdist_path, mode="r:gz") as archive:
        names = archive.getnames()

    required = {
        f"{expected_root}/README.md",
        f"{expected_root}/pyproject.toml",
        f"{expected_root}/src/inferra_core/__init__.py",
    }
    missing = sorted(required - set(names))
    escaped = [
        name
        for name in names
        if name != expected_root and not name.startswith(f"{expected_root}/")
    ]
    platform_files = [
        name
        for name in names
        if name.startswith(
            (
                f"{expected_root}/src/src/",
                f"{expected_root}/.github/",
                f"{expected_root}/docs/",
            )
        )
    ]
    if missing or escaped or platform_files:
        raise RuntimeError(
            "invalid source distribution contents: "
            f"missing={missing}, escaped={escaped}, platform_files={platform_files}"
        )


def _verify_isolated_install(
    wheel_path: Path,
    wheelhouse: Path,
    temporary_root: Path,
) -> dict:
    environment = temporary_root / "venv"
    isolated_cwd = temporary_root / "outside-repository"
    isolated_cwd.mkdir()
    venv.EnvBuilder(with_pip=True, clear=True).create(environment)
    python = _venv_python(environment)

    _run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--find-links",
            str(wheelhouse),
            str(wheel_path),
        ],
        cwd=isolated_cwd,
    )

    verification = r'''
import json
from importlib.metadata import requires, version
from pathlib import Path
import sys

import inferra_core
from inferra_core import DependencyType, FactSource, FactValue, FactValueType
from inferra_core._internal.domain.rule_parser import (
    RuleSetParser, RuleSetReader, RuleSetScanner,
)
from inferra_core._internal.domain.expression_evaluator import (
    SafeExpressionError, evaluate_expression,
)

assert version("inferra-core") == inferra_core.__version__ == "__CORE_VERSION__"
declared_requirements = requires("inferra-core") or []
runtime_requirements = [
    requirement for requirement in declared_requirements
    if "extra ==" not in requirement
]
assert runtime_requirements == [], runtime_requirements
assert FactValue(True).get_value_type() is FactValueType.BOOLEAN
assert FactSource.from_value("SEMANTIC") is FactSource.SEMANTIC
assert int(DependencyType.MANDATORY | DependencyType.AND) == 72

source = "INPUT age AS NUMBER\n\neligible\n    AND age >= 18\n"
reader = RuleSetReader()
reader.create()
reader.set_file_with_text(source)
parser = RuleSetParser()
parser.create()
parser.set_source_name("isolated-wheel")
scanner = RuleSetScanner(reader, parser)
scanner.scan_rule_set()
node_set = scanner.establish_node_set()
assert sorted(node_set.get_node_dictionary()) == ["age >= 18", "eligible"]
assert list(node_set.get_graph().edges()) == [("eligible", "age >= 18", 8)]
assert not any(name == "src" or name.startswith("src.") for name in sys.modules)

try:
    evaluate_expression("__import__('builtins').sum((20, 22))", {})
except SafeExpressionError:
    pass
else:
    raise AssertionError("installed Core accepted a Python expression")

forbidden = {
    "celery", "fastapi", "httpx", "openai", "pydantic", "rdflib",
    "redis", "requests", "sqlalchemy", "structlog", "sympy", "uvicorn"
}
loaded_forbidden = sorted({name.split(".", 1)[0] for name in sys.modules} & forbidden)
assert loaded_forbidden == []

print(json.dumps({
    "module_path": str(Path(inferra_core.__file__).resolve()),
    "version": inferra_core.__version__,
    "loaded_forbidden": loaded_forbidden,
}, sort_keys=True))
'''.replace("__CORE_VERSION__", CORE_VERSION)
    environment_variables = os.environ.copy()
    environment_variables.pop("PYTHONPATH", None)
    environment_variables.pop("PYTHONHOME", None)
    environment_variables["PYTHONNOUSERSITE"] = "1"
    output = _run(
        [str(python), "-I", "-c", verification],
        cwd=isolated_cwd,
        env=environment_variables,
    )
    result = json.loads(output.splitlines()[-1])

    repository = str(REPOSITORY_ROOT.resolve()).casefold()
    if repository in result["module_path"].casefold():
        raise RuntimeError("isolated import resolved into the repository working tree")
    return result


def verify(output_directory: Path | None = None) -> dict:
    with tempfile.TemporaryDirectory(prefix="inferra-core-wheel-") as temporary:
        temporary_root = Path(temporary)
        build_source = temporary_root / "source" / "inferra-core"
        wheel_directory = temporary_root / "wheel"
        sdist_directory = temporary_root / "sdist"
        shutil.copytree(
            PACKAGE_ROOT,
            build_source,
            ignore=shutil.ignore_patterns(
                ".pytest_cache",
                "__pycache__",
                "*.egg-info",
                "build",
                "dist",
            ),
        )
        wheel_directory.mkdir()
        sdist_directory.mkdir()

        sdist_builder = (
            "from setuptools.build_meta import build_sdist; "
            "import sys; print(build_sdist(sys.argv[1]))"
        )
        _run(
            [sys.executable, "-c", sdist_builder, str(sdist_directory)],
            cwd=build_source,
        )
        sdists = sorted(sdist_directory.glob(f"inferra_core-{CORE_VERSION}.tar.gz"))
        if len(sdists) != 1:
            raise RuntimeError(f"expected one Core source distribution, found: {sdists}")
        sdist_path = sdists[0]
        _assert_sdist_contents(sdist_path)

        _run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-cache-dir",
                "--no-deps",
                "--no-build-isolation",
                "--wheel-dir",
                str(wheel_directory),
                str(build_source),
            ],
            cwd=temporary_root,
        )
        wheels = sorted(wheel_directory.glob(f"inferra_core-{CORE_VERSION}-*.whl"))
        if len(wheels) != 1:
            raise RuntimeError(f"expected one Core wheel, found: {wheels}")

        wheel_path = wheels[0]
        _assert_wheel_contents(wheel_path)
        isolated = _verify_isolated_install(
            wheel_path,
            wheel_directory,
            temporary_root,
        )
        wheel_hash = hashlib.sha256(wheel_path.read_bytes()).hexdigest()
        sdist_hash = hashlib.sha256(sdist_path.read_bytes()).hexdigest()

        retained_wheel_path = None
        retained_sdist_path = None
        if output_directory is not None:
            output_directory.mkdir(parents=True, exist_ok=True)
            retained_wheel_path = output_directory / wheel_path.name
            retained_sdist_path = output_directory / sdist_path.name
            shutil.copy2(wheel_path, retained_wheel_path)
            shutil.copy2(sdist_path, retained_sdist_path)

        return {
            "distribution": "inferra-core",
            "version": CORE_VERSION,
            "wheel": wheel_path.name,
            "wheel_sha256": wheel_hash,
            "source_distribution": sdist_path.name,
            "source_distribution_sha256": sdist_hash,
            "retained_wheel_path": (
                str(retained_wheel_path) if retained_wheel_path else None
            ),
            "retained_source_distribution_path": (
                str(retained_sdist_path) if retained_sdist_path else None
            ),
            "isolated_install": isolated,
            "repository_pythonpath_used": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Optional directory in which to retain the verified wheel.",
    )
    arguments = parser.parse_args()
    print(json.dumps(verify(arguments.output_dir), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
