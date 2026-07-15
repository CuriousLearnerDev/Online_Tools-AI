# 自定义添加 HexStrike AI 工具说明

本文说明在本项目（统领 + HexStrike community 版）中，如何把**新工具**接入 AI / MCP / 接口调试。默认以 **community 版**为主；若你单独运行 **`storage/hexstrike_server.py` 单体服务**，见文末补充。

---

## 1. 架构与数据流（先读这段）

| 环节 | 作用 |
|------|------|
| **`tool_registry.py` 中的 `TOOLS`** | 工具目录元数据：`name`、`desc`、`endpoint`、`params` / `optional`，供 **`GET /api/tools`** 和统领「接口调试」拉列表。 |
| **`server_api/...` 里的 Blueprint 路由** | 实际执行工具，例如 **`POST /api/tools/你的工具名`**。 |
| **`mcp_tools/...` + `mcp_core/tool_profiles.py`** | MCP 暴露给外部 AI 客户端的函数（可选但推荐）。 |
| **`storage/tools_config.json`** | 统领 **`12.7下载优化.py`** 启动 Server 时注入 **Path**，并在回退逻辑里标记「已加载工具」；Python 类工具还与 **工作目录** 行为相关。 |
| **`GET /web-dashboard` 的 `tools_status`** | 接口调试里只显示 **`tools_status[工具名] === true`** 的项；需在健康检查里能探测到「已安装」。 |

Community 代码根目录：

`storage/hexstrike-ai-community-edition-master/`

---

## 2. Community 版：添加新工具（推荐按顺序做）

### 步骤 A：注册 HTTP 接口

1. 在合适子包下新增模块，例如 `server_api/vuln_scan/my_tool.py`（或新建子包）。
2. 定义 Blueprint，并实现 **`POST /api/tools/<工具名>`**（与下文中 registry 的 `endpoint` 一致）。
3. 在该子包的 **`__init__.py`** 中增加：`from .my_tool import *`（导出 Blueprint 变量）。
4. 在 **`server_api/__init__.py`** 的 **`register_blueprints(app)`** 里增加一行：  
   `app.register_blueprint(api_xxx_my_tool_bp)`  
   （变量名以你模块里定义的为准。）

**响应格式**：尽量与现有工具一致，例如包含 `success`、`stdout`、`stderr`、`return_code`、`command` 等，便于统领记录与排错。

**参考实现**：同目录下 `nuclei.py`（命令行）、`afrog.py` / `pocbomber.py`（子进程 + 日志 / ProcessManager）。

### 步骤 B：写入工具目录（`tool_registry.py`）

在 **`TOOLS`** 字典中增加一项，例如：

```python
"my_tool": {
    "desc": "一句话说明",
    "endpoint": "/api/tools/my_tool",
    "method": "POST",
    "category": "web_vuln",  # 与现有分类一致，见文件内其它项
    "params": {"target": {"required": True}},  # 必填参数；无则 "params": {}
    "optional": {"additional_args": ""},
    "effectiveness": 0.85,
},
```

- **`params`**：接口调试里会显示为带 `*` 的必填项（若 `required: True`）。
- **`optional`**：字符串默认 `""`，数字默认 `0`，布尔默认 `False`。

无需改 **`server_api/tools_catalog/routes.py`**：目录接口会遍历 `TOOLS`。

### 步骤 C：健康检查 / 接口调试「已安装」

接口调试用 **`GET /api/tools`** 与 **`GET /web-dashboard`** 的 **`tools_status`** 求交集。

- 在 **`server_core/tool_constants.py`** 的 **`HEALTH_TOOL_CATEGORIES`** 里，把工具名加到合适分类（例如 `"web_vuln"`）。
- 若工具**不是**系统 PATH 上的单一可执行文件名（例如是 **`python xxx.py`**），需要在 **`server_api/ops/system_monitoring.py`** 的 **`probe()`** 里像 **`pocbomber`** 一样单独写探测逻辑，否则 `which` 会一直为 false，列表里看不到。

### 步骤 D（可选）：MCP

1. 在 **`mcp_tools/<分类>/my_tool.py`** 中写 `register_xxx(mcp, hexstrike_client, logger)`，内部 **`hexstrike_client.safe_post("api/tools/my_tool", data)`**。
2. **`mcp_tools/<分类>/__init__.py`**：`from .my_tool import *`
3. **`mcp_core/tool_profiles.py`** 里把注册函数挂到合适 profile（如 **`vuln_scan`**）。

### 步骤 E（可选）：自动化测试

在 **`tests/test_endpoints_exist.py`** 中为 **`POST /api/tools/my_tool`** 增加路由存在性测试（与现有 `pocbomber` 等写法一致）。

---

## 3. 统领：`storage/tools_config.json`

统领启动 Server 时会把各工具的 **`path`** 拼进 **Path**，子进程继承 **`os.environ`**。

建议为可执行工具或 Python 工具增加一项（路径相对**项目根目录**，与 `12.7` 里 `root_path` 一致），例如：

```json
"my_tool": {
    "path": "storage/my_tool",
    "executable": "my_tool.exe",
    "type": "exe",
    "aliases": ["my_tool"]
}
```

Python 脚本示例：

```json
"pocbomber": {
    "path": "storage/POC-bomber",
    "executable": "pocbomber.py",
    "type": "python",
    "aliases": ["pocbomber"]
}
```

- 字段 **`script`** 与 **`executable`** 在统领里部分逻辑会兼容，建议与现有条目保持一致风格。
- **接口调试回退**：若 **`/web-dashboard`** 不可用，会用 **`tools_config.json`** 里「路径存在」的工具名与 **`/api/tools`** 做交集；路径填错会导致工具不出现在列表中。

---

## 4. Python 脚本类工具（易踩坑）

1. **工作目录（cwd）**  
   很多脚本依赖相对路径加载 POC/配置，请在 **`subprocess.Popen`** 中设置 **`cwd=脚本所在目录`**，命令行用 **`python pocbomber.py`** 这类形式，避免只改「绝对路径」仍扫不到资源。参考 **`server_api/vuln_scan/pocbomber.py`**。

2. **解释器**  
   统领已通过 Path 注入 **`storage/Python38`** 等目录；子进程应 **`env=os.environ`**（或默认继承），不要在未必要时写死长绝对路径，除非你明确要覆盖（如环境变量 **`POCBOMBER_PYTHON`**）。

3. **Windows 与编码**  
   需要时指定 **`encoding="utf-8", errors="replace"`**，必要时 **`stdin=subprocess.DEVNULL`**，避免挂起或乱码。

---

## 5. 单体服务 `storage/hexstrike_server.py`（若使用）

若 AI / 调试指向的是**根目录单体** `hexstrike_server.py`：

- 在该文件中增加 **`@app.route("/api/tools/...", methods=["POST"])`** 实现；
- 工具目录若依赖 **`tool_registry`**，需保证 **`storage/hexstrike-ai-community-edition-master`** 与 **`hexstrike_server.py`** 同目录，以便 **`GET /api/tools`** 能加载注册表（以你当前仓库实现为准）；
- **`/web-dashboard`** 与 **`tools_status`** 需与统领客户端约定字段一致。

---

## 6. 自检清单

- [ ] **`POST /api/tools/<name>`** 返回 200 且 body 合理  
- [ ] **`GET /api/tools`** 的 `tools` 数组里能看到新工具  
- [ ] **`GET /web-dashboard`** 中 **`tools_status.<name>`** 为 **`true`**（若要用接口调试筛选）  
- [ ] **`tools_config.json`** 路径存在且与统领根目录一致  
- [ ] （可选）MCP 客户端能调用新工具  

---

## 7. 推荐阅读源码（按复杂度）

| 工具 | 路径 | 说明 |
|------|------|------|
| nuclei | `server_api/vuln_scan/nuclei.py` | 命令行 + 参数拼装 |
| afrog | `server_api/vuln_scan/afrog.py` | 子进程流式输出、ProcessManager |
| pocbomber | `server_api/vuln_scan/pocbomber.py`、`server_core/pocbomber_paths.py` | Python 脚本、cwd、tools_config 解析、健康检查特例 |

---

**免责声明**：请仅在合法授权范围内使用安全测试工具；自定义 PoC/利用相关接口时务必遵守当地法律与目标系统授权范围。
