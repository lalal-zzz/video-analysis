"""Tool Registry - Global tool registration.

All tools are auto-registered via @ToolRegistry.register decorators.
Import this module to ensure all tools are registered.
"""

from __future__ import annotations


class ToolRegistry:
    """全局工具注册表，所有 Skill 共享."""

    _registry: dict[str, object] = {}

    @classmethod
    def register(cls, name: str):
        """装饰器：注册工具函数."""
        def decorator(func):
            cls._registry[name] = func
            return func
        return decorator

    @classmethod
    def call(cls, name: str, **kwargs) -> object:
        """调用已注册的工具."""
        func = cls._registry.get(name)
        if func is None:
            raise KeyError(f"Tool '{name}' not registered. Available: {list(cls._registry.keys())}")
        if callable(func):
            return func(**kwargs)
        return func

    @classmethod
    def list_all(cls) -> list[str]:
        """列出所有已注册工具."""
        return list(cls._registry.keys())
