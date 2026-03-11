"""
Domain Layer - 领域层。

包含核心业务实体和领域服务，不依赖任何外部基础设施。
"""

from . import entities
from . import services

__all__ = ["entities", "services"]
