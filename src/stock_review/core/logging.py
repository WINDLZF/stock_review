"""统一日志。"""
from __future__ import annotations

import logging
import sys

from .config import get_settings


def setup_logging() -> None:
    s = get_settings()
    logging.basicConfig(
        level=s.log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        stream=sys.stdout,
        force=True,
    )
