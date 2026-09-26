# Memory Hub：ChatGPT / Claude / 其他 AI 共用的 Obsidian 记忆库

把你的 **Obsidian 仓库** 变成所有 AI 共用的长期记忆：

- **每条 AI 记忆都是一篇 Markdown 笔记**，放在 `AI Memory/` 文件夹，带 Obsidian 属性（Properties）和 `[[实体]]` 双链，可以在图谱、反向链接、Dataview 里直接看到。
- **AI 也能搜到你自己写的笔记**：整个仓库都会建立全文索引（中文、英文都支持）。
- **在 Obsidian 里改或删笔记，AI 马上就能看到**：服务每 3 秒重新扫描一次仓库。
- **一套服务同时接入多种客户端**：
  - MCP：Claude Desktop、Claude Code、claude.ai、Cursor、ChatGPT 连接器
  - REST / OpenAPI：ChatGPT 自定义 GPT 的 Actions、脚本、n8n 等
- **零依赖**：只需要 Node.js ≥ 22.13（内置 `node:sqlite`），不用 `npm install`。
- **网页观察台**：打开 `http://localhost:8787/` 可以实时看到哪个 AI 写了什么，也能在这里搜索、添加、删除，或一键跳到 Obsidian。

```
 ChatGPT ──(Actions / MCP)──┐
 Claude  ──(MCP)────────────┤                      ┌── AI Memory/Observations/<实体>/*.md
 Cursor  ──(MCP)────────────┼──► Memory Hub ──────►│   AI Memory/Entities/<实体>.md
 脚本    ──(REST)───────────┘   (Node, :8787)       └── 你自己的笔记（只读检索，或按要求写入）
                                     ▲
                                  Obsidian（同一个文件夹，双向同步）
```

## 0. Windows 一键安装（推荐）

1. 安装 [Node.js](https://nodejs.org) LTS（≥ 22.13；没装的话安装向导也可以用 winget 帮你装）。
2. 把 `memory-hub` 文件夹放到一个固定位置，例如 `D:\memory-hub`。
3. 双击 **`windows\setup.bat`**，按提示操作：
   - 选择 Obsidian 仓库文件夹（可以直接粘贴路径，也可以在弹出的窗口里选）；
   - 是否开放给**同一 Wi-Fi / 局域网**里的设备：选"是"会自动生成访问密钥，并添加防火墙规则（弹出一次管理员确认，只对"专用/域网络"生效）；
   - 是否**开机自启**：选"是"后登录 Windows 时会自动在后台运行，崩溃后也会自动重启；
   - 是否写入**本机 Claude Desktop** 配置：会先备份原文件，已有的其他 MCP 配置都会保留。
4. 安装完成后会显示所有连接方式（本机、局域网地址、密钥、其他电脑的 Claude Desktop / Claude Code 配置），同时保存到 `windows\connect-info.txt`，方便复制。

| 脚本 | 作用 |
|---|---|
| `setup.bat` | 安装 / 修改配置（可以重复运行） |
| `start.bat` | 在前台运行，窗口里能看到日志（排查问题时用） |
| `stop.bat` | 停止后台服务 |
| `status.bat` | 查看运行状态、局域网地址和连接配置 |
| `uninstall.bat` | 停止服务、取消开机自启、删除防火墙规则（不会动你的仓库和记忆） |

局域网使用须知：
- 其他电脑、手机、平板只要和主机连在同一个 Wi-Fi，就能用浏览器打开观察台，或者让它们的 Claude Desktop / Claude Code 连到主机。
- **ChatGPT 和 claude.ai 网页版、手机 App 用不了局域网地址**：它们的请求是从云端发出的，访问不到你家里的内网。要接这些客户端，请看第 2 节。
- 局域网内走的是 HTTP，只在自己家里、公司这类可信 Wi-Fi 上使用。建议在路由器里给主机设置固定 IP（DHCP 保留），不然 IP 变了其他设备会连不上。
- 日志在 `windows\logs\` 里；配置文件是 `windows\config.json`，里面有密钥，不要分享。

## 1. 启动（命令行 / macOS / Linux）

```bash
cd memory-hub
OBSIDIAN_VAULT="$HOME/Documents/Obsidian/我的仓库" npm start
# Windows PowerShell:
#   $env:OBSIDIAN_VAULT="D:\Obsidian\我的仓库"; npm start
```

启动后打开 <http://localhost:8787/> 即可看到观察台。

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `OBSIDIAN_VAULT` | `./vault` | Obsidian 仓库路径 |
| `OBSIDIAN_VAULT_NAME` | 文件夹名 | 用于生成 `obsidian://` 打开链接，需要与 Obsidian 里显示的仓库名一致 |
| `MEMORY_FOLDER` | `AI Memory` | AI 记忆存放的文件夹 |
| `MEMORY_API_KEY` | 空 | 访问密钥。一旦对外暴露就**必须**设置（可以用 `openssl rand -hex 24` 生成） |
| `HOST` / `PORT` | `127.0.0.1` / `8787` | 监听地址。没设置 `MEMORY_API_KEY` 时，程序拒绝监听公网地址 |
| `PUBLIC_URL` | `http://localhost:PORT` | 对外的 HTTPS 地址，会写进 `openapi.json` |

### 仓库里的样子

```
我的仓库/
├── AI Memory/
│   ├── Entities/
│   │   ├── user.md                 ← 实体页，反向链接列出所有相关记忆
│   │   └── project-rpwms.md
│   └── Observations/
│       └── project-rpwms/
│           └── 2026-09-25 RPWMS 生产环境部署使用 pm2 restart wms.md
└── Projects/RPWMS.md               ← 你自己的笔记，AI 也能检索
```

```markdown
---
entity: "project:rpwms"
about: "[[AI Memory/Entities/project-rpwms|project:rpwms]]"
type: "fact"
tags: ["部署"]
importance: 3
source: "claude"
created: "2026-09-25T04:09:52.580Z"
updated: "2026-09-25T04:09:52.580Z"
---
RPWMS 生产环境部署使用 pm2 restart wms
```

- 删除的记忆会被移到仓库的 `.trash/` 文件夹，随时可以找回。
- 如果装了 Dataview 插件，可以用下面的查询在任意笔记里列出高重要度的记忆：

````markdown
```dataview
TABLE entity, type, importance, source FROM "AI Memory/Observations"
WHERE importance >= 4 SORT updated DESC
```
````

## 2. 对外暴露（ChatGPT、claude.ai 网页版和手机端需要）

ChatGPT 和 claude.ai 都在云端运行，只能访问公网 HTTPS 地址。最简单的做法是用 Cloudflare Tunnel：

```bash
export MEMORY_API_KEY=$(openssl rand -hex 24)
cloudflared tunnel --url http://localhost:8787          # 会输出一个 https://xxxx.trycloudflare.com 地址
PUBLIC_URL=https://xxxx.trycloudflare.com OBSIDIAN_VAULT=... MEMORY_API_KEY=$MEMORY_API_KEY npm start
```

要长期使用，建议换成固定域名的 named tunnel、Tailscale Funnel，或者把服务部署到 VPS 上（仓库通过 Obsidian Sync、Syncthing 或 git 同步过去）。部署到服务器可以用 Docker：

```bash
docker build -t memory-hub .
docker run -d -p 8787:8787 -v /srv/obsidian/我的仓库:/vault \
  -e MEMORY_API_KEY=xxx -e PUBLIC_URL=https://mem.example.com -e OBSIDIAN_VAULT_NAME=我的仓库 memory-hub
```

密钥可以用三种方式传：`Authorization: Bearer <key>`、`X-API-Key: <key>`、URL 参数 `?key=<key>`（给只能填一个 URL 的客户端用）。

## 3. 接入各个 AI

### Claude Code

```bash
# 本机直连仓库（stdio）
claude mcp add memory-hub -s user -e OBSIDIAN_VAULT="$HOME/Documents/Obsidian/我的仓库" -- node /绝对路径/memory-hub/bin/mcp-stdio.js
# 或者连远程服务
claude mcp add --transport http memory-hub https://mem.example.com/mcp -s user --header "Authorization: Bearer <key>"
```

### Claude Desktop（`claude_desktop_config.json`）

```json
{
  "mcpServers": {
    "memory-hub": {
      "command": "node",
      "args": ["/绝对路径/memory-hub/bin/mcp-stdio.js"],
      "env": { "OBSIDIAN_VAULT": "/Users/you/Documents/Obsidian/我的仓库" }
    }
  }
}
```

如果另一台电脑上没有这个仓库，把 `env` 改成 `{ "MEMORY_URL": "https://mem.example.com", "MEMORY_API_KEY": "<key>" }`。这样 stdio 进程只负责把请求转发到远程服务，所有设备共用同一份记忆。

### claude.ai 网页版 / 手机端

进入「设置 → Connectors → Add custom connector」，URL 填 `https://mem.example.com/mcp?key=<key>`。

### ChatGPT：方式 A，自定义 GPT（Actions）

1. 创建一个 GPT，进入 Configure → Actions → Import from URL，填 `https://mem.example.com/openapi.json`。
2. Authentication 选 API Key，Auth Type 选 Bearer，填入 `MEMORY_API_KEY`。
3. Privacy policy 填 `https://mem.example.com/privacy`。
4. Instructions 里加上下面这段：

   > 对话开始时先调用 getContext（query 填当前话题）。得知关于我、我的项目、偏好或决定这类长期有效的信息时，调用 remember（source 填 "chatgpt"，每条只写一个独立的事实）。写入前先用 recall 查一下，避免重复；信息过时就用 updateMemory 更新，写错了就用 forget 删除。不要保存密码、密钥等敏感信息。

### ChatGPT：方式 B，连接器（MCP，需要开启开发者模式）

进入「Settings → Apps & Connectors → Advanced → Developer mode」，然后新建连接器：MCP URL 填 `https://mem.example.com/mcp?key=<key>`，认证选 No authentication。服务同时提供 ChatGPT 要求的 `search` 和 `fetch` 两个工具。

### Cursor / Windsurf / Cline 等其他 MCP 客户端

配置格式和 Claude Desktop 一样（例如 Cursor 的 `~/.cursor/mcp.json`），也可以直接填远程 URL：`https://mem.example.com/mcp`，并加上 `Authorization` 请求头。

### 其他工具、脚本（REST）

```bash
curl -H "Authorization: Bearer $KEY" "https://mem.example.com/api/context?query=RPWMS"
curl -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
     -d '{"content":"客户 A 要求每周一发库存报表","entity":"customer:A","type":"task","source":"n8n"}' \
     https://mem.example.com/api/memories
```

不支持调用工具的模型（比如某些 API 或本地模型），可以先把 `/api/context?query=...` 返回的 Markdown 拼进 system prompt。

## 4. 工具 / 接口一览

| MCP 工具 | REST | 作用 |
|---|---|---|
| `get_context` | `GET /api/context?query=&entity=&limit=` | 返回重要记忆和相关笔记的 Markdown 简报 |
| `recall` | `GET /api/search?query=&scope=all\|memory\|notes&entity=&type=&tag=&source=&limit=` | 搜索记忆和笔记 |
| `remember` | `POST /api/memories` | 写入一条记忆（内容相同的会合并，不重复写） |
| `update_memory` | `PATCH /api/memories?id=<路径>` | 修改记忆，会保留你在 Obsidian 里自己加的属性 |
| `forget` | `DELETE /api/memories?id=<路径>` | 把记忆移到 `.trash/` |
| `read_note` / `fetch` | `GET /api/notes?path=<路径>` | 读取任意笔记的全文、属性和链接 |
| `write_note` | `POST /api/notes` `{path, content, mode}` | 新建、追加或覆盖普通笔记 |
| `list_entities` | `GET /api/entities` | 列出所有实体 |
| `search` | – | ChatGPT 连接器使用的搜索接口 |
| – | `GET /api/stats`、`GET /api/events`（SSE） | 统计信息 / 实时事件流 |

另外还有 `GET /openapi.json`、`GET /health`、`POST /mcp`（MCP Streamable HTTP）这几个入口。

## 5. 安全说明

- AI **只能写入 `AI Memory/`**（通过 `remember`），以及你明确要求它写的笔记（通过 `write_note`，默认不会覆盖已有文件）。修改和删除操作只对 AI 记忆笔记有效，不会动你自己的笔记。
- 路径做了校验：不能跳出仓库目录，也不能访问 `.obsidian`、`.git`、`.trash` 等隐藏文件夹。
- 对外暴露时务必设置 `MEMORY_API_KEY`，并且只走 HTTPS。`?key=` 这种写法会让密钥出现在访问日志里，只在客户端不支持自定义请求头时使用。

## 开发

```bash
npm test        # node --test，覆盖 frontmatter、仓库同步、MCP、HTTP、stdio
```
