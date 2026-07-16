"""Process-boundary environment loading for INFERRA entry points."""

import os
from pathlib import Path
from typing import Optional, Union

from dotenv import load_dotenv


_TRUE_VALUES = {"1", "true", "yes"}
_FALSE_VALUES = {"0", "false", "no"}


def load_process_environment(
    env_file: Optional[Union[str, Path]] = None,
) -> bool:
    """Load a dotenv file without overriding exported process variables.

    API and worker entry points call this before importing application modules.
    Set ``INFERRA_LOAD_DOTENV=false`` to disable file loading, or
    ``INFERRA_ENV_FILE`` to select a file other than the root ``.env``.
    """
    if not _dotenv_loading_enabled():
        return False

    selected_file = env_file or os.environ.get("INFERRA_ENV_FILE") or ".env"
    return bool(load_dotenv(dotenv_path=selected_file, override=False))


def _dotenv_loading_enabled() -> bool:
    raw_value = os.environ.get("INFERRA_LOAD_DOTENV", "true").strip().lower()
    if raw_value in _TRUE_VALUES:
        return True
    if raw_value in _FALSE_VALUES:
        return False
    raise ValueError(
        "INFERRA_LOAD_DOTENV must be one of: true, 1, yes, false, 0, no"
    )
