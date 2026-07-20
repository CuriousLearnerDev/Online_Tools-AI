# Code Audit Skill

<div align="center">

**AI 驱动的 Java/前端 代码安全审计框架**

[![Version](https://img.shields.io/badge/Version-1.10.0-blue.svg)](https://github.com/AuroraProudmoore/java-audit-skill/releases)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Java](https://img.shields.io/badge/Java/Kotlin-8%2B-orange.svg)](https://www.oracle.com/java/)
[![JavaScript](https://img.shields.io/badge/JS/TS/React/Vue-Supported-yellow.svg)](https://developer.mozilla.org/en-US/docs/Web/JavaScript)
[![AI](https://img.shields.io/badge/AI-LLM%20Driven-purple.svg)](https://en.wikipedia.org/wiki/Large_language_model)
[![Security](https://img.shields.io/badge/Security-Policy-green.svg)](SECURITY.md)

[中文文档](#中文文档) | [English Documentation](#english-documentation)

📧 Email: 997689721@qq.com
</div>

---

<a name="中文文档"></a>

## 中文文档

### 📖 概述

**Code Audit Skill** 是一个 AI 驱动的多语言代码安全审计框架，将资深安全审计员的方法论编码成 LLM 可执行的工作流协议。

**支持语言**：

| 语言类型 | 框架支持 | 主要检查内容 |
|----------|----------|--------------|
| **Java/Kotlin** | Spring、Spring Boot、Struts、Jersey | 反序列化、SQL注入、命令执行、SSRF |
| **JavaScript/TypeScript** | 原生、Node.js | XSS、代码注入、原型污染 |
| **React** | React 16+、Next.js | dangerouslySetInnerHTML、href注入 |
| **Vue** | Vue 2/3、Nuxt.js | v-html XSS、模板注入 |

**核心价值**：解决裸跑 LLM 做代码审计的三大痛点——**覆盖率低、幻觉高、优先级混乱**。

> **LLM 有能力，缺纪律。** 本框架不教 LLM "什么是 SQL 注入"，而是给它装上资深审计员的工作骨架——定义工作流、分配资源、设置护栏、标准化输出。

---

## 📁 脚本架构

**v1.10.0 架构重构：脚本按语言类型拆分，职责清晰**

```
scripts/
├── audit.py              # 通用入口（语言检测 + 路由分发）
├── java_audit.py         # Java/Kotlin 后端审计
└── frontend_audit.py     # JavaScript/React/Vue 前端审计
```

### 脚本职责

| 脚本 | 职责 | 包含功能 |
|------|------|----------|
| **audit.py** | 通用入口 | 语言检测、路由分发、统一参数解析 |
| **java_audit.py** | Java 审计 | Java Tier 分类、Java 危险模式、EALOC 计算、覆盖率检查 |
| **frontend_audit.py** | 前端审计 | 前端 Tier 分类、前端危险模式、依赖检查、配置安全 |

### 使用方法

```bash
# 自动检测语言并执行审计
python scripts/audit.py /path/to/project --scan --tier

# Java 项目审计（直接调用）
python scripts/java_audit.py /path/to/java-project --scan --tier

# 前端项目审计（直接调用）
python scripts/frontend_audit.py /path/to/frontend-project --language react --scan --tier
```

---

## ✨ 核心功能

### 1. 🔄 6 阶段审计流水线

从代码度量到标准化报告，每个阶段有明确的输入输出和质量标准。

```
Phase 0 → Phase 1 → Phase 2 → Phase 2.5 → Phase 3 → Phase 5 → Phase 4（可选）
 代码度量   项目侦察   多层审计   覆盖率门禁  漏洞验证  标准化报告   规则沉淀
```

| 阶段 | 功能 | 输入 | 输出 |
|------|------|------|------|
| **Phase 0** | 代码度量 | 项目源码 | audit-metrics.json（文件数、行数、EALOC） |
| **Phase 1** | 项目侦察 | pom.xml、源码 | Tier 分类、依赖安全检查、场景标签 |
| **Phase 2** | 多层审计 | L1 扫描结果 | findings-raw.md（候选漏洞列表） |
| **Phase 2.5** | 覆盖率门禁 | 审阅文件清单 | 覆盖率报告（必须达标才能继续） |
| **Phase 3** | 漏洞验证 | findings-raw.md | findings-verified.md（确认漏洞 + DKTSS 评分） |
| **Phase 5** | 标准化报告 | findings-verified.md | audit-report.md（最终报告） |
| **Phase 4** | 规则沉淀 | 确认漏洞模式 | custom-rules.yaml（Semgrep 规则） |

### 2. 📊 多层审计架构（Phase 2 内部）

Phase 2 包含 4 个层级，兼顾效率与深度：

| 层级 | 名称 | 作用 | 工具 |
|------|------|------|------|
| **Layer 1** | 全量预扫描 | 用 grep 快速扫描危险模式 | grep / Select-String |
| **Layer 2** | 双轨审计 | 追踪漏洞来源 + 检查权限控制 | LLM + Read |
| **Layer 2-Deep** | CoT 四步推理 | 逻辑漏洞深度分析 | LLM |
| **Layer 3** | 调用链验证 | 用 Read 验证每一跳 | Read |

### 3. 🚧 覆盖率门禁（核心创新）

**这是反 LLM 天性的核心设计**——LLM 倾向于跳过"看起来不重要"的代码，而漏洞偏偏喜欢藏在那些地方。

| 项目规模 | EALOC | 覆盖率要求 | T1 覆盖率 |
|----------|-------|------------|-----------|
| 小型 | < 15,000 | **100%** | **100%** |
| 中型 | 15,000 - 50,000 | **95%** | **100%** |
| 大型 | > 50,000 | **90%** | **100%** |

**T1 文件（Controller/Filter）必须 100% 覆盖，无例外。**

### 4. 🎯 DKTSS 评分体系

比 CVSS 更贴合实战的漏洞优先级评分标准。

```
Score = Base - Friction + Weapon + Ver
```

| 维度 | 说明 | 示例 |
|------|------|------|
| **Base** | 漏洞类型 + 实际影响 | SQL注入 = 8，RCE = 10 |
| **Friction** | 实战阻力 | 需要管理员权限 = -3，需要内网访问 = -2 |
| **Weapon** | 武器化程度 | 现成 EXP = +2，需要定制 = 0 |
| **Ver** | 版本因子 | 最新版本 = 0，旧版本 = +1 |

**评分示例**：

| 漏洞 | CVSS | DKTSS | 分析 |
|------|------|-------|------|
| 后台 SQL 注入 | 8.8 | 6 | 需要管理员权限，实战优先级降低 |
| 前台 Velocity SSTI | 9.8 | 10 | 无需认证 + 现成 EXP |
| 内网 SSRF | 7.5 | 5 | 需要内网访问 |

### 5. 🛡️ 反幻觉机制（7 条铁律）

确保报告可信度，避免 LLM 编造漏洞。

| # | 铁律 | 说明 |
|---|------|------|
| 1 | 文件存在验证 | 报告漏洞前必须用 Read 验证文件存在 |
| 2 | 代码真实性 | 代码片段必须来自实际 Read 输出，不得编造 |
| 3 | 行号标注 | 调用链每一跳必须标注 **文件:行号** |
| 4 | 状态标记 | 不确定标记为 HYPOTHESIS，不得标记为 CONFIRMED |
| 5 | 宁漏勿误 | 宁可漏报，不可误报 |
| 6 | **CVE 核实** | CVE 编号必须联网核实（用 tavily），禁止凭记忆编造 |
| 7 | **行号验证** | 行号必须用 Read 验证，禁止模糊范围 |

### 6. 🔗 调用链追踪

完整追踪从用户输入到危险 Sink 的调用路径：

```
AdminController.runCommand() (AdminController.java:67)
  → CmdController.executeCmd() (CmdController.java:45)
    → Runtime.exec() (危险 Sink)
```

---

## 📂 项目结构

```
java-audit-skill/
├── SKILL.md                    # 主协议文档（6阶段审计流水线）
├── README.md                   # 项目说明文档
├── REPORT-RULES.md             # 报告输出规范
├── CHANGELOG.md                # 版本更新记录
├── references/                 # 参考文档
│   ├── dktss-scoring.md        # DKTSS 评分体系
│   ├── vulnerability-conditions.md  # 漏洞成立判断条件
│   ├── logic-vulnerability-cot.md   # 逻辑漏洞 CoT 四步推理
│   ├── business-scenario-tags.md    # 业务场景标签系统
│   ├── security-checklist.md   # 安全检查清单（55+ 漏洞类型）
│   └── report-template.md      # 标准化报告模板
├── scripts/                    # 审计脚本
│   ├── java_audit.py           # 审计辅助脚本（跨平台）
│   ├── layer1-scan.ps1         # Layer 1 预扫描 (Windows)
│   ├── tier-classify.ps1       # Tier 分级脚本 (Windows)
│   └── coverage-check.ps1      # 覆盖率检查 (Windows)
├── rules/semgrep/              # Semgrep 规则（314条）
└── examples/                   # 审计报告示例
```

---

## 🚀 快速开始

### 环境要求

| 依赖 | 版本 | 用途 |
|------|------|------|
| Python | 3.8+ | 运行审计脚本 |
| PowerShell | 5.0+ | Windows 扫描命令 |
| Semgrep | 最新版 | Layer 1 扫描（可选） |

### 安装步骤

```bash
# 1. 克隆仓库
git clone https://github.com/AuroraProudmoore/java-audit-skill.git

# 2. 放置到 OpenClaw skills 目录
# Windows: C:\Users\<用户名>\.openclaw\workspace\skills\java-audit-skill\
# Linux/macOS: ~/.openclaw/workspace/skills/java-audit-skill/

# 3. 安装 Semgrep（可选，用于 Layer 1 扫描）
pip install semgrep
```

### 使用方式

#### 方式一：作为 OpenClaw Skill 使用（推荐）

在 OpenClaw 对话中触发：

```
帮我审计这个 Java 项目：E:\项目\demo-project
```

LLM 会自动执行完整的 6 阶段审计流程。

#### 方式二：独立使用脚本

**Phase 0: 代码度量**

```powershell
# 统计 Java 文件数
(Get-ChildItem -Recurse -Filter *.java).Count

# 统计代码行数
(Get-ChildItem -Recurse -Filter *.java | Get-Content | Measure-Object -Line).Lines

# 列出所有 Java 文件
Get-ChildItem -Recurse -Filter *.java | Select-Object -ExpandProperty FullName
```

**Phase 1: 项目侦察**

```powershell
# 读取 pom.xml
Get-Content pom.xml

# 统计 Controller 数量
Select-String -Path (Get-ChildItem -Recurse -Filter *.java).FullName -Pattern "@Controller|@RestController"

# 检查权限注解
Select-String -Path (Get-ChildItem -Recurse -Filter *.java).FullName -Pattern "@PreAuthorize|hasRole"
```

**Phase 2 Layer 1: 危险模式预扫描**

```powershell
# P0 级（严重）- 反序列化
Select-String -Path (Get-ChildItem -Recurse -Filter *.java).FullName -Pattern "ObjectInputStream|JSON\.parseObject|Runtime\.getRuntime|ProcessBuilder"

# P1 级（高危）- SQL 注入
Select-String -Path (Get-ChildItem -Recurse -Filter *.xml).FullName -Pattern '\$\{'

# P1 级（高危）- SSRF
Select-String -Path (Get-ChildItem -Recurse -Filter *.java).FullName -Pattern "URL\(|HttpClient|RestTemplate"
```

**Phase 2 Layer 2: 双轨审计**

LLM 自动执行，对 Layer 1 发现的问题点追踪验证。

**Phase 3: 漏洞验证**

```bash
# 使用 tavily 搜索 CVE
node ~/.openclaw/workspace/skills/tavily-search/scripts/search.mjs "netty 4.1.107 CVE" -n 10
```

---

## 📋 详细流程说明

### Phase 0: 代码库度量

**目标**：统计项目规模，判断是小型/中型/大型项目。

**执行步骤**：

```powershell
# Step 1: 统计文件数
$javaFiles = (Get-ChildItem -Recurse -Filter *.java).Count

# Step 2: 统计代码行数
$loc = (Get-ChildItem -Recurse -Filter *.java | Get-Content | Measure-Object -Line).Lines

# Step 3: 统计入口点数量
$controllers = Select-String -Path (Get-ChildItem -Recurse -Filter *.java).FullName -Pattern "@Controller|@RestController"

# Step 4: 计算 EALOC
# EALOC = T1_LOC × 1.0 + T2_LOC × 0.5 + T3_LOC × 0.1
```

**输出文件**：`audit-metrics.json`

```json
{
  "java_files": 18,
  "total_loc": 779,
  "controllers": 11,
  "ealoc": 6500,
  "project_size": "小型",
  "coverage_requirement": "100%"
}
```

### Phase 1: 项目侦察

**目标**：识别技术栈、关键依赖、Tier 分类。

**执行步骤**：

```powershell
# Step 1: 读取 pom.xml 获取依赖
Read pom.xml

# Step 2: 识别入口点（T1 级文件）
Select-String -Pattern "@Controller|@RestController|@WebServlet|extends HttpServlet"

# Step 3: 检查权限控制
Select-String -Pattern "@PreAuthorize|@Secured|hasRole|permitAll"

# Step 4: 依赖安全检查（使用 tavily）
node ~/.openclaw/workspace/skills/tavily-search/scripts/search.mjs "netty 4.1.107 CVE" -n 10
```

**Tier 分类规则**：

| Tier | 文件类型 | 分析深度 | 权重 |
|------|----------|----------|------|
| T1 | Controller、Filter、Servlet、Action | 完整深度分析 | × 1.0 |
| T2 | Service、DAO、Util、配置文件 | 聚焦关键维度 | × 0.5 |
| T3 | Entity、VO、DTO | 快速模式匹配 | × 0.1 |

### Phase 2: 多层审计

#### Layer 1: 全量预扫描

**目标**：用 grep 快速扫描，找出危险模式候选点。

```powershell
# P0 级扫描
Get-ChildItem -Recurse -Include *.java | Select-String -Pattern "ObjectInputStream|JSON\.parseObject|Runtime\.getRuntime|Velocity\.evaluate|InitialContext\.lookup"

# P1 级扫描
Get-ChildItem -Recurse -Include *.java | Select-String -Pattern "Statement|createStatement|\$\{|URL\(|FileInputStream|MultipartFile"

# P2 级扫描
Get-ChildItem -Recurse -Include *.java | Select-String -Pattern "@PreAuthorize|permitAll|MessageDigest|MD5"
```

**输出文件**：`p0-critical.md`、`p1-high.md`、`p2-medium.md`

#### Layer 2: 双轨审计

**轨道 1: Sink-driven**（从危险代码往上追）

```
发现 Runtime.exec(cmd)
  ↓ Read 读取代码
  ↓ 追踪 cmd 参数来源
  ↓ 搜索调用者
  ↓ 判断是否用户可控
  ↓ 结论：漏洞 / 安全
```

**轨道 2: Control-driven**（从入口往下查权限）

```
列出所有 Controller 入口
  ↓ Read 读取每个 Controller
  ↓ 检查是否有 @PreAuthorize
  ↓ 无权限注解 + 敏感操作 = 漏洞
```

#### Layer 2-Deep: 逻辑漏洞 CoT 四步推理

**执行时机**：当发现资金交易、状态变更等敏感接口时。

```
Step 1: 场景与入口识别 → 识别 API 功能场景
Step 2: 防御机制审计 → 寻找代码中的"锁"和"盾"
Step 3: 对抗性沙箱模拟 → 设计 PoC
Step 4: 漏洞结果判定 → 给出负责任结论
```

#### Layer 3: 调用链语义级验证

**目标**：用 Read 验证 Layer 2 追踪的调用链是否正确。

```
Layer 2 输出的调用链:
  Controller → Service → Runtime.exec

Layer 3 验证:
  ↓ Read Controller.java 确认入口
  ↓ Read Service.java 确认调用
  ↓ Read 实际执行点确认危险代码
  ↓ 检查是否有条件分支阻断
  ↓ 结论：调用链正确 / 有阻断
```

### Phase 2.5: 覆盖率门禁

**检查逻辑**：

```
已审计文件列表 vs 实际文件列表
  ↓
diff 对比
  ↓
覆盖率达标 → 进入 Phase 3
覆盖率不达标 → 返回 Phase 2 补扫遗漏文件
```

### Phase 3: 漏洞验证

**核心任务**：

1. 应用反幻觉 7 条铁律
2. CVE 联网核实（用 tavily）
3. DKTSS 评分
4. 状态标记（CONFIRMED / HYPOTHESIS）

**输出文件**：`findings-verified.md`

### Phase 5: 标准化报告

**报告结构**（v1.8.0 新格式）：

```markdown
## 漏洞列表

| 序号 | 漏洞名称 |
|------|---------|
| 1 | [漏洞名称1] |
| 2 | [漏洞名称2] |

---

## 审计进度

| 审计层级 | 进度 | 说明 |
|---------|------|------|
| L1 危险模式扫描 | ✅ 已完成 | 发现 X 个候选漏洞 |
| L2 双轨审计 | ✅ 已完成 | 确认 Y 个有效漏洞 |
| L3 调用链验证 | ✅ 已完成 | 全部漏洞已验证 |

---

## 详细漏洞报告

# [漏洞名称]

### 描述
[100字左右，漏洞类型 + 成因 + 核心风险点]

### 漏洞详情

**代码位置**：
[完整绝对路径]:[行号]

**问题代码展示**：
```java
// 带上下文的实际代码
```

**漏洞分析**：
[300字以上，包含 6 要素]

### 修复建议
[完整解决方案 + 可执行代码示例]
```

**漏洞分析 6 要素**：

| # | 要素 | 说明 |
|---|------|------|
| 1 | 调用链追踪 | 每一跳标注 文件:行号 |
| 2 | 缺少的安全控制 | 表格形式 |
| 3 | 攻击路径 | 步骤形式（1、2、3...） |
| 4 | 对比分析 | 与安全代码的差异 |
| 5 | 未使用的安全机制 | 项目中存在但未启用 |
| 6 | 漏洞类型归纳 | CWE 标准分类 |

**格式规范**：

| 内容 | 标签 | 说明 |
|------|------|------|
| 漏洞名称 | `#` (h1) | 单独一行，禁止添加严重程度标签 |
| 描述 | `###` (h3) | 100字左右 |
| 漏洞详情 | `###` (h3) | 代码位置 + 代码展示 + 漏洞分析 |
| 修复建议 | `###` (h3) | 完整解决方案 |

---

## 🔍 覆盖的漏洞类型

### Java/Kotlin 后端漏洞

#### P0 级（严重）

| 类型 | 具体漏洞 |
|------|---------|
| **反序列化** | Fastjson、Jackson、XStream、Hessian、Java 原生序列化 |
| **SSTI** | Velocity、FreeMarker、Thymeleaf |
| **表达式注入** | SpEL、OGNL |
| **JNDI 注入** | InitialContext.lookup |
| **命令执行** | Runtime.exec、ProcessBuilder |

#### P1 级（高危）

| 类型 | 具体漏洞 |
|------|---------|
| **SQL 注入** | MyBatis `${}`、JDBC 原生拼接 |
| **SSRF** | URL、HttpClient、RestTemplate |
| **文件操作** | 路径穿越、任意文件上传/读取 |
| **XXE** | DocumentBuilder、SAXParser |

#### P2 级（中危）

| 类型 | 具体漏洞 |
|------|---------|
| **认证授权** | 越权访问、认证绕过 |
| **加密安全** | 弱哈希算法、硬编码密钥 |
| **信息泄露** | 敏感信息日志、错误信息暴露 |

### 前端漏洞（JavaScript/React/Vue）

#### P0 级（严重）

| 类型 | 具体漏洞 |
|------|---------|
| **XSS** | innerHTML、dangerouslySetInnerHTML、v-html |
| **代码注入** | eval()、new Function()、setTimeout(字符串) |

#### P1 级（高危）

| 类型 | 具体漏洞 |
|------|---------|
| **原型污染** | Object.assign、_.merge、_.extend |
| **敏感信息泄露** | localStorage 存储 token、硬编码密钥 |
| **开放重定向** | 未验证的 redirect 参数 |

#### P2 级（中危）

| 类型 | 具体漏洞 |
|------|---------|
| **配置安全** | CORS 配置不当、CSP 缺失 |
| **不安全随机数** | Math.random() 用于安全场景 |

### 依赖安全检查

#### Java 依赖（mvnrepository.com 联网核实）

| 依赖 | 危险版本 | 安全版本 |
|------|----------|----------|
| Log4j2 | < 2.17.1 | ≥ 2.17.1 |
| Fastjson | < 1.2.83 | ≥ 1.2.83 |
| Shiro | < 1.13.0 | ≥ 1.13.0 |
| Netty | < 4.1.129 | ≥ 4.1.129 |

#### 前端依赖（npm audit 实时检查）

| 依赖 | 检查方式 |
|------|----------|
| 所有依赖 | npm audit / yarn audit |
| 漏洞数据库 | npm 官方漏洞数据库 |

---

## 🎯 适用场景

### Java/Kotlin 后端审计

- ✅ Java/Kotlin 项目的 **0day 漏洞挖掘**
- ✅ 企业级代码库的**安全审计**
- ✅ **CI/CD 集成**的前期漏洞发现
- ✅ 甲方安全建设（代码审计标准化）
- ✅ 安全培训（审计方法论学习）

### 前端审计（JavaScript/React/Vue）

- ✅ 前端项目的 **XSS 漏洞挖掘**
- ✅ 单页应用（SPA）**安全评估**
- ✅ 前后端分离项目的**前端安全审计**
- ✅ 前端依赖安全检查
- ✅ 前端配置安全审计

---

## 📚 参考文档

| 文档 | 说明 |
|------|------|
| [SKILL.md](SKILL.md) | 完整协议文档 |
| [REPORT-RULES.md](REPORT-RULES.md) | 报告输出规范 |
| [references/dktss-scoring.md](references/dktss-scoring.md) | DKTSS 评分体系 |
| [references/vulnerability-conditions.md](references/vulnerability-conditions.md) | 漏洞成立条件 |
| [references/security-checklist.md](references/security-checklist.md) | 安全检查清单 |
| [references/report-template.md](references/report-template.md) | 报告模板 |

---

## 🤝 贡献指南

欢迎贡献！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解详情。

**贡献方向**：
- 🐛 报告 Bug
- 💡 提出新功能建议
- 📝 改进文档
- 🔧 贡献代码
- 📋 分享审计案例

---

## 📄 许可证

本项目采用 [MIT License](LICENSE) 开源协议。

---

<a name="english-documentation"></a>

## English Documentation

### Overview

**Code Audit Skill** is an AI-powered multi-language code security audit framework that encodes senior security auditors' methodologies into LLM-executable workflow protocols.

**Supported Languages**:

| Language | Frameworks | Main Checks |
|----------|------------|-------------|
| **Java/Kotlin** | Spring, Spring Boot, Struts | Deserialization, SQLi, RCE, SSRF |
| **JavaScript/TypeScript** | Native, Node.js | XSS, Code Injection, Prototype Pollution |
| **React** | React 16+, Next.js | dangerouslySetInnerHTML, href Injection |
| **Vue** | Vue 2/3, Nuxt.js | v-html XSS, Template Injection |

**Core Value**: Solves the three main pain points of using LLMs for code auditing—**low coverage, high hallucination, and chaotic prioritization**.

> **LLMs have capability but lack discipline.** This framework doesn't teach LLMs "what is SQL injection"—it equips them with the work framework of senior auditors.

---

## ✨ Core Features

### 1. 🔄 6-Phase Audit Pipeline

```
Phase 0 → Phase 1 → Phase 2 → Phase 2.5 → Phase 3 → Phase 5 → Phase 4 (Optional)
 Metrics    Recon     Audit     Coverage    Verify    Report    Rules
```

### 2. 📊 Multi-Layer Audit Architecture

| Layer | Purpose | Tool |
|-------|---------|------|
| **Layer 1** | Full pre-scan | grep / Select-String |
| **Layer 2** | Dual-track audit | LLM |
| **Layer 2-Deep** | CoT reasoning | LLM |
| **Layer 3** | Call chain verification | Read |

### 3. 🚧 Coverage Gate

| Project Size | EALOC | Coverage Requirement |
|--------------|-------|---------------------|
| Small | < 15,000 | **100%** |
| Medium | 15,000 - 50,000 | **95%** |
| Large | > 50,000 | **90%** |

### 4. 🎯 DKTSS Scoring

```
Score = Base - Friction + Weapon + Ver
```

### 5. 🛡️ Anti-Hallucination (7 Iron Rules)

1. Must verify file exists
2. Code must come from actual Read output
3. Every hop must have file:line annotation
4. Mark uncertain findings as HYPOTHESIS
5. Better to miss than false positive
6. **CVE numbers must be verified online**
7. **Line numbers must be verified with Read**

---

## 🚀 Quick Start

### Requirements

- Python 3.8+
- PowerShell 5.0+
- Semgrep (optional)

### Installation

```bash
# Clone repository
git clone https://github.com/AuroraProudmoore/java-audit-skill.git

# Place in OpenClaw skills directory
# Windows: C:\Users\<user>\.openclaw\workspace\skills\java-audit-skill\
# Linux/macOS: ~/.openclaw/workspace/skills/java-audit-skill/

# Install Semgrep (optional)
pip install semgrep
```

### Usage

**Option 1: As OpenClaw Skill (Recommended)**

```
Help me audit this Java project: E:\project\demo
```

**Option 2: Standalone Scripts**

```powershell
# Phase 0: Metrics
(Get-ChildItem -Recurse -Filter *.java).Count

# Phase 1: Reconnaissance
Select-String -Pattern "@Controller|@RestController"

# Phase 2 Layer 1: Pre-scan
Select-String -Pattern "Runtime\.getRuntime|JSON\.parseObject"

# Phase 3: CVE Verification
node ~/.openclaw/workspace/skills/tavily-search/scripts/search.mjs "netty 4.1.107 CVE" -n 10
```

---

## 🔍 Vulnerability Coverage

### Java/Kotlin Backend

#### P0 (Critical)

- Deserialization: Fastjson, Jackson, Hessian
- SSTI: Velocity, FreeMarker, Thymeleaf
- RCE: Runtime.exec, ProcessBuilder

#### P1 (High)

- SQL Injection: MyBatis `${}`, JDBC concatenation
- SSRF: URL, HttpClient, RestTemplate
- File Operations: Path traversal, arbitrary upload

#### P2 (Medium)

- Authentication: Access bypass, auth bypass
- Cryptography: Weak hashing, hardcoded keys

### Frontend (JavaScript/React/Vue)

#### P0 (Critical)

- XSS: innerHTML, dangerouslySetInnerHTML, v-html
- Code Injection: eval(), new Function()

#### P1 (High)

- Prototype Pollution: Object.assign, _.merge
- Sensitive Data: localStorage token, hardcoded keys
- Open Redirect: Unvalidated redirect parameter

#### P2 (Medium)

- Configuration: CORS misconfiguration, missing CSP
- Insecure Random: Math.random() for security

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [SKILL.md](SKILL.md) | Full protocol documentation |
| [REPORT-RULES.md](REPORT-RULES.md) | Report output rules |
| [references/dktss-scoring.md](references/dktss-scoring.md) | DKTSS scoring system |
| [references/security-checklist.md](references/security-checklist.md) | Security checklist |

---

## 🤝 Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

<div align="center">

**Made with ❤️ by Security Researchers**

[⬆ Back to Top](#code-audit-skill)

</div>
