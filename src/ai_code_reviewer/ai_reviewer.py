"""AI 审查器 - 将代码发送给 AI 进行审查。"""

import json
import os
from dataclasses import dataclass
from typing import Optional

try:
    import httpx
except ImportError:
    httpx = None


@dataclass
class ReviewRequest:
    """代码审查请求。"""
    diff_content: str
    context_code: str
    filename: str
    element_name: Optional[str] = None
    element_type: Optional[str] = None


@dataclass
class ReviewResult:
    """AI 代码审查的结果。"""
    filename: str
    element_name: Optional[str]
    summary: str
    issues: list[dict]
    suggestions: list[str]
    raw_response: str


class AIReviewer:
    """将代码发送给 AI 进行审查，支持多种 LLM 提供商。"""

    def __init__(
            self,
            api_key: Optional[str] = None,
            model: str = "claude-sonnet-4-20250929",
            base_url: Optional[str] = None,
            provider: str = "anthropic"
    ):
        """
        初始化 AI 审查器。

        Args:
            api_key: API 密钥（或使用对应环境变量）
            model: 要使用的模型名称
            base_url: API 基础 URL（可选，用于自定义端点或兼容 OpenAI 格式的提供商）
            provider: 提供商类型 ('anthropic', 'openai', 'qwen', 'doubao' 等)
        """
        if httpx is None:
            raise ImportError("未安装 httpx 包。运行：pip install httpx")

        # 根据提供商选择 API key 环境变量
        env_var_map = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "qwen": "QWEN_API_KEY",
            "doubao": "DOUBAO_API_KEY",
            "custom": "CUSTOM_API_KEY",
        }
        env_var = env_var_map.get(provider.lower(), "API_KEY")

        self.api_key = api_key or os.getenv(env_var)
        if not self.api_key:
            raise ValueError(f"未提供 API 密钥。请设置 {env_var} 环境变量或使用 api_key 参数。")

        self.model = model
        self.base_url = base_url
        self.provider = provider.lower()

    def review(self, request: ReviewRequest) -> ReviewResult:
        """
        发送代码进行 AI 审查。

        Args:
            request: 包含待审查代码的 ReviewRequest

        Returns:
            包含 AI 分析结果的 ReviewResult
        """
        prompt = self._build_prompt(request)
        response_text = self._call_llm(prompt)

        return self._parse_response(request.filename, request.element_name, response_text)

    def _call_llm(self, prompt: str) -> str:
        """调用 LLM API 获取响应。"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        # 根据不同提供商构建请求体
        if self.provider == "anthropic":
            url = "https://api.anthropic.com/v1/messages"
            body = {
                "model": self.model,
                "max_tokens": 4096,
                "system": "You are an expert code reviewer. Analyze code changes for quality, correctness, security, and maintainability.",
                "messages": [{"role": "user", "content": prompt}]
            }
        elif self.provider in ["openai", "qwen", "doubao"]:
            # OpenAI 格式（也适用于千问、豆包等兼容 OpenAI 格式的 API）
            if self.base_url is None:
                # 默认 URL
                urls = {
                    "openai": "https://api.openai.com/v1/chat/completions",
                    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                    "doubao": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
                }
                url = urls.get(self.provider, "https://api.openai.com/v1/chat/completions")
            else:
                url = self.base_url

            body = {
                "model": self.model,
                "max_tokens": 4096,
                "messages": [
                    {"role": "system", "content": "You are an expert code reviewer."},
                    {"role": "user", "content": prompt}
                ]
            }
        else:
            # 自定义 provider，使用 base_url
            if not self.base_url:
                raise ValueError("自定义 provider 需要提供 base_url")
            url = self.base_url
            body = {
                "model": self.model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}]
            }

        # 发送请求
        try:
            print(f"  发送给ai的请求url：{url},headers:{headers},body:{body}")
            response = httpx.post(url, headers=headers, json=body, timeout=120)
            response.raise_for_status()
            result = response.json()

            # 解析不同格式的响应
            if self.provider == "anthropic":
                return result.get("content", [{}])[0].get("text", "")
            else:
                # OpenAI 格式
                return result.get("choices", [{}])[0].get("message", {}).get("content", "")

        except httpx.HTTPError as e:
            raise RuntimeError(f"LLM API 调用失败：{e}")

    def review_batch(self, requests: list[ReviewRequest]) -> list[ReviewResult]:
        """
        审查多个代码元素。

        Args:
            requests: ReviewRequest 对象列表

        Returns:
            ReviewResult 对象列表
        """
        results = []
        for request in requests:
            try:
                result = self.review(request)
                results.append(result)
            except Exception as e:
                results.append(ReviewResult(
                    filename=request.filename,
                    element_name=request.element_name,
                    summary=f"审查失败：{str(e)}",
                    issues=[],
                    suggestions=[],
                    raw_response=""
                ))
        return results

    def _build_prompt(self, request: ReviewRequest) -> str:
        """构建审查提示。"""
        prompt = f"""我需要你审查一个代码变更。请分析以下内容：
1. 代码质量和最佳实践
2. 潜在的 bug 或问题
3. 安全问题
4. 性能影响
5. 可维护性和可读性

## 更改的文件：{request.filename}

## Diff:
```diff
{request.diff_content}
```

## 相关代码上下文：
```python
{request.context_code}
```

请提供：
1. 更改的简要摘要
2. 发现的问题（严重程度：critical/high/medium/low）
3. 具体的改进建议
4. 总体评估（approve/needs changes/major revision needed）
5. 涉及到的调用链路,如出现问题会导致哪个调用链异常

请将你的响应格式化为 JSON：
{{
    "summary": "...",
    "issues": [
        {{"severity": "high", "description": "...", "line": 10}}
    ],
    "suggestions": ["..."],
    "assessment": "approve"
}}
"""
        return prompt

    def _parse_response(
            self,
            filename: str,
            element_name: Optional[str],
            response_text: str
    ) -> ReviewResult:
        """将 AI 响应解析为结构化结果。"""
        issues = []
        suggestions = []
        summary = response_text

        # 尝试从响应中提取 JSON
        json_start = response_text.find("{")
        json_end = response_text.rfind("}") + 1

        if json_start >= 0 and json_end > json_start:
            try:
                json_str = response_text[json_start:json_end]
                data = json.loads(json_str)
                summary = data.get("summary", response_text)
                issues = data.get("issues", [])
                suggestions = data.get("suggestions", [])
            except json.JSONDecodeError:
                pass

        return ReviewResult(
            filename=filename,
            element_name=element_name,
            summary=summary,
            issues=issues,
            suggestions=suggestions,
            raw_response=response_text
        )
