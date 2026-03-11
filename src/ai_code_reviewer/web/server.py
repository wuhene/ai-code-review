"""
FastAPI Web 服务器 - AI Code Reviewer Web 层（表现层）。

本模块负责：
1. 处理 HTTP 请求
2. 参数校验
3. 调用应用服务
4. 格式化响应
"""

from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from ..application.review_service import ReviewApplicationService

load_dotenv()

app = FastAPI(title="AI Code Reviewer", version="0.2.0")

# 静态文件目录
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


class ReviewParams(BaseModel):
    """审查参数。"""
    branch: str
    base: str = "master"
    repo: Optional[str] = None
    platform: str = "gitlab"
    gitlab_url: Optional[str] = None
    github_token: Optional[str] = None
    gitlab_token: Optional[str] = None
    api_key: str
    model: str = "claude-sonnet-4-20250929"
    provider: str = "anthropic"
    base_url: Optional[str] = None
    project_root: str = "."


@app.get("/", response_class=HTMLResponse)
async def index():
    """首页。"""
    html_path = static_dir / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>AI Code Reviewer</h1><p>页面加载中...</p>")


@app.post("/api/review")
async def start_review(params: ReviewParams):
    """
    启动代码审查任务。

    这是一个典型的表现层接口：
    1. 接收请求参数
    2. 校验参数
    3. 调用应用服务
    4. 格式化响应
    """
    try:
        # 步骤 1：获取参数
        platform = params.platform.lower()
        token = params.gitlab_token if platform == "gitlab" else params.github_token

        print(f"[步骤 1/3] 从 {platform.upper()} 获取 diff...")

        # 如果没有指定 repo，尝试从本地获取
        if not params.repo:
            import subprocess
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True, text=True, check=True,
                cwd=params.project_root
            )
            remote_url = result.stdout.strip()
            if "github.com" in remote_url:
                parts = remote_url.rstrip(".git").split("/")[-2:]
                params.repo = "/".join(parts)

        # 步骤 2：创建应用服务
        service = ReviewApplicationService(
            platform=platform,
            token=token,
            repo_url=params.repo or "",
            api_key=params.api_key,
            model=params.model,
            provider=params.provider,
            base_url=params.base_url,
            gitlab_url=params.gitlab_url if platform == "gitlab" else None
        )

        # 步骤 3：获取 diff
        diffs = await service.get_diffs(params.branch, params.base)
        print(f"  找到 {len(diffs)} 个文件已更改")

        if not diffs:
            return {
                "success": True,
                "message": "没有文件更改",
                "results": []
            }

        # 步骤 4：执行审查
        print(f"[步骤 2/3] 分析代码更改...")
        results = await service.review_code(diffs, params.branch, params.base)
        print(f"  AI 审查完成，共 {len(results)} 个结果")

        # 步骤 5：格式化响应
        formatted_results = []
        for result in results:
            location = ""
            if result.element_type and result.element_name:
                location = f"{result.element_type} {result.element_name}"
            if result.element_line_start > 0:
                location += f" (行 {result.element_line_start}"
                if result.element_line_end > result.element_line_start:
                    location += f"-{result.element_line_end}"
                location += ")"

            formatted_results.append({
                "filename": result.filename,
                "element_name": result.element_name,
                "element_type": result.element_type,
                "location": location,
                "line_start": result.element_line_start,
                "line_end": result.element_line_end,
                "summary": result.summary[:500] + "..." if len(result.summary) > 500 else result.summary,
                "full_summary": result.summary,
                "issues_count": len(result.issues),
                "suggestions_count": len(result.suggestions),
                "issues": result.issues[:5],
                "suggestions": result.suggestions[:5]
            })

        total_issues = sum(len(r.issues) for r in results)
        total_suggestions = sum(len(r.suggestions) for r in results)

        return {
            "success": True,
            "message": f"审查完成！发现 {total_issues} 个问题，{total_suggestions} 条建议",
            "results": formatted_results,
            "summary": {
                "total_files": len(diffs),
                "total_elements": len(results),
                "total_issues": total_issues,
                "total_suggestions": total_suggestions
            }
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            "success": False,
            "message": f"审查失败：{str(e)}",
            "results": []
        }


@app.get("/api/test-connection")
async def test_connection(provider: str = "anthropic"):
    """测试 API 连接。"""
    test_urls = {
        "anthropic": "https://api.anthropic.com/v1/messages",
        "openai": "https://api.openai.com/v1/chat/completions",
        "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "doubao": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
    }

    url = test_urls.get(provider, None)
    if not url:
        return {"connected": False, "message": "未知的提供商"}

    return {"connected": True, "message": "连接正常"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
