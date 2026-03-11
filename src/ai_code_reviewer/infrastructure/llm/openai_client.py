"""
OpenAI 兼容格式 LLM 客户端实现。

适用于 OpenAI、阿里云 Qwen、字节豆包等兼容 OpenAI 格式的 API。
"""

from .llm_client_base import LLMClientBase


class OpenAICompatibleClient(LLMClientBase):
    """OpenAI 兼容格式的 LLM 客户端。"""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4",
        base_url: str = "https://api.openai.com/v1",
        **kwargs
    ):
        """
        初始化 OpenAI 兼容客户端。

        Args:
            api_key: API 密钥
            model: 模型名称
            base_url: API 基础 URL
        """
        try:
            import httpx
        except ImportError:
            raise ImportError("需要安装 httpx: pip install httpx")

        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.httpx = httpx
        self.url = f"{self.base_url}/chat/completions"

    def chat(self, prompt: str, **kwargs) -> str:
        """发送聊天请求。"""
        messages = [
            {"role": "system", "content": "You are an expert code reviewer."},
            {"role": "user", "content": prompt}
        ]
        return self.chat_with_messages(messages, **kwargs)

    def chat_with_messages(self, messages: list[dict], **kwargs) -> str:
        """使用消息格式发送请求。"""
        max_tokens = kwargs.get("max_tokens", 30000)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages
        }

        try:
            response = self.httpx.post(self.url, headers=headers, json=body, timeout=120)
            response.raise_for_status()
            result = response.json()

            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            return content

        except self.httpx.HTTPError as e:
            raise RuntimeError(f"API 调用失败：{e}")
