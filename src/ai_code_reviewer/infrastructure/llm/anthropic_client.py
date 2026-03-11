"""
Anthropic Claude LLM 客户端实现。
"""

from .llm_client_base import LLMClientBase


class AnthropicClient(LLMClientBase):
    """Anthropic Claude API 客户端。"""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250929", **kwargs):
        """
        初始化 Anthropic 客户端。

        Args:
            api_key: Anthropic API 密钥
            model: 模型名称
        """
        try:
            import httpx
        except ImportError:
            raise ImportError("需要安装 httpx: pip install httpx")

        self.api_key = api_key
        self.model = model
        self.httpx = httpx
        self.url = "https://api.anthropic.com/v1/messages"

    def chat(self, prompt: str, **kwargs) -> str:
        """发送聊天请求。"""
        messages = [{"role": "user", "content": prompt}]
        return self.chat_with_messages(messages, **kwargs)

    def chat_with_messages(self, messages: list[dict], **kwargs) -> str:
        """使用消息格式发送请求。"""
        max_tokens = kwargs.get("max_tokens", 30000)

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01"
        }

        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": "You are an expert code reviewer. Analyze code changes for quality, correctness, security, and maintainability.",
            "messages": messages
        }

        try:
            response = self.httpx.post(self.url, headers=headers, json=body, timeout=120)
            response.raise_for_status()
            result = response.json()

            content = result.get("content", [{}])[0].get("text", "")
            return content

        except self.httpx.HTTPError as e:
            raise RuntimeError(f"Anthropic API 调用失败：{e}")
