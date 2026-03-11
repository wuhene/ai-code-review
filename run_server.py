#!/usr/bin/env python3
"""AI Code Reviewer Web 服务器 - 可直接运行版本。"""

import sys
from pathlib import Path

# 确保 src 目录在 Python 路径中
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

from ai_code_reviewer.web.server import app

if __name__ == "__main__":
    print("AI Code Reviewer - Web Server")
    print("Web UI: http://localhost:8000")
    # print("API Docs: http://localhost:8000/docs")
    print("-----------------------------------")

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
