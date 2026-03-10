# AI Code Reviewer

AI 辅助的代码审查工具，使用大语言模型分析 GitHub/GitLab 分支 diff 并提供代码审查建议。

## 启动

```bash
python run_server.py
```

然后在浏览器打开 http://localhost:8000

## 使用

1. 选择平台（GitLab 或 GitHub）
2. 填写仓库地址（如 `owner/repo`）
3. 填写分支名称
4. 填写 API Token
5. 点击开始审查

## 支持的 AI 提供商

| 提供商 | 模型示例 |
|--------|----------|
| Anthropic | claude-sonnet-4-20250929 |
| OpenAI | gpt-4o |
| 阿里云通义千问 | qwen-plus, qwen3.5-plus |
| 火山引擎豆包 | doubao-pro-32k |
