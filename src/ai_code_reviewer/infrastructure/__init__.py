"""
Infrastructure Layer - 基础设施层。

包含外部服务集成（Git API、LLM API 等）。
"""

from . import git
from . import llm

__all__ = ["git", "llm"]
