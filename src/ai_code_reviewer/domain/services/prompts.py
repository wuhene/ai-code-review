"""
提示词模板 - 用于 AI 代码审查。
"""

# 通用代码审查
GENERAL_PROMPT = """
你需要对代码变更进行全面的审查分析。

## 审查内容
1. 代码质量和最佳实践
2. 潜在的 bug 或问题
3. 安全问题
4. 性能影响
5. 可维护性和可读性

## 更改的文件
{filename}

## 代码变更 (Diff)
```diff
{diff_content}
```

## 完整代码上下文（带行号）
```
{context_code}
```

## 输出要求
请提供：
1. 更改的简要摘要
2. 发现的问题（严重程度：critical/high/medium/low），必须包含具体行号 line
3. 具体的改进建议，必须包含具体行号 line
4. 总体评估 (approve/needs changes/major revision needed)

请将你的响应格式化为 JSON：
{{
    "summary": "...",
    "issues": [
        {{"severity": "high", "description": "问题描述", "line": 10}}
    ],
    "suggestions": [
        {{"description": "建议描述", "line": 15}}
    ],
    "assessment": "approve"
}}
"""

# 安全代码审查
SECURITY_PROMPT = """
你是一位资深安全工程师，进行聚焦的安全代码审查。

## 审查目标
执行安全代码审查，识别高置信度（>80%）的安全漏洞。本次不是通用代码审查——只关注此PR新引入的安全问题，不要评论已有的问题。

## 关键指令
1. 最小化误报：只报告可利用性 >80% 的问题
2. 避免噪音：跳过理论性问题、风格问题或低影响发现
3. 关注影响：优先可能导致未授权访问、数据泄露或系统危害的漏洞
4. 不报告以下类型：
   - 拒绝服务（DOS）漏洞
   - 磁盘上存储的密钥或敏感数据
   - 限流或资源耗尽问题

## 安全审查类别

**输入验证漏洞：**
- SQL 注入（未参数化的用户输入）
- 命令注入（系统调用、子进程）
- XXE 注入（XML 解析）
- 模板注入
- NoSQL 注入
- 路径遍历（文件操作）

**认证与授权问题：**
- 认证绕过逻辑
- 权限提升路径
- 会话管理缺陷
- JWT 令牌漏洞
- 授权逻辑绕过

**加密与密钥管理：**
- 硬编码的 API 密钥、密码或令牌
- 弱加密算法或不安全实现
- 不当的密钥存储或管理
- 加密随机性问题
- 证书验证绕过

**注入与代码执行：**
- 反序列化远程代码执行
- Pickle 注入
- YAML 反序列化漏洞
- Eval 注入
- XSS 漏洞（反射型、存储型、DOM型）

**数据泄露：**
- 敏感数据日志记录或存储
- PII 处理违规
- API 端点数据泄露
- 调试信息泄露

**分析阶段：**

阶段1 - 仓库上下文研究：
- 识别现有安全框架和库
- 查找代码库中已有的安全编码模式

阶段2 - 对比分析：
- 将新代码变更与现有安全模式对比
- 识别与安全实践的偏差
- 标记引入新攻击面的代码

阶段3 - 漏洞评估：
- 检查每个修改文件的安全影响
- 追踪用户输入到敏感操作的数据流

## 更改的文件
{filename}

## 代码变更 (Diff)
```diff
{diff_content}
```

## 完整代码上下文（带行号）
```
{context_code}
```

## 输出要求
请根据上述代码进行安全审查，提供：
1. 更改的简要摘要
2. 发现的问题（严重程度：critical/high/medium/low），必须包含具体行号 line
3. 具体的改进建议，必须包含具体行号 line
4. 总体评估 (approve/needs changes/major revision needed)

## 严重程度指南
- **critical/high**: 可直接利用的漏洞，导致 RCE、数据泄露或认证绕过
- **medium**: 需要特定条件但有重大影响的漏洞
- **low**: 纵深防御问题或较低影响的漏洞

## 不报告以下类型
- 拒绝服务（DOS）漏洞或资源耗尽攻击
- 磁盘上存储的密钥/凭据
- 限流问题
- 内存消耗或 CPU 耗尽问题

请将你的响应格式化为 JSON（必须包含有效的 JSON，不要有额外文本）:
{{
    "summary": "...",
    "issues": [
        {{"severity": "high", "description": "问题描述", "line": 10}}
    ],
    "suggestions": [
        {{"description": "建议描述", "line": 15}}
    ],
    "assessment": "approve"
}}
"""


def build_prompt(request, review_type: str = "general") -> str:
    """
    构建审查提示词。

    Args:
        request: ReviewRequest 对象
        review_type: 审查类型 ("general" 或 "security")

    Returns:
        完整的 prompt
    """
    template = SECURITY_PROMPT if review_type == "security" else GENERAL_PROMPT

    return template.format(
        filename=request.filename,
        diff_content=request.diff_content,
        context_code=request.context_code
    )
