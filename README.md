# AI Code Reviewer

AI-powered code review tool that analyzes GitHub PR diffs and provides project-level feedback using Claude.

## Features

- **GitHub Integration**: Fetch diffs between any branch and master
- **Code Analysis**: Extract changed classes/methods and trace their references
- **AI Review**: Send code context to Claude for comprehensive review
- **Project-level Understanding**: Not just diff - analyzes full impact

## Installation

```bash
# Clone the repository
cd ai-code-reviewer

# Install dependencies
pip install -e ".[dev]"
```

## Configuration

1. Create `.env` file:
```bash
ai-review init
```

2. Edit `.env` with your credentials:
```env
GITHUB_TOKEN=your_github_token_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

### Getting GitHub Token

1. Go to https://github.com/settings/tokens
2. Create a new token with `repo` scope
3. Copy the token to `.env`

### Getting Anthropic API Key

1. Go to https://console.anthropic.com/dashboard
2. Create a new API key
3. Copy the key to `.env`

## Usage

### Basic Review

```bash
# Review a feature branch against master
ai-review review --branch feature/my-feature

# Specify base branch
ai-review review --branch develop --base main

# Specify repo explicitly
ai-review review --branch my-branch --repo owner/repo
```

### Options

| Option | Description |
|--------|-------------|
| `-b, --branch` | Feature branch to review (required) |
| `--base` | Base branch (default: master) |
| `-r, --repo` | GitHub repo in format owner/repo |
| `-t, --token` | GitHub token (or set GITHUB_TOKEN env) |
| `--api-key` | Anthropic API key (or set ANTHROPIC_API_KEY env) |
| `--model` | AI model to use (default: claude-sonnet-4-20250929) |
| `--project-root` | Project root for code analysis (default: .) |

## How It Works

1. **Fetch Diff**: Connects to GitHub API to get file changes between branches
2. **Analyze Code**:
   - Parses Python AST to extract changed classes/methods
   - Uses ripgrep to find all references in the project
   - Builds full context for each changed element
3. **AI Review**: Sends diff + context to Claude for analysis
4. **Report**: Displays structured review results

## Project Structure

```
ai-code-reviewer/
├── src/ai_code_reviewer/
│   ├── __init__.py        # Package exports
│   ├── github_diff.py     # GitHub API integration
│   ├── code_analyzer.py   # Code analysis & reference tracing
│   ├── ai_reviewer.py     # Claude API integration
│   └── cli.py             # Command-line interface
├── tests/
├── pyproject.toml
└── README.md
```

## Development

```bash
# Run tests
pytest

# Format code
black src tests

# Lint code
ruff check src tests
```

## License

MIT
