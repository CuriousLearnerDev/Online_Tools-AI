English | [中文](./README.zh-CN.md)

## TongLing Web Standalone

> **AI-Powered Web Penetration Testing Console** for **Windows / Linux / macOS**

TongLing Web Standalone is an independent extraction of the **TongLing Toolkit (Online_tools)**, allowing the AI-powered penetration testing console to run without the desktop application.

Originally developed for Windows, it has now been fully adapted for **Windows, Linux, and macOS**, providing a consistent cross-platform experience.

------

## ✨ Key Features

| Feature                                 | Description                                                  |
| --------------------------------------- | ------------------------------------------------------------ |
| 🤖 AI Penetration Terminal               | Browser-based terminal powered by Claude Code with HexStrike MCP integration |
| 📊 Scan Visualization                    | Interactive graph showing AI workflow, scan processes, and tool relationships |
| 📝 Scan Reports                          | Automatically archives Markdown penetration testing reports with outline preview |
| 📋 Task Monitoring                       | Monitor background scans, audit tasks, and execution status in real time |
| 💬 Social Integrations                   | Two-way integration with DingTalk, Telegram, and QQ (OneBot) |
| 🌍 Remote Access                         | Built-in NPS `npc` support for remote and mobile access      |
| 🎯 Vulnerability & Fingerprint Libraries | Unified management for Nuclei, Afrog, and HFinger databases  |

------

## 🚀 Why TongLing Web?

Compared with traditional command-line workflows, TongLing Web provides:

- Browser-based operation with no desktop GUI required
- AI-assisted penetration testing workflow
- Visualized scanning process
- Automatic Markdown report generation
- Cross-platform support for PC, tablet, and mobile devices
- Remote collaboration capabilities

------

## ⚙️ Requirements

| Component        | Requirement                                  |
| ---------------- | -------------------------------------------- |
| Python           | 3.10+ (3.11 recommended)                     |
| Node.js          | Required for Claude Code                     |
| Operating System | Windows / Linux / macOS                      |
| Browser          | Chrome, Edge, Firefox, or any modern browser |

------

## 📦 Built-in Components

Included out of the box:

- ✅ HexStrike Community Edition
- ✅ Nuclei Templates
- ✅ Afrog POC Library
- ✅ Prebuilt POC Search Index

Optional components:

- Claude Code
- NPS
- HFinger
- Nuclei CLI
- Portable Python (Windows)

------

# 🚀 Quick Start

## Method 1: Docker (Recommended)

```bash
# Pull the image
docker pull curiouslearnerdev/online_tools_ai:latest

# Start the container
docker run -d \
  --name online_tools_ai \
  -p 15038:15038 \
  curiouslearnerdev/online_tools_ai:latest

# View the access URL and Token
docker logs online_tools_ai
```

### Specify a Custom Token

```bash
docker run -d \
  --name online_tools_ai \
  -p 15038:15038 \
  -e TONGLING_WEB_TOKEN="your-token" \
  curiouslearnerdev/online_tools_ai:latest
```

### Persist Logs and Data

```bash
docker run -d \
  --name online_tools_ai \
  -p 15038:15038 \
  -e TONGLING_WEB_TOKEN="your-token" \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/storage_data:/app/storage \
  curiouslearnerdev/online_tools_ai:latest
```

------

## Method 2: Run from Source

> Supported on Windows, Linux, and macOS.

### 1. Install Python Dependencies

```bash
pip install -r requirements-web.txt
```

### 2. Install Node.js and Claude Code

```bash
npm install -g @anthropic-ai/claude-code
```

### 3. Extract Skill Files

```bash
unzip Skill.zip -d storage/ && rm Skill.zip
```

### 4. Start the Service

```bash
python tongling_hexstrike_launcher.py \
    --host 0.0.0.0 \
    --port 15038
```

### 5. Access from Your Browser

After startup, the terminal will display something similar to:

```text
============================================================
[TongLing Web] Access Token: xxxxxxxxxxxxxxxxxxxxxxxxx
[TongLing Web] Local Console:
http://127.0.0.1:15038/tongling/?token=...
============================================================
```

------

## Method 3: Docker Compose

```yaml
version: "3.8"

services:
  online_tools_ai:
    image: curiouslearnerdev/online_tools_ai:latest
    container_name: online_tools_ai

    ports:
      - "15038:15038"

    environment:
      - TONGLING_WEB_TOKEN=your-token

    volumes:
      - ./logs:/app/logs
      - ./storage_data:/app/storage

    restart: unless-stopped
docker-compose up -d
```

------

# 🔒 Security

On first launch, an access token will be automatically generated:

```text
storage/.tongling_web_token
```

Access the console via:

```text
http://<IP>:15038/tongling/?token=<your-token>
```

> **Important:** Never commit your Token, API Keys, or NPS vkey to a public repository.

------

# 📂 Project Structure

```text
web-standalone/
├── start-web.cmd
├── install-deps.cmd
├── tongling_hexstrike_launcher.py
├── claude_hexstrike_bridge.py
├── requirements-web.txt
├── tongling_web/
├── cc_visual/
└── storage/
    ├── hexstrike-ai-community-edition-master/
    ├── nuclei/nuclei-templates/
    ├── afrog-pocs/
    ├── im_bridge/
    └── logs/
```

------

# 📚 Screenshots

## Desktop

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


## Mobile

![img](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/20260706133816_392_8.png)

![img](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/20260706134321_396_81.png)

## DingTalk Integration

![img](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/image-20260713113130681.png)

![img](https://zssnp-1301606049.cos.ap-nanjing.myqcloud.com/img/image-20260713113029751.png)

------

# 🔗 Upstream Projects

- **TongLing Toolkit (Online_tools)**
  https://github.com/CuriousLearnerDev/Online_tools
- **Docker Image**
  https://hub.docker.com/r/curiouslearnerdev/online_tools_ai

------

# 🔗 References

## HexStrike & Provider Configuration

| Description                      | URL                                                          |
| -------------------------------- | ------------------------------------------------------------ |
| HexStrike AI Community Edition   | https://github.com/CommonHuman-Lab/hexstrike-ai-community-edition |
| cc-switch Provider Configuration | https://github.com/farion1231/cc-switch/blob/main/docs/user-manual/providers.md |

## Claude Code & Anthropic

| Description               | URL                                                       |
| ------------------------- | --------------------------------------------------------- |
| Claude Code Overview      | https://code.claude.com/docs/en/overview                  |
| Claude Code CLI Reference | https://code.claude.com/docs/en/cli-reference             |
| Anthropic Documentation   | [https://docs.anthropic.com](https://docs.anthropic.com/) |
| Anthropic API Endpoint    | [https://api.anthropic.com](https://api.anthropic.com/)   |

## Terminal & Technical References

| Description                        | URL                                              |
| ---------------------------------- | ------------------------------------------------ |
| xterm.js                           | [https://xtermjs.org](https://xtermjs.org/)      |
| xterm.js (CDN)                     | https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/ |
| pyte Alternate Screen Buffer Issue | https://github.com/selectel/pyte/issues/90       |

## ⚠️ Disclaimer

This project is intended **only for authorized security research, education, and penetration testing**.

By downloading or using this project, you agree to comply with all applicable laws and regulations. The authors and contributors shall not be liable for any misuse of this project or any damages arising from its use.

For more information, please see [README.zh-CN.md](README.zh-CN.md).
