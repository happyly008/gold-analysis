"""Cross-platform filesystem locations used by the application.

All bundled resources are resolved from the source tree.  Writable runtime
files default to the source tree for backwards compatibility, but deployments
can redirect them with ``GOLD_ANALYSIS_HOME`` (for example to an XDG data
directory on Linux or an AppData directory on Windows).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Union


PathLike = Union[str, os.PathLike]

PROJECT_ROOT = Path(__file__).resolve().parent
RUNTIME_ROOT = Path(os.environ.get("GOLD_ANALYSIS_HOME", PROJECT_ROOT)).expanduser().resolve()

CONFIG_DIR = RUNTIME_ROOT / "config"
DATA_DIR = RUNTIME_ROOT / "data"
LOG_DIR = RUNTIME_ROOT / "logs"
REPORT_DIR = RUNTIME_ROOT / "reports"

EMAIL_CONFIG = CONFIG_DIR / "email.ini"
ALERTS_CONFIG = CONFIG_DIR / "alerts.json"
FEES_CONFIG = CONFIG_DIR / "fees.json"


def runtime_path(path: PathLike) -> Path:
    """Resolve a user/runtime path without depending on the process cwd."""
    value = Path(path).expanduser()
    return value if value.is_absolute() else RUNTIME_ROOT / value


def bundled_path(path: PathLike) -> Path:
    """Resolve a read-only resource shipped with the project."""
    value = Path(path)
    return value if value.is_absolute() else PROJECT_ROOT / value
