统领 Web 独立版

本项目是从 [https://github.com/CuriousLearnerDev/Online_tools](https://github.com/CuriousLearnerDev/Online_tools)（如需桌面版，可使用这个提供的 Windows 一键安装版本。） 独立拆分出的 **AI 渗透 Web 控制台**，可脱离统领桌面端单独运行，支持独立部署。



在 Windows 原版基础上做了跨平台适配，目前可在 **Windows / Linux / macOS** 上正常使用

## ✨ 核心特性

| 功能          | 说明                                                |
| ------------- | --------------------------------------------------- |
| 🤖 AI 渗透终端 | 浏览器内运行 Claude Code，支持 HexStrike MCP 工具链 |
| 📊 扫描图谱    | 可视化展示 AI 调用链、扫描流程及工具关系            |
| 📝 扫描报告    | 自动归档 Markdown 报告，支持目录预览                |
| 📋 任务监控    | 实时查看后台扫描、审计任务及运行状态                |
| 💬 社交联动    | 支持钉钉、Telegram、QQ（OneBot）双向交互            |
| 🌍 内网穿透    | 集成 NPS npc，可远程访问 Web 控制台                 |
| 🎯 漏洞库管理  | Nuclei、Afrog、HFinger 指纹库统一管理               |

## 🚀 为什么使用统领 Web？

相比传统命令行工具，它提供：

- 浏览器即可操作，无需安装桌面 GUI
- AI 自动调用扫描工具
- 扫描过程可视化
- 自动生成渗透报告
- 手机、平板、PC 多端访问
- 支持团队远程协作

## ⚙️ 环境要求

| 项目    | 要求                    |
| ------- | ----------------------- |
| Python  | 3.10+（推荐 3.11）      |
| Node.js | Claude Code 运行环境    |
| 系统    | Windows / Linux / macOS |
| 浏览器  | Chrome / Edge / Firefox |

## 📦 内置组件

开箱即用，无需额外下载：

- ✅ HexStrike Community Edition
- ✅ Nuclei Templates
- ✅ Afrog POC
- ✅ POC 搜索索引

可按需扩展：

- Claude Code
- NPS
- HFinger
- Nuclei CLI
- Python Portable（Windows）

## 🚀 快速开始（推荐 Docker）

### 方式一：Docker（推荐）

```bash
 # 1. 拉取镜像
 docker pull curiouslearnerdev/online_tools_ai:latest
 
 # 2. 启动容器
 docker run -d --name online_tools_ai -p 15038:15038 curiouslearnerdev/online_tools_ai:latest
 
 # 3. 查看访问地址和 Token
 docker logs online_tools_ai
```

**指定自定义 Token：**

```bash
 docker run -d --name online_tools_ai -p 15038:15038 \
   -e TONGLING_WEB_TOKEN="你的自定义Token" \
   curiouslearnerdev/online_tools_ai:latest
```

**挂载数据到宿主机（保留日志和审计记录）：**

```bash
 docker run -d --name online_tools_ai -p 15038:15038 \
   -e TONGLING_WEB_TOKEN="你的Token" \
   -v $(pwd)/logs:/app/logs \
   -v $(pwd)/storage_data:/app/storage \
   curiouslearnerdev/online_tools_ai:latest
```

### 💻 方式二：源码直接运行

> 适用于 Windows / Linux / macOS

**1. 安装 Python 依赖：**

```
 pip install -r requirements-web.txt
```

**2. 安装 Node.js 与 Claude Code：**

```
 npm install -g @anthropic-ai/claude-code
```

**3. 解压 Skill 技能文档：**

```
 unzip Skill.zip -d storage/ && rm Skill.zip
```

**4. 启动服务：**

```
 python tongling_hexstrike_launcher.py --host 0.0.0.0 --port 15038
```

**5. 浏览器访问**

启动后终端会打印访问地址：

```
 ============================================================
 [统领 Web] 访问令牌: gCIoaw0RQIbU9SGmfN3EJZLL2Kzy2D-BOk8yX40dzGc
 [统领 Web] 本机控制台: http://127.0.0.1:15038/tongling/?token=...
 ============================================================
```

### 方式三：docker-compose

```
 # docker-compose.yml
 version: "3.8"
 services:
   online_tools_ai:
     image: curiouslearnerdev/online_tools_ai:latest
     container_name: online_tools_ai
     ports:
       - "15038:15038"
     environment:
       - TONGLING_WEB_TOKEN=你的自定义Token
     volumes:
       - ./logs:/app/logs
       - ./storage_data:/app/storage
     restart: unless-stopped
 docker-compose up -d
```


## 📚工具界面

### **电脑端显示：**

![](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/image-20260717180527883.png)

![img](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/image-20260715140930749.png)

![img](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/image-20260715140908177.png)

![img](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/image-20260715140844479.png)

![img](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/image-20260715141024448.png)

![img](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/image-20260712200100407.png)

![img](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/image-20260712200121041.png)

![img](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/image-20260712200225786.png)

![img](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/image-20260712200240311.png)

![img](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/image-20260712200315783.png)

![img](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/image-20260713113230127.png)

### **手机端显示：**

![img](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/20260706133816_392_8.png)

![img](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/20260706134321_396_81.png)

### 钉钉和终端对接

![img](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/image-20260713113130681.png)

![img](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/image-20260713113029751.png)


##  安全说明

首次启动将自动生成访问 Token：

```
storage/.tongling_web_token
```

访问地址：

```
http://IP:15038/tongling/?token=xxxx
```

> ⚠️ 请勿将 Token、API Key、NPS vkey 提交至公开仓库。

## 📂 目录结构

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

## 🔗 相关上游项目

- 统领完整项目：[CuriousLearnerDev/Online_tools](https://github.com/CuriousLearnerDev/Online_tools)
- Docker 镜像：[curiouslearnerdev/online_tools_ai](https://hub.docker.com/r/curiouslearnerdev/online_tools_ai)

## 🔗 技术参考

| 说明                     | 地址                                                         |
| :----------------------- | :----------------------------------------------------------- |
| HexStrike AI 社区版      | https://github.com/CommonHuman-Lab/hexstrike-ai-community-edition |
| cc-switch 提供商配置说明 | https://github.com/farion1231/cc-switch/blob/main/docs/user-manual/providers.md |

#### Claude Code / Anthropic 官方

| 说明               | 地址                                             |
| :----------------- | :----------------------------------------------- |
| Claude Code 概述   | https://code.claude.com/docs/zh-CN/overview      |
| Claude Code CLI    | https://code.claude.com/docs/zh-CN/cli-reference |
| Anthropic 官方文档 | https://docs.anthropic.com/                      |
| 官方 API 端点      | https://api.anthropic.com                        |

#### 终端与技术实现

| 说明                                            | 地址                                             |
| :---------------------------------------------- | :----------------------------------------------- |
| xterm.js（Web 终端）                            | https://xtermjs.org/                             |
| xterm.js（npm / CDN）                           | https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/ |
| pyte 不支持备用屏幕缓冲（为何不用简易 VT 仿真） | https://github.com/selectel/pyte/issues/90       |




## ⚠️ 免责声明（Disclaimer）

本项目仅供**网络安全研究、教育学习、授权安全测试及合法合规的技术交流**使用。

使用本项目时，您应确保已获得目标系统或资产所有者的明确授权，并严格遵守所在国家或地区的法律法规。**严禁将本项目用于任何未经授权的渗透测试、攻击、破坏、数据窃取、非法控制、商业牟利或其他违法活动。**

本项目集成或调用了部分第三方开源组件、工具及规则库（包括但不限于 Claude Code、HexStrike、Nuclei、Afrog、HFinger 等），其版权及许可证归各自项目作者所有，使用时请遵循相应开源许可证及使用条款。

本项目按 **"AS IS"（按现状）** 提供，不提供任何形式的明示或默示担保，包括但不限于适销性、特定用途适用性及非侵权保证。作者及贡献者不对因使用或无法使用本项目而导致的任何直接、间接、附带、特殊、惩罚性或后果性损失承担任何责任，包括但不限于数据丢失、业务中断、系统损坏、法律纠纷或经济损失。

使用本项目即表示您已充分理解并同意承担因使用本项目产生的全部风险和责任。如您不同意本免责声明，请立即停止下载、安装或使用本项目。
