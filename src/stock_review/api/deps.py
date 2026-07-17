"""接口依赖注入。"""
from stock_review.core.config import get_settings
from stock_review.core.db import get_db

__all__ = ["get_db", "get_settings"]
