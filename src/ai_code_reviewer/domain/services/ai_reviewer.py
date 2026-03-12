"""
AI 审查器 - 领域服务。

职责：
1. 调用 LLM 进行代码审查
2. 构建审查 Prompt
3. 解析 LLM 响应

本模块属于 Domain Layer，依赖 LLM Provider 基础设施。
"""

import json
import os
from typing import Optional

from ..entities import ReviewRequest, ReviewResult


class AIReviewer:
    """
    AI 代码审查领域服务。

    负责将代码发送给 LLM 进行审查，支持多种 LLM 提供商。
    """

    def __init__(
            self,
            api_key: Optional[str] = None,
            model: str = "claude-sonnet-4-20250929",
            base_url: Optional[str] = None,
            provider: str = "anthropic",
            llm_client: Optional[object] = None
    ):
        """
        初始化 AI 审查器。

        Args:
            api_key: API 密钥
            model: 模型名称
            base_url: 自定义 API 端点
            provider: 提供商类型
            llm_client: LLM 客户端实例（可选，如果提供则优先使用）
        """
        if llm_client is not None:
            self.llm_client = llm_client
        else:
            from ...infrastructure.llm.llm_factory import LLMFactory
            self.llm_client = LLMFactory.create_client(
                provider=provider,
                api_key=api_key,
                model=model,
                base_url=base_url
            )

        self.model = model
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
        response_text = self.llm_client.chat(prompt)

        return self._parse_response(
            request.filename,
            request.element_name,
            request.element_type,
            request.element_line_start,
            request.element_line_end,
            response_text
        )

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
                print(f"审查异常: {e}")
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
        prompt_parts = [
            "我需要你审查一个代码变更。请分析以下内容：",
            "1. 代码质量和最佳实践",
            "2. 潜在的 bug 或问题",
            "3. 安全问题",
            "4. 性能影响",
            "5. 可维护性和可读性",
            ""
        ]

        if request.call_chain_info:
            prompt_parts.append("## 调用链信息")
            prompt_parts.append("```")
            prompt_parts.append(request.call_chain_info)
            prompt_parts.append("```")
            prompt_parts.append("特别注意检查这些调用链是否会被你的更改影响！")
            prompt_parts.append("")

        prompt_parts.extend([
            f"## 更改的文件：{request.filename}",
            "",
            "## 代码变更 (Diff):",
            "```diff",
            f"{request.diff_content}",
            "```",
            "",
            "## 完整代码上下文 (已提供功能分支和主分支的完整文件，可直接对比):",
            "```",
            f"{request.context_code}",
            "```",
            "",
            "请提供：",
            "1. 更改的简要摘要",
            "2. 发现的问题 (严重程度：critical/high/medium/low)，必须包含具体行号 line",
            "3. 具体的改进建议，必须包含具体行号 line",
            "4. 总体评估 (approve/needs changes/major revision needed)",
            "",
            f"注意：已提供带行号的完整代码上下文，请根据该上下文中的行号来标注 issues 和 suggestions 中的实际行号，不要使用 DIFF 中的相对行号。",
            "",
            "请将你的响应格式化为 JSON:",
            "{",
            '    "summary": "...",',
            '    "issues": [',
            '        {"severity": "high", "description": "问题描述", "line": 10},  // 必须包含 line 字段',
            "    ],",
            '    "suggestions": [',
            '        {"description": "建议描述", "line": 15}',
            "    ],",
            '    "assessment": "approve"',
            "}"
        ])

        return "\n".join(prompt_parts)

    def _parse_response(
            self,
            filename: str,
            element_name: Optional[str],
            element_type: Optional[str],
            line_start: int,
            line_end: int,
            response_text: str
    ) -> ReviewResult:
        """将 AI 响应解析为结构化结果。"""
        issues = []
        suggestions = []
        summary = response_text

        json_start = response_text.find("{")
        json_end = response_text.rfind("}") + 1

        if json_start >= 0 and json_end > json_start:
            try:
                json_str = response_text[json_start:json_end]
                data = json.loads(json_str)
                summary = data.get("summary", response_text)
                issues = data.get("issues", [])

                raw_suggestions = data.get("suggestions", [])
                suggestions = []
                for s in raw_suggestions:
                    if isinstance(s, dict):
                        suggestions.append(f"[行{s.get('line', '?')}] {s.get('description', '')}")
                    else:
                        suggestions.append(str(s))
            except json.JSONDecodeError:
                pass

        return ReviewResult(
            filename=filename,
            element_name=element_name,
            element_type=element_type,
            element_line_start=line_start,
            element_line_end=line_end,
            summary=summary,
            issues=issues,
            suggestions=suggestions,
            raw_response=response_text
        )
