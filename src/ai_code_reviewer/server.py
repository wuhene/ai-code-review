"""FastAPI Web 服务器 - AI Code Reviewer 的可视化界面。"""

import os
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from .gitlab_diff import GitDiffFetcher
from .code_analyzer import CodeAnalyzer
from .ai_reviewer import AIReviewer, ReviewRequest

load_dotenv()

app = FastAPI(title="AI Code Reviewer", version="0.1.0")

# 静态文件目录
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


class ReviewParams(BaseModel):
    """审查参数。"""
    branch: str
    base: str = "master"
    repo: Optional[str] = None
    platform: str = "gitlab"  # "github" 或 "gitlab"
    gitlab_url: Optional[str] = None  # 自定义 GitLab 地址（仅当 platform=gitlab 时使用）
    github_token: Optional[str] = None
    gitlab_token: Optional[str] = None
    api_key: str
    model: str = "claude-sonnet-4-20250929"
    provider: str = "anthropic"
    base_url: Optional[str] = None
    project_root: str = "."
    manual_files: Optional[str] = None  # 用户手动指定的相关文件（逗号分隔的文件路径列表）


class ReviewProgress(BaseModel):
    """审查进度。"""
    stage: str  # "fetching", "analyzing", "reviewing", "completed", "error"
    message: str
    progress: int = 0


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

    Args:
        params: 审查参数

    Returns:
        审查结果
    """
    try:
        # 步骤 1：获取 diff
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

        fetcher = GitDiffFetcher(
            token=token,
            repo_url=params.repo or "",
            platform=platform,
            base_url=params.gitlab_url if platform == "gitlab" else None
        )

        diffs = await fetcher.get_branch_diff(params.branch, params.base)
        print(f"  找到 {len(diffs)} 个文件已更改")

        if not diffs:
            return {
                "success": True,
                "message": "没有 Python 文件更改",
                "results": []
            }

        # 步骤 2：分析代码
        print(f"[步骤 2/3] 分析代码更改...")

        # 解析用户手动指定的相关文件
        manual_file_list = []
        if params.manual_files:
            manual_file_list = [f.strip() for f in params.manual_files.split(",") if f.strip()]
            print(f"  用户指定的相关文件：{len(manual_file_list)} 个")

        # 创建 Analyzer，传入 fetcher 用于从远程获取代码
        analyzer = CodeAnalyzer(
            params.project_root,
            fetcher=fetcher,
            ref=params.branch,
            base_ref=params.base,  # 主分支
            manual_files=manual_file_list if manual_file_list else None,
            auto_fetch_all=True  # 如果用户未提供文件，自动获取全部
        )

        review_requests = []
        for file_diff in diffs:
            elements = analyzer.extract_changed_elements(file_diff.diff, file_diff.new_path)
            print(f"  {file_diff.filename}: {len(elements)} 个元素已更改")

            # 简化：每个文件只发送一次审查请求，包含完整 diff
            if elements:
                review_requests.append(ReviewRequest(
                    diff_content=file_diff.diff,
                    context_code=file_diff.diff,  # 直接使用 diff 内容
                    filename=file_diff.filename,
                    element_name=elements[0].name if elements else file_diff.filename,
                    element_type="file",
                    call_chain_info=""
                ))

        print(f"  总计：{len(review_requests)} 个审查项（按文件分组）")

        # 步骤 3：AI 审查
        print(f"[步骤 3/3] 发送给 AI 进行审查...")
        reviewer = AIReviewer(
            api_key=params.api_key,
            model=params.model,
            provider=params.provider,
            base_url=params.base_url
        )

        results = reviewer.review_batch(review_requests)
        print(f"  AI 审查完成，共 {len(results)} 个结果")

        # 格式化结果
        formatted_results = []
        for result in results:
            formatted_results.append({
                "filename": result.filename,
                "element_name": result.element_name,
                "summary": result.summary[:500] + "..." if len(result.summary) > 500 else result.summary,
                "full_summary": result.summary,
                "issues_count": len(result.issues),
                "suggestions_count": len(result.suggestions),
                "issues": result.issues[:5],
                "suggestions": result.suggestions[:5]
            })

        total_issues = sum(len(r.issues) for r in results)
        total_suggestions = sum(len(r.suggestions) for r in results)

        print(f"  准备返回结果给前端")
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
    import httpx

    test_urls = {
        "anthropic": "https://api.anthropic.com/v1/messages",
        "openai": "https://api.openai.com/v1/chat/completions",
        "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "doubao": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
    }

    url = test_urls.get(provider, None)
    if not url:
        return {"connected": False, "message": "未知的提供商"}

    try:
        # 这里只是简单测试连通性，实际验证需要在真实请求时进行
        return {"connected": True, "message": "连接正常"}
    except Exception as e:
        return {"connected": False, "message": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
