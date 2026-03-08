#!/usr/bin/env python3
"""AI Code Reviewer Web 服务器启动脚本."""

import uvicorn

if __name__ == "__main__":
    print("AI Code Reviewer - Web Server")
    print("Web UI: http://localhost:8000")
    print("API Docs: http://localhost:8000/docs")
    print("-----------------------------------")
    uvicorn.run("ai_code_reviewer.server:app", host="0.0.0.0", port=8000, reload=True)
