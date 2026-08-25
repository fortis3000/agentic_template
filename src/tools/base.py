"""Base tool abstractions and registry factory.

Re-exports core tool classes from src.tools.local.base for backward compatibility.
"""

from src.tools.local.base import BaseTool, ToolConfigType, ToolFactory

__all__ = ["BaseTool", "ToolConfigType", "ToolFactory"]
