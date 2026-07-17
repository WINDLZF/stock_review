"""通用插件注册中心：支持数据源、分析维度等的注册式扩展。

新增一个数据源/维度只需：
    @register_source("myapi")
    class MyApiSource: ...
无需修改任何主流程代码——这是"扩展点"的落地机制。
"""
from __future__ import annotations

from typing import Callable, Generic, TypeVar

T = TypeVar("T")


class Registry(Generic[T]):
    """按名称注册/获取实现类的通用注册表。"""

    def __init__(self, kind: str):
        self._kind = kind
        self._items: dict[str, type[T]] = {}

    def register(self, name: str) -> Callable[[type[T]], type[T]]:
        def deco(cls: type[T]) -> type[T]:
            key = name.lower()
            if key in self._items:
                raise ValueError(f"{self._kind} '{name}' 已注册")
            self._items[key] = cls
            return cls

        return deco

    def get(self, name: str) -> type[T]:
        key = name.lower()
        if key not in self._items:
            raise KeyError(
                f"未找到 {self._kind} '{name}'，可用: {sorted(self._items)}"
            )
        return self._items[key]

    def create(self, name: str, **kwargs) -> T:
        return self.get(name)(**kwargs)

    def names(self) -> list[str]:
        return sorted(self._items)

    def __contains__(self, name: str) -> bool:
        return name.lower() in self._items


# 全局注册表实例（各扩展点各一个）
source_registry: Registry = Registry("data_source")
dimension_registry: Registry = Registry("analysis_dimension")
</parameter>
<parameter name="explanation">创建通用插件注册中心，为数据源和分析维度提供注册式扩展机制。