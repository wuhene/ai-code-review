"""
Application Layer - 应用层。

负责协调领域服务和基础设施，完成业务流程。
"""

from .review_service import ReviewApplicationService

__all__ = ["ReviewApplicationService"]
