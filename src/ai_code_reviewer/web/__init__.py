"""
Presentation Layer - 表现层。

包含 Web 接口（FastAPI），负责处理 HTTP 请求和响应。
"""

from .server import app

__all__ = ["app"]
