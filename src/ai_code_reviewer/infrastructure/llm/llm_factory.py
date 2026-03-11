"""
LLM 客户端工厂 - 根据提供商类型创建对应的客户端。
"""

import os
from typing import Optional

from .llm_client_base import LLMClientBase
from .anthropic_client import AnthropicClient
from .openai_client import OpenAICompatibleClient


class LLMFactory:
    """LLM 客户端工厂类。"""

    # 默认 URL 映射
    DEFAULT_URLS = {
        "openai": "https://api.openai.com/v1",
        "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "doubao": "https://ark.cn-beijing.volces.com/api/v3",
    }

    # 环境变量映射
    ENV_VAR_MAP = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "qwen": "QWEN_API_KEY",
        "doubao": "DOUBAO_API_KEY",
        "custom": "CUSTOM_API_KEY",
    }

    @classmethod
    def create_client(
        cls,
        provider: str,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-20250929",
        base_url: Optional[str] = None
    ) -> LLMClientBase:
        """
        根据提供商类型创建 LLM 客户端。

        Args:
            provider: 提供商类型 ('anthropic', 'openai', 'qwen', 'doubao', 'custom')
            api_key: API 密钥
            model: 模型名称
            base_url: 自定义 API 端点

        Returns:
            LLM 客户端实例

        Raises:
            ValueError: 缺少必要的配置
        """
        provider = provider.lower()

        # 获取 API Key
        env_var = cls.ENV_VAR_MAP.get(provider, "API_KEY")
        api_key = api_key or os.getenv(env_var)
        if not api_key:
            raise ValueError(f"未提供 API 密钥。请设置 {env_var} 环境变量或使用 api_key 参数。")

        # 根据提供商创建客户端
        if provider == "anthropic":
            return AnthropicClient(
                api_key=api_key,
                model=model
            )
        elif provider in ["openai", "qwen", "doubao", "custom"]:
            # 确定 base_url
            if base_url is None:
                base_url = cls.DEFAULT_URLS.get(provider, "https://api.openai.com/v1")

            return OpenAICompatibleClient(
                api_key=api_key,
                model=model,
                base_url=base_url
            )
        else:
            raise ValueError(f"不支持的提供商：{provider}")
