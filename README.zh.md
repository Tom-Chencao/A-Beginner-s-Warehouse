# Tavily MCP 密钥号池

> English version: [README.md](README.md)

**为什么需要它？** 如果你手里有多把 Tavily API key（多账号、团队预算、批量购买的积分……），并通过 AI 编程助手使用它们，很快会遇到三个问题：

1. **单 key 瓶颈**——一把 key 的速率限制会拖垮整体。
2. **静默失败**——某把 key 过期 / 触发限额 / 被吊销，搜索就……突然不工作了。
3. **看不见用量**——你不知道哪把 key 被用了多少次、花了多少积分。

这个项目一次性解决这三个问题：一个轻量的 MCP 服务器，在你的 key 池里轮询调度、自动停用失效 key、暴露用量统计——你只需把它接入 Claude Desktop、Cursor、DeepSeek Harness 或任何 MCP 客户端，工作流完全不用改。

---

## 亮点

- 🔄 **轮询调度**：在 N 把 Tavily key 之间 round-robin（SQLite 背书，零启动开销）。
- 📊 **用量追踪**：每把 key 的请求数、错误数、积分消耗。
- 🩺 **健康检查**：用轻量搜索探测所有 key，自动停用失效 key；通过 `tavily_pool_status` 工具暴露结果。
- 🛠️ **六个核心 MCP 工具**（Tavily 全功能：search / extract / crawl / map / research），**外加** `tavily_pool_status` 和 `tavily_research_status`（异步取回）。
- 🌐 **独立 FastAPI 面板**（CORS 启用、loopback 监听）：统计、key 明细、增/删/启停、一键健康检查。
- 🔌 **任何 MCP 客户端即插即用**（stdio）；DeepSeek Harness 集成只需一段 patch + 一个 client 插件示例（见 `examples/dsh-integration/`）。

## 与官方 `tavily-mcp` 的区别

| 特性 | 官方 `tavily-mcp` | 本仓库 |
|---|---|---|
| 单 key 环境变量 | ✅ | — |
| 多 key 轮询 | — | ✅ SQLite 号池 |
| 单 key 用量统计 | — | ✅ 请求数 / 积分 / 错误数 |
| 健康检查 + 自动停用 | — | ✅ |
| 独立面板 | — | ✅ FastAPI 监听 127.0.0.1:8000 |
| MCP 工具与官方一致（search/extract/crawl/map/research） | ✅ | ✅（外加 pool-status / research-status） |
| 异步 research 轮询 | （手动） | ✅ 内置 `tavily_research` + `tavily_research_status` |

## 架构

```
+--------------------------------------------------+
|  MCP 客户端 (Claude Desktop / Cursor / DSH …)    |
+--------+---------------------+-------------------+
         | stdio (JSON-RPC)     | HTTPS / CORS
+--------▼--------------+     +▼-----------------------+
|  mcp_server.py (FastMCP)|     |  dashboard.py (FastAPI) |
|  + key_pool.py (SQLite) |     |  uvicorn 127.0.0.1:8000 |
+----------------------+--+     +-----+----------------+
                       |              |
                       v              v
                tavily_keys.db  <— SQLite 背书的号池
                       |
                       v
              Tavily REST API（在 N 把 key 间轮询）
```

## 快速开始

### 1. 安装依赖

```bash
python -m venv .venv
. .venv/bin/activate        # Linux/macOS
# 或（Windows PowerShell）：
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`requirements.txt` 中 `mcp` 的约束是 **`<2.0`**——原因见
[DeepSeek Harness 集成 / 坑 #1](#坑-1mcp-sdk-版本兼容)：FastMCP 的导入路径在 `mcp` 2.x 中已迁移。

### 2. 添加 API key

建一个 `keys.txt`，一行一把 key：

```
tvly-xxxxxxxxxxxxxxxx
tvly-yyyyyyyyyyyyyyyy
```

然后导入：

```bash
python cli.py add --from-file keys.txt
```

或者启动面板（下一步），把 key 粘贴到 **Add API Keys** 表单。Key 以明文存在 `tavily_keys.db`（SQLite）中，让号池能零启动开销地轮询——见 [安全](#安全)。

### 3. 启动 MCP 服务器

对**直接 stdio 的 MCP 服务器**（任何 MCP 客户端可用）：

```bash
./run_mcp.sh                                # Linux/macOS
# 或（Windows）：
.venv\Scripts\python.exe mcp_server.py
```

服务器对外暴露 7 个工具；在 MCP 客户端里工具名是 `tavily_search`、`tavily_extract` 等。

### 4. 启动面板（可选，独立进程）

```bash
./run_dashboard.sh                          # 默认端口 8000
# 或（Windows）：
.venv\Scripts\python.exe -m uvicorn dashboard:app --host 127.0.0.1 --port 8000
```

浏览器打开 <http://127.0.0.1:8000>。面板**对 loopback 来源 CORS 启用**，所以其他内嵌 UI（比如 DSH 设置面板）可以 fetch 调用。

## MCP 工具

| 工具 | 用途 |
|---|---|
| `tavily_search` | 网页搜索（basic/advanced 深度、topic、时间范围、include/exclude 域名、国家等） |
| `tavily_extract` | 从 URL 提取干净内容 |
| `tavily_crawl` | 抓取网站并提取多个页面 |
| `tavily_map` | 发现站点 URL（比 crawl 快） |
| `tavily_research` | AI 深度研究（30–120 秒+；内置后台轮询——见 [坑 #2](#坑-2tavily_research-异步且绑定创建-key)） |
| `tavily_pool_status` | 号池统计：活跃 key、累计请求/错误/积分、最近 24h 分布 |
| `tavily_research_status(request_id)` | 取回异步 research 任务的结果（即使调用已超时） |

## CLI

```bash
python cli.py list                 # 列出所有 key
python cli.py list --active        # 仅活跃 key
python cli.py stats                # JSON dump 号池状态
python cli.py health               # 探测所有活跃 key；自动停用失效 key
python cli.py recent -n 20         # 最近请求日志
python cli.py add tvly-... [...]   # 添加一把或多把 key
python cli.py add --from-file keys.txt
python cli.py activate tvly-xx****yy       # 掩码 id，见 `list`
python cli.py deactivate tvly-xx****yy --reason "manually disabled"
python cli.py remove tvly-xx****yy
```

## 接入 Claude Desktop / Cursor / 其他通用 MCP 客户端

任何接受 MCP stdio 命令的客户端：

```json
{
  "mcpServers": {
    "tavily": {
      "command": "/absolute/path/to/.venv/bin/python3",
      "args": ["mcp_server.py"],
      "cwd": "/absolute/path/to/this/repo"
    }
  }
}
```

如果你的客户端支持 **streamable HTTP**（且你自己用 HTTP 传输包了 server）也可以，但不在本仓库范围。

---

## DeepSeek Harness (DSH) 集成

> 测试环境：`@deepseek-ai/dsh` 0.1.0-rc.6（web profile）。

DeepSeek Harness（`dsh`）用 Cordis 插件框架，自带官方 MCP 客户端桥（`@deepseek-ai/dsh-mcp-client`）。所以集成非常薄：只需要一段用户 patch + 一个浏览器侧插件示例（`examples/dsh-integration/client-tavily-panel/`）。

### A. 在 DSH 注册 Tavily MCP 服务器

编辑 `~/.dsh/profiles/web/cordis.patch.yml`（在所有 bundle 之上应用的用户 patch）。新增一个 `insert` 块——下面的值假设仓库在 `C:\Users\ASUS\.dsh\tavily-pool\`：

```yaml
- insert:
    - id: mcp-tavily
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        transport: stdio
        serverName: tavily
        command: 'C:\Users\ASUS\.dsh\tavily-pool\.venv\Scripts\python.exe'
        args: ['mcp_server.py']
        cwd: 'C:\Users\ASUS\.dsh\tavily-pool'
        # research 在大主题上可能跑超过 2 分钟；默认 30s 太短
        toolCallTimeoutMs: 600000
        failOnStartupError: false
```

重启前用 `dsh --profile web --dump-config` 验证合并。重启后 MCP 服务器会以 `mcp__tavily__tavily_search` 等形式出现在 agent 的工具列表里。

### B. （可选）把面板嵌入 DSH 设置页

把 `examples/dsh-integration/client-tavily-panel/` 拷贝到任意位置。该示例使用 `@deepseek-ai/dsh-client-ui-slots` 的 `settings.section` 槽位——插件注册一个 **Tavily 号池** 面板，通过 fetch 调用面板后端。安装步骤：

1. **放置包**（例如 `~/.dsh/plugins/client-tavily-panel/`）。
2. **链接到 profile 的 `node_modules`**，让 `require.resolve` 能找到（DSH 通过包名解析链加载 client 插件）：

   ```powershell
   New-Item -ItemType Junction `
     -Path "$env:DSH_HOME\profiles\node_modules\dsh-client-tavily-panel" `
     -Target "C:\Users\ASUS\.dsh\plugins\client-tavily-panel"
   ```

   用 Junction 而非 symlink 避免需要管理员权限。直接 `pnpm add` 安装本地包也可以，但要注意：pnpm 可能因为 profile 里的其他无关 `file:` / GitHub 依赖卡住。
3. **在 `cordis.patch.yml` 加 roster 行**：

   ```yaml
   - insert:
       - id: client-tavily-panel
         name: 'dsh-client-tavily-panel'
   ```

4. **重启 `dsh web`**（见坑 #6——web profile 的 HMR 是刻意禁用的，patch 改动只在完整重启时加载）。

重启后，打开 ⚙️ 设置，**Tavily 号池** 就会出现在左侧导航。

### DeepSeek 集成踩过的坑

下面是真实踩坑记录。按顺序读——每条都耗过时间。

#### 坑 #1：`mcp` SDK 版本兼容

`mcp_server.py` 用了 `from mcp.server.fastmcp import FastMCP`。这个模块在 **`mcp` 2.0 已被移除**（FastMCP 实现迁到了独立的 `fastmcp` 包，API 不同）。如果你 `pip install mcp` 装了最新版，服务器启动直接报：

```
ModuleNotFoundError: No module named 'mcp.server.fastmcp'
```

锁版本：

```
# requirements.txt
mcp>=1.0.0,<2.0.0
```

测试用 `mcp 1.29.0`。

#### 坑 #2：`tavily_research` 异步 + **绑定创建 key**

四个子坑在一处：

- `tavily-python` SDK 把 `research()` 的第一个位置参数从 `query` 改名成了 `input`。`client.research(query=…)` 会抛 `missing 1 required positional argument: 'input'`。
- SDK 运行时强制 `model ∈ {"mini", "pro", "auto"}`，但 Tavily REST API 本身接受 `model=standard|pro`。传 `"standard"` 会抛 `model must be one of: mini, pro or auto`。
- `research()` 立刻返回 `status: pending` 的信封——实际结果 30–120+ 秒后才到。**必须** 轮询 `get_research(request_id)` 直到 `status == "completed"`。否则工具永远返回 "pending"，模型会以为调用失败。
- **research 任务与创建它的 key 绑定。** 其他池中 key 拉不到结果（404）。必须用**同一个** `TavilyClient` 实例轮询——**不要** 每次迭代重新 `pool.next_key()`，否则永远命中错的 key。

本仓库的 `tavily_research` 已经把完整生命周期包好：轮询最多 ~570 秒，然后返回带 `request_id` 的 `status: timeout` 信封，调用者可以稍后取回。第二个工具 `tavily_research_status(request_id)` 会遍历活跃 key 列表找到正确 key 来取回——因为首次调用可能在不同进程里超时。

#### 坑 #3：`dashboard.py` 在 Windows 上的 UTF-8 bug

`dashboard.py` 这一行：

```python
DASHBOARD_HTML = TPL.read_text()
```

`Path.read_text()` 默认用 `locale.getpreferredencoding()`——**Windows（zh-CN）上是 GBK**。配套的 `templates/dashboard.html` 是 UTF-8 含中文字符，面板启动直接报：

```
UnicodeDecodeError: 'gbk' codec can't decode byte 0xb6 in position 4308
```

修复：

```python
DASHBOARD_HTML = TPL.read_text(encoding="utf-8")
```

#### 坑 #4：`run_*.sh` 的跨平台路径

`run_mcp.sh` 和 `run_dashboard.sh` 硬编码 `.venv/bin/python3`（Linux 风格），从未在 Windows 上测试过。原作者还配了 systemd unit 用 `/home/user/code/Tavily`——明显 Linux only。

在 Windows 上你**根本不需要这些脚本**——直接调用 `.venv\Scripts\python.exe`（见上面 yaml）。这些脚本只为原 Linux 场景保留。

#### 坑 #5：DSH patch 配置只在启动时加载

`cordis.patch.yml` 在 `web` profile 启动时被读入。改动**不热重载**——web-app bundle patch 里 `hmr` 行刻意禁用：

```yaml
- id: hmr
  disabled: true
# TODO: Re-enable shared HMR for Web after its reload lifecycle is tested.
```

所以改完 `cordis.patch.yml` **必须重启 `dsh web`**（怎么安全重启见坑 #6）。

用 `dsh --profile web --dump-config` 在不启动 GUI 的前提下验证 patch 合并是否正确，比反复启动-检查-杀-改-重启快得多。

#### 坑 #6：怎么重启 `dsh web` 而不自杀

`dsh web` 是**运行你当前会话**的宿主进程。如果你在由它派生出的 pwsh 里天真地跑：

```powershell
Stop-Process -Id <dsh-web-pid> -Force
Start-Process dsh.cmd web
```

**你会在新实例起来之前把自己杀掉。** 第一次尝试时 PowerShell 直接 `exit code 4294967295` 退出，啥也没发生。

解决：把重启任务交给 **Windows 任务计划程序**，让它在 `svchost` 下运行（不在 `dsh web` 下）：

```powershell
$script = "$env:TEMP\dsh_restart.ps1"
@"
Start-Sleep -Seconds 8
Stop-Process -Id <dsh-web-pid> -Force
Get-CimInstance Win32_Process |
  Where-Object { `$_.CommandLine -match 'dsh web' } |
  ForEach-Object { Stop-Process -Id `$_.ProcessId -Force }
Start-Sleep -Seconds 3
Start-Process 'C:\…\dsh.cmd' web -WorkingDirectory 'H:\…' -WindowStyle Hidden
"@ | Out-File $script -Encoding utf8

schtasks /create /tn dsh-restart /tr "powershell -NoProfile -File $script" /sc once /st 23:59 /f
schtasks /run /tn dsh-restart
schtasks /delete /tn dsh-restart /f
```

老实例死前你有 ~8 秒输出最终答案。然后让用户 20–30 秒后刷新 `http://127.0.0.1:3080`。

#### 坑 #7：MCP 服务器在跑时迁移工具目录

DSH 的 `mcp-client` 在连接断开后会按指数退避重连（`initialDelayMs 500`, `maxAttempts 10`）。杀掉 Python 子进程会触发重连——**立刻**再 spawn 一个新子进程。这时你再 `Move-Item` 目录，新 `.venv\Scripts\python.exe` 把文件锁了，robocopy 直接 `[Result: 32]` / "being used by another process"。

两种可行策略：

- **先复制后删源**。`Copy-Item` 通过 Windows 文件共享读被锁文件，不需要独占访问。复制成功后杀旧 MCP 服务器 + 删源。只要 `pyvenv.cfg` 的 `home =` 还指向同一个基础 Python 安装（例 `G:\python`），`.venv` 完全可移动。
- **循环杀 + robocopy /MOVE**，直到在退避窗口内成功。不优雅但管用。

最初迁移用的命令：

```powershell
Copy-Item -Path D:\Downloads\Tavily -Destination C:\Users\ASUS\.dsh\tavily-pool -Recurse -Force
# 校验
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'python.exe' -and $_.CommandLine -match 'mcp_server' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
# 循环删源
for ($i=0; $i -lt 8; $i++) {
  Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'mcp_server' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  Start-Sleep -Milliseconds 200
  Remove-Item D:\Downloads\Tavily -Recurse -Force -ErrorAction SilentlyContinue
  if (-not (Test-Path D:\Downloads\Tavily)) { break }
  Start-Sleep -Seconds 2
}
```

#### 坑 #8：`pnpm add` 可能被无关依赖卡住

跑 `dsh plugin --profile web add <dir>` 安装本地插件时，pnpm 会解析**整个 profile workspace**——包括你 `package.json` 里所有 GitHub 或 HTTP 来源的 bundle。如果 profile 里已经有类似 `dsh-files: https://codeload.github.com/...tar.gz/...` 这种依赖，下载卡住（防火墙/DNS/冷缓存/quota），**你的本地插件就永远装不上**，pnpm 一直挂到超时。

绕过：跳过 pnpm，自己创建解析：

```powershell
New-Item -ItemType Junction `
  -Path "$env:DSH_HOME\profiles\node_modules\dsh-client-tavily-panel" `
  -Target "<你的插件包绝对路径>"
```

Junction（不是 symlink）不需要管理员，对 `require.resolve` 行为完全一致。patch 层引用包名即可，跟 pnpm 装的效果一样。

#### 坑 #9：设置面板 client 插件的打包格式

如果你要自己写 DSH client 插件（浏览器侧），运行时格式**不是** ESM、**不是** 从源码跑 Cordis。`dsh-client-modules` 插件在内存里跑一个小型 module loader，从 `/plugins/<id>/client.js` 拉每个 client bundle。bundle 必须这样写：

```js
window.__ModuleLoader__.load({
  id: "your-package-name",   // 与 package.json 的 "name" 一致
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;
    var react = require("react");           // 可用
    var jsx = require("react/jsx-runtime"); // 可用
    // ... 定义组件 ...
    function apply(ctx) {
      ctx.slots.inject("settings.section", () => ctx.slots.register({
        name: "settings.section",
        id: "your-id",
        order: 100,
        label: "Your Label"
      }, YourComponent));
    }
    exports.apply = apply;
    exports.inject = ["slots"];             // 你依赖的服务
    return module.exports;
  }
});
```

`package.json` 必须包含：

```json
{
  "main": "lib/index.js",
  "exports": { "./client": { "default": "./lib/client.js" } },
  "dsh": { "client": { "inject": ["@deepseek-ai/dsh-client-ui-slots"], "platform": "web" } }
}
```

`lib/index.js` 是**宿主侧**入口——服务端运行——可以是空操作（`function apply() {}; export { apply };`）。

---

## 安全

- **静态明文存储 key。** `tavily_keys.db` 用明文存你的 Tavily key，因为 SQLite 号池每次请求都会查。文件级权限保护（Linux：`chmod 600`）。**永远不要提交 `tavily_keys.db`**（见 `.gitignore`）。
- **面板默认仅 loopback 监听。** `dashboard.py` 绑定 `127.0.0.1:8000`。如要在局域网暴露，立刻加身份认证。
- **CORS 是故意开着的**——面板本来就要被同主机的内嵌 UI 调用。在 loopback bind 下安全；如改了 bind 地址，请收窄 `CORSMiddleware.allow_origins`。
- **轮换泄露的 key**：`python cli.py remove tvly-xxxxxxxx****yyyy`，到 Tavily 后台吊销它，对池中每行都做一遍。

## 故障排除

| 现象 | 原因 / 修复 |
|---|---|
| `ModuleNotFoundError: No module named 'mcp.server.fastmcp'` | `mcp` ≥ 2.0；锁 `<2.0`（坑 #1） |
| `TavilyClient.research() missing 1 required positional argument: 'input'` | 旧调用——`mcp_server.py` 已经用 `input=`（坑 #2） |
| `model must be one of: mini, pro or auto` | SDK 限制，本仓库已映射到 `auto`（坑 #2） |
| research 一直返回 `pending` | 是否在 `research` 后调了 `get_research`？本仓库已自动处理 |
| `UnicodeDecodeError: 'gbk' codec can't decode…` | dashboard HTML 读取 bug（坑 #3）；本仓库已修 |
| `node.exe` 和 `python.exe` 在移动时被锁 | 杀 MCP 服务器，先复制后删源（坑 #7） |
| 工具注册了但 DSH 会话看不到 | 是否重启了 `dsh web`？patch 只在启动时加载（坑 #5） |
| `__DSH_BOOT__` 里没列出你的插件 | junction / require-resolve 问题（坑 #8）；用 `dsh --profile web --dump-config` 校验 |

## 致谢

号池管理代码（`key_pool.py`、`dashboard.py`、FastMCP 的 `mcp_server.py` 骨架、`cli.py`）最初由一位**匿名**作者公开发布。本仓库在此基础上新增：

- `mcp` 1.x 兼容（`query` → `input`、`model` 映射、research 轮询）。
- 新增 `tavily_research_status` 工具支持异步取回。
- Windows 跨平台修复（`dashboard.py` 的 UTF-8 读取）。
- 可直接接入 DSH 的设置面板 client 插件 + 集成坑日志。

如果你认识原作者，请提 issue 我加上致谢。

## 许可

MIT。详见 `LICENSE`。