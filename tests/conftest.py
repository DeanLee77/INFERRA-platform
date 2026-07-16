import os

import pytest

from src.domain.state.feature_flags import get_feature_flag_specs


# Test collection must not inherit a developer's root .env. Environment-loading
# behavior is covered explicitly with temporary files in infrastructure tests.
os.environ.setdefault("INFERRA_LOAD_DOTENV", "false")
for _spec in get_feature_flag_specs():
    for _env_name in _spec.environment_names:
        os.environ.pop(_env_name, None)


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="run tests marked integration that require live Docker services",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-integration"):
        return

    skip_integration = pytest.mark.skip(
        reason="requires live Docker services; pass --run-integration to run"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
