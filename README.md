# AI Code Reviewer

AI 辅助的代码审查工具，使用 Claude 分析 GitHub/GitLab PR diff 并提供项目级别的反馈。

## 功能特性

- **GitHub/GitLab 集成**: 在任意分支和主分支之间获取 diff
- **双分支完整代码**: 同时获取改动文件在两个分支的完整代码
- **完整调用链追踪**: 自动分析 A->B->C 这样的完整调用链路
- **调用链全覆盖**: 获取调用链涉及的所有类的完整代码（两分支版本）
- **AI 审查**: 将完整代码上下文 + diff + 调用链一起发送给 Claude
- **项目级别理解**: AI 可以看到完整的影响范围，而不仅仅是 diff

### 调用链追踪示例

当你修改了 `UserServiceImpl#updateUser()` 方法时，系统会自动发现：

```
UserController#handleUpdate <- Service#processUser <- UserServiceImpl#updateUser (已修改)
          ↓
   EmailService#sendNotification (可能受影响)
```

并且会将这些类的完整代码都发送给 AI，让 AI 基于完整的上下文进行审查！

## 安装

```bash
# 克隆仓库
cd ai-code-review

# 安装依赖
pip install -e ".[dev]"
```

## 配置

### 1. 创建 .env 文件

```bash
python -m ai_code_reviewer.cli init
```

### 2. 编辑 `.env` 添加凭据

```env
# Anthropic API (必需)
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# GitLab Token (可选)
GITLAB_TOKEN=your_gitlab_token_here

# GitHub Token (可选)
GITHUB_TOKEN=your_github_token_here

# 其他支持的提供者 (可选)
OPENAI_API_KEY=your_openai_key_here
QWEN_API_KEY=your_qwen_key_here
```

### 获取 API Key

#### Anthropic API Key
1. 访问 https://console.anthropic.com/dashboard
2. 创建新的 API 密钥
3. 复制到 `.env` 文件

#### GitLab Token
1. 访问 https://gitlab.com/profile/personal_access_tokens
2. 创建新令牌，勾选 `api` 范围
3. 复制到 `.env` 文件

#### GitHub Token
1. 访问 https://github.com/settings/tokens
2. 创建新令牌，勾选 `repo` 范围
3. 复制到 `.env` 文件

## 使用方法

### Web 界面启动

```bash
# 1. 确保 .env 文件已配置好 API KEY
# 2. 启动服务器
python run_server.py

# 3. 在浏览器打开 http://localhost:8000
#    - 输入 GitLab/GitHub 仓库地址 (如：owner/repo)
#    - 输入分支名称
#    - 点击开始审查
```

### CLI 命令行

```bash
# 使用 CLI 需要本地有 clone 的项目目录
cd /path/to/local/project

# 审查当前项目的某个分支
ai-review review --branch feature/my-feature

# 指定基分支和远程 token
ai-review review --branch develop --base main \
  --github-token YOUR_TOKEN --api-key YOUR_API_KEY
```

### Web 界面使用说明

Web 界面的工作流程：

1. **输入仓库信息**
   - Platform: 选择 GitLab 或 GitHub
   - Repo URL: 填写 `owner/repo` 格式（如 `mygroup/myproject`）

2. **输入分支信息**
   - Branch: 要审查的功能分支
   - Base: 基础分支（默认 master）

3. **输入 API Token**
   - GitLab Token: 从 GitLab Personal Access Tokens 获取
   - GitHub Token: 从 GitHub Settings > Developer Settings > Personal access tokens 获取

4. **输入 AI API Key**
   - Anthropic API Key: 用于 Claude 代码审查

5. **📝 手动指定相关文件 (可选)**
   - 如果你清楚改动涉及哪些文件，可以在此填写
   - 格式：用逗号分隔的文件路径列表
   - 示例：`src/service/UserService.java, src/controller/UserController.java`
   - **优势**: 避免下载整个项目，大大加快分析速度

6. **点击"开始审查"**
   - 系统会从远程获取 diff
   - 如果提供了手动文件列表，优先下载这些文件构建调用图
   - 如果未提供且项目较小，自动下载全部 Python 文件
   - 分析调用链并发送给 AI 审查
   - 显示审查结果

### 参数说明

| 参数 | 说明 |
|------|------|
| `-b, --branch` | 要审查的功能分支（必需） |
| `--base` | 基分支（默认：master） |
| `--platform` | 平台类型：gitlab（默认）或 github |
| `--repo` | 仓库地址，格式 owner/repo |
| `--gitlab-url` | GitLab 地址（仅当 platform=gitlab 时使用） |
| `--github-token` | GitHub token |
| `--gitlab-token` | GitLab token（或设置 GITLAB_TOKEN 环境变量） |
| `--api-key` | Anthropic API key（或设置 ANTHROPIC_API_KEY 环境变量） |
| `--model` | AI 模型（默认：claude-sonnet-4-20250929） |
| `--provider` | AI 提供商：anthropic（默认）、openai、qwen、doubao |
| `--project-root` | 代码分析的项目根目录（默认：当前目录） |

## 工作原理

### 完整的双分支代码审查流程

1. **获取 Diff**: 从 GitLab/GitHub API 获取功能分支与主分支之间的文件变更
   ```
   GET /projects/{id}/repository/compare?from=base&to=branch
   ```

2. **下载改动文件的完整代码**（两个分支版本）
   - 功能分支：该文件的完整源代码
   - 主分支：该文件的完整源代码
   - 这样 AI 可以对比改动前后的完整代码

3. **分析调用链**
   - 解析 AST 构建函数调用图
   - 向上追溯完整调用链（A -> B -> C）
   - 收集调用链涉及的所有类

4. **下载调用链相关文件的完整代码**（两个分支版本）
   - 调用链中涉及的所有类的完整代码
   - AI 可以看到完整的上下文，而不只是 diff 片段

5. **发送给 AI 审查**
   - 包含内容：
     - diff 内容（变更的具体行）
     - 改动文件的功能分支完整代码
     - 改动文件的主分支完整代码
     - 调用链涉及的所有类的完整代码
     - 调用链路径说明
   - AI 可以基于完整上下文进行全面评估

### 流程图

```
用户输入 (Web)        API          代码分析器           AI
    │                │                │              │
    ├─Repo URL ─────►│                │              │
    ├─Branch   ─────►│                │              │
    ├─Base      ─────►               │              │
    │                ▼                │              │
    │         1. 获取 Diff            │              │
    │                │                │              │
    │                ▼                │              │
    │    2. 下载改动文件的完整代码     │              │
    │    (功能分支 + 主分支两个版本)  │              │
    │                │                │              │
    │                ▼                │              │
    │    3. 分析调用链，获取相关类     │              │
    │                │                │              │
    │                ▼                │              │
    │    4. 下载调用链相关文件代码     │              │
    │       (功能分支 + 主分支)       │              │
    │                │                │              │
    │                ▼                │              │
    │    5. 组装完整上下文           │              │
    │       (diff + 完整代码 + 调用链)│              │
    │                │                │              │
    │                ▼                │              │
    │         6. 发送到 AI            │              │
    │                │                │              │
    │                ▼                │              │
    ◄───────────────回复结果─────────────────────────┤
```

### 优势

- **完整代码上下文**: AI 看到的是完整类代码，而不只是 diff 片段
- **双分支对比**: 同时提供改动前后的完整代码，便于对比分析
- **调用链全覆盖**: 调用链中所有相关类的完整代码都会发送给 AI
- **无需本地 clone**: 不需要把整个项目 clone 到本地即可分析
- **实时分析**: 直接分析远程仓库的最新代码

### 优势

- **无需本地 clone**: 不需要把整个项目 clone 到本地即可分析调用链
- **实时分析**: 直接分析远程仓库的最新代码
- **支持多语言**: 当前支持 Python，可扩展支持 Java、Go 等（只需调整 AST 解析器）

## 项目结构

```
ai-code-review/
├── src/ai_code_reviewer/
│   ├── __init__.py          # 包导出
│   ├── server.py            # FastAPI Web 服务器
│   ├── cli.py               # 命令行接口
│   ├── gitlab_diff.py       # GitLab/GitHub API 集成 + 远程文件获取
│   ├── code_analyzer.py     # 代码分析与调用链追踪
│   ├── ai_reviewer.py       # Claude API 集成
│   └── static/              # 静态资源
│       └── index.html       # Web 界面
├── run_server.py            # 启动脚本
├── pyproject.toml
└── README.md
```

## 开发

```bash
# 运行测试
pytest

# 格式化代码
black src tests

# 代码检查
ruff check src tests
```

## 常见问题

### Q: 如何选择 GitLab 还是 GitHub？
A: Web 界面可以自由选择。CLI 模式需要根据你使用的平台提供相应的 token。

### Q: 支持哪些 AI 模型？
A: 默认使用 Claude Sonnet 4，也支持 OpenAI、阿里云通义千问、火山引擎豆包等。

### Q: 为什么要远程获取文件而不是本地分析？
A: Web 模式下用户没有本地代码，必须通过 API 从远程获取。这样可以做到无需克隆整个项目就能进行调用链分析。

### Q: 项目很大怎么办？下载所有文件会不会很慢？
A: 这是当前的一个限制。对于超大型项目，可以考虑：
- 只分析特定目录下的文件
- 或者先在本地 clone 相关子项目，用 CLI 模式分析

### Q: 支持非 Python 语言吗？
A: 当前版本主要支持 Python（使用 Python 的 ast 模块）。对于 Java 等其他语言，需要扩展对应的 AST 解析器。

## License

MIT
