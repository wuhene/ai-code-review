# AI Code Reviewer

AI 辅助的代码审查工具，使用大语言模型分析 GitHub/GitLab 分支 diff 并提供代码审查建议。

## 架构

采用 DDD 四层架构：

```
src/ai_code_reviewer/
├── domain/                      # 领域层
│   ├── entities/               # 实体
│   │   ├── code_element.py
│   │   ├── file_diff.py
│   │   ├── remote_file.py
│   │   ├── review_request.py
│   │   └── review_result.py
│   └── services/              # 领域服务
│       ├── ai_reviewer.py
│       └── element_extractor.py
│
├── application/                # 应用层
│   └── review_service.py      # 协调 domain 和 infra
│
├── infrastructure/            # 基础设施层
│   ├── git/
│   │   ├── git_client_base.py
│   │   ├── github_client.py
│   │   ├── gitlab_client.py
│   │   └── git_factory.py
│   └── llm/
│       ├── llm_client_base.py
│       ├── anthropic_client.py
│       ├── openai_client.py
│       └── llm_factory.py
│
└── web/                      # 表现层
    ├── server.py
    └── static/
```

| 层级 | 职责 |
|------|------|
| domain | 核心业务逻辑（元素提取、AI审查）|
| application | 用例编排，协调领域服务 |
| infrastructure | 外部服务集成（GitHub/GitLab API、LLM API）|
| web | HTTP 请求/响应处理 |

## 安装

```bash
pip install -e .
```

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
