# 统领 Web 独立版

本项目是从 [统领工具](https://github.com/CuriousLearnerDev/Online_tools) 中分离出来的 **AI 渗透 Web 控制台**，可脱离统领桌面端单独运行。

在 Windows 原版基础上做了跨平台适配，目前可在 **Windows / Linux / macOS** 上正常使用。

---

## 功能概览

- **AI 渗透终端**：浏览器内 Web 终端，对接 Claude Code + HexStrike MCP 工具链
- **扫描图谱**：可视化展示扫描会话中的工具调用与探测关系
- **扫描报告**：自动收录 Markdown 渗透报告，支持大纲预览
- **任务监控**：查看后台扫描进程与审计任务
- **社交接入**：钉钉 Stream / Telegram / QQ（OneBot）与终端双向联动
- **内网穿透**：NPS `npc` 命令行模式，便于手机或外网访问
- **指纹库 / POC 库**：Nuclei、HFinger 等库管理与同步

---

## 环境要求

| 项目 | 说明 |
|------|------|
| Python | **3.10+**（推荐 3.11） |
| 操作系统 | Windows / Linux / macOS |
| 网络 | 本机访问无需外网；AI 终端与工具下载需联网 |
| 浏览器 | Chrome / Edge / Firefox 等现代浏览器 |

**已内置（本仓库已包含）：**

- `storage/hexstrike-ai-community-edition-master/` — HexStrike CE 服务端（**启动必需**）
- `storage/nuclei/nuclei-templates/` — Nuclei 漏洞模板（**漏洞库**，随 `独立Web.cmd` 同步打入）
- `storage/afrog-pocs/` — Afrog POC 规则（**漏洞库**）
- `storage/nuclei/poc-index-lite.json` — 漏洞库预建索引（有则一并同步，开箱可搜）

**可选（按需自行准备）：**

| 路径 | 用途 |
|------|------|
| `storage/Python311/` | 便携 Python（Windows 无系统 Python 时可用） |
| `storage/node_ai/` | Claude Code 运行时（AI 终端功能） |
| `storage/nps/npc` | NPS 客户端（内网穿透） |
| `storage/hfinger/data/finger.json` | 指纹库数据（Web 指纹页；未打入时需手动放置） |
| `storage/nuclei/nuclei` 等二进制 | 实际执行扫描的 CLI 工具（漏洞库仅含模板 YAML） |

---

## 安装与启动

### Windows（推荐）

1. 克隆或解压本目录到任意路径（路径尽量不含特殊字符）
2. 双击 **`start-web.cmd`**
   - 首次运行会自动执行 `install-deps.cmd` 安装 Python 依赖
   - 若系统未装 Python，可将便携版放到 `storage/Python311/python.exe`
3. 控制台会打印 **访问令牌** 与本机地址，例如：
   ```
   http://127.0.0.1:15038/tongling/?token=xxxxxxxx
   ```
4. 用浏览器打开上述地址即可

### Linux / macOS

```bash
cd /path/to/web-standalone

# 安装依赖（首次）
python3 -m pip install -r requirements-web.txt

# 启动（默认 0.0.0.0:15038）
export TONGLING_ROOT="$(pwd)"
python3 tongling_hexstrike_launcher.py
```

可选环境变量：

```bash
export HEXSTRIKE_HOST=0.0.0.0    # 监听地址，默认 0.0.0.0
export HEXSTRIKE_PORT=15038      # API 端口，默认 15038
```

### 完整 HexStrike 扫描依赖（可选）

若需使用 HexStrike 全部扫描工具 API，可额外安装：

```bash
pip install -r storage/hexstrike-ai-community-edition-master/requirements.txt
```

---

## 访问与安全

- **首次启动**会在 `storage/.tongling_web_token` 生成访问令牌，重启后不变
- 请通过 **`/tongling/?token=…`** 访问控制台；根路径 `/` 不对外开放
- **勿将 Token、API Key、NPS vkey** 提交到公开仓库
- 外网或手机访问时，建议配合内网穿透并仅暴露必要端口

局域网 / 手机访问示例：

```
http://<本机IP>:15038/tongling/?token=<你的令牌>
```

---

## 目录结构

```
web-standalone/
├── start-web.cmd              # Windows 一键启动
├── install-deps.cmd           # Windows 依赖安装
├── tongling_hexstrike_launcher.py   # 主启动入口
├── claude_hexstrike_bridge.py       # Claude ↔ HexStrike 桥接
├── requirements-web.txt       # Web 最小依赖
├── tongling_web/              # Web 门户（页面、API、IM 桥接）
├── cc_visual/                 # Claude 终端与会话
└── storage/
    ├── hexstrike-ai-community-edition-master/   # HexStrike CE（已内置）
    ├── nuclei/nuclei-templates/                 # 漏洞库 Nuclei 模板（已内置）
    ├── afrog-pocs/                              # 漏洞库 Afrog POC（已内置）
    ├── im_bridge/             # 社交接入配置（运行时生成）
    └── logs/                  # 运行日志
```

---

## 常用说明

### 漏洞库（Nuclei + Afrog）

独立包**已预置模板与 POC**（由统领根目录 `独立Web.cmd` 从本机 `storage/` 同步）：

```text
storage/nuclei/nuclei-templates/    # Nuclei YAML 模板
storage/afrog-pocs/pocs/            # Afrog POC
storage/nuclei/poc-index-lite.json  # 搜索索引（可选，有则免首次扫描）
```

- **Linux / 离线**：打开 Web「漏洞库」即可使用，**无需 git 拉取**
- **更新**：Web 内点「拉取最新 POC」仍可从 GitHub 增量更新（需本机安装 `git` 且能访问 GitHub）
- **同步前准备**：在统领 Windows 端先在工具箱下载 **nuclei**、**afrog**（或至少拉过一次 POC），再跑 `独立Web.cmd`，否则独立包内无漏洞库

### 指纹库（HFinger）

指纹数据文件路径：

```text
storage/hfinger/data/finger.json
```

独立包**默认不同步**指纹库；需在统领工具箱下载 hfinger 后手动拷贝，或从 [HackAllSec/hfinger](https://github.com/HackAllSec/hfinger) 获取 `data/finger.json` 放到上述路径。

### 扫描报告保存位置

默认写入 Claude 工作目录：

```text
storage/node_ai/claude-code/reports/{目标}_{时间戳}.md
```

部分会话也可能直接写在 `claude-code/` 根目录。可在 Web「扫描报告」页统一查看。

### AI 终端（Claude Code）

1. 准备 `storage/node_ai/`（含 `npx` / Claude Code）
2. 在 Web「设置 → 提供商」配置 `ANTHROPIC_BASE_URL` 与 API Key
3. 打开「AI 渗透终端」即可在浏览器中使用

### 内网穿透（NPS）

1. 在 VPS 部署 NPS，于 Web 管理端创建客户端并复制 **vkey**
2. 本机将 `npc` 放到 `storage/nps/`（或通过统领工具箱下载）
3. Web「设置 → 内网穿透」填写服务端地址与 vkey，点击启动
4. 外网访问：`http://公网IP:端口/tongling/?token=…`

### 钉钉与终端对接

在「社交接入」中配置钉钉 Stream（或 HTTP 回调），绑定 AI 终端后，可通过钉钉发消息驱动扫描任务，回复会镜像回 IM。

---

## 从统领主项目同步更新

若你同时维护统领完整版源码，可在统领根目录双击 **`独立Web.cmd`**，将最新 Web 代码同步到本目录（会覆盖 `tongling_web/`、`cc_visual/` 等，**请勿手改这些目录的源码**）。

---

## 工具界面

运行后打开浏览器访问控制台：

![](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/image-20260713112748385.png)

**电脑端显示：**

![](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/image-20260712200100407.png)

![](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/image-20260712200121041.png)

![](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/image-20260712200225786.png)

![](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/image-20260712200240311.png)

![](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/image-20260712200315783.png)

![](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/image-20260713113230127.png)

**手机端显示：**

![](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/20260706133816_392_8.png)

![](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/20260706134321_396_81.png)

### 钉钉和终端对接

![](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/image-20260713113130681.png)

![](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/image-20260713113029751.png)

---

## 常见问题

**Q：启动报错找不到 `hexstrike_server`？**  
A：确认存在 `storage/hexstrike-ai-community-edition-master/hexstrike_server.py`。

**Q：Web 终端黑屏或无法输入？**  
A：Windows 需 `pywinpty`（`requirements-web.txt` 已包含）；Linux/macOS 使用系统 `pty`。

**Q：提示 Token 无效？**  
A：查看 `storage/.tongling_web_token`，或重启服务后使用控制台新打印的地址。

**Q：扫描工具不可用？**  
A：在 Web 工具箱中按提示下载对应工具到 `storage/`，或安装 HexStrike 完整 `requirements.txt`。

---

## 相关链接

- 统领完整项目：[CuriousLearnerDev/Online_tools](https://github.com/CuriousLearnerDev/Online_tools)
