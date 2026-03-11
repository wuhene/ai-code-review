"""
LLM 客户端基类 - 定义 LLM 提供商的统一接口。
"""

from abc import ABC, abstractmethod


class LLMClientBase(ABC):
    """LLM 客户端基类，定义统一的接口。"""

    @abstractmethod
    def chat(self, prompt: str, **kwargs) -> str:
        """
        发送聊天请求并获取响应。

        Args:
            prompt: 提示词
            **kwargs: 其他参数

        Returns:
            LLM 响应文本
        """
        pass

    @abstractmethod
    def chat_with_messages(self, messages: list[dict], **kwargs) -> str:
        """
        使用消息格式发送聊天请求。

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            **kwargs: 其他参数

        Returns:
            LLM 响应文本
        """
        pass
