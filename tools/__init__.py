"""Tools package - Auto-register all tools."""

from .registry import ToolRegistry

# Import all tool modules to trigger @register decorators
import tools.stock  # noqa: F401
import tools.scraper  # noqa: F401
import tools.general  # noqa: F401
import tools.author  # noqa: F401

__all__ = ["ToolRegistry"]
