"""Automatic discovery for model-visible management tools.

Every non-private module in this package is a tool module and must expose a
``create_tool(context)`` factory. Adding a module is therefore enough to make
its tool available to the management agent.
"""

from __future__ import annotations

import importlib
import pkgutil
from agent import Tool

from ._context import ToolContext


def discover_tools(context: ToolContext) -> list[Tool]:
    discovered: list[Tool] = []
    package_path = __path__  # type: ignore[name-defined]
    modules = sorted(pkgutil.iter_modules(package_path), key=lambda item: item.name)
    for module_info in modules:
        if module_info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{module_info.name}")
        factory = getattr(module, "create_tool", None)
        if not callable(factory):
            raise RuntimeError(
                f"Tool module {module.__name__!r} must expose create_tool(context)"
            )
        discovered.append(factory(context))

    names = [tool.name for tool in discovered]
    if len(names) != len(set(names)):
        raise RuntimeError("Discovered tool names must be unique")
    return discovered


__all__ = ["ToolContext", "discover_tools"]
