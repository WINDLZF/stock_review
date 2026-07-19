"""维度注册引导：导入各维度模块使其 @register 生效。

在 ReviewService 启动或应用启动时调用 ensure_dimensions()，即可让 config.yaml
里列出的维度可用。新增维度模块后，在此 import 即可被自动注册。
"""
from __future__ import annotations


def ensure_dimensions() -> None:
    from stock_review.adapters.dimension import breadth, sector  # noqa: F401
