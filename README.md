# Tavily MCP Key Pool

> 简体中文版 README: [README.zh.md](README.zh.md)

**Why?** If you have multiple Tavily API keys (multiple accounts, a team
budget, batch-purchased credits, …) and use them through an AI coding
agent, you'll hit three problems fast:

1. **Single-key bottlenecks** — one key's rate limit throttles everything.
2. **Silent failures** — a key expires, hits a quota, or gets revoked, and
   your searches just... stop working.
3. **No visibility** — you don't know which keys are being used or how much.

This project solves all three: a tiny MCP server that round-robins across
your key pool, auto-deactivates dead keys, and exposes usage stats — so you
can drop it into Claude Desktop, Cursor, DeepSeek Harness, or any MCP
client without changing your workflow.

A Tavily MCP server with a SQLite-backed **round-robin API key pool**,
built-in usage tracking, automatic health-based failover, and a standalone
FastAPI dashboard. Standard MCP protocol — works with any MCP-compatible
client (Claude Desktop, Cursor, **DeepSeek Harness**, etc.).

## Highlights

- 🔄 **Round-robin key rotation** across N Tavily API keys (SQLite, zero startup cost).
- 📊 **Usage tracking**: per-key request count, error count, credits consumed.
- 🩺 **Automatic health check**: probe all keys with a lightweight search,
 auto-deactivate dead ones; expose results via `tavily_pool_status`.
- 🛠️ **Six core MCP tools** (Tavily parity: search, extract, crawl, map, research) **plus** `tavily_pool_status` and `tavily_research_status` (async fetch).
- 🌐 **Standalone FastAPI dashboard** (CORS-enabled, loopback-only) with stats,
 per-key view, add/remove/deactivate/activate, and one-click health probe.
- 🔌 **Drop-in for any MCP client** via stdio; the DSH integration is a one-page
 patch + an example client plugin (see `examples/dsh-integration/`).

## How it differs from the official `tavily-mcp`

| Feature | Official `tavily-mcp` | This repo |
|---|---|---|
| Single API key env var | ✅ | — |
| Multiple keys, round-robin | — | ✅ SQLite pool |
| Per-key usage stats | — | ✅ request count + credits + errors |
| Health probe + auto-deactivation | — | ✅ |
| Standalone dashboard | — | ✅ FastAPI on 127.0.0.1:8000 |
| MCP tools parity (search/extract/crawl/map/research) | ✅ | ✅ (plus the pool-status / research-status extras) |
| Async research polling | (manual) | ✅ built-in `tavily_research` + `tavily_research_status` |

## Architecture

```
+--------------------------------------------------+
|  MCP clients (Claude Desktop / Cursor / DSH …)   |
+--------+---------------------+-------------------+
         | stdio (JSON-RPC)     | HTTPS / CORS
+--------▼--------------+     +▼-----------------------+
|  mcp_server.py (FastMCP)|     |  dashboard.py (FastAPI) |
|  + key_pool.py (SQLite) |     |  uvicorn 127.0.0.1:8000 |
+----------------------+--+     +-----+----------------+
                       |              |
                       v              v
                tavily_keys.db  <— SQLite-backed pool
                       |
                       v
              Tavily REST API (round-robin over N keys)
```

## Quick Start

### 1. Install dependencies

```bash
python -m venv .venv
. .venv/bin/activate        # Linux/macOS
# or:  .venv\Scripts\Activate.ps1   (Windows PowerShell)
pip install -r requirements.txt
```

The pinned `mcp` constraint in `requirements.txt` is **`<2.0`**: see
[DSH integration / Pitfall #1](#pitfall-1-mcp-sdk-versioning) — the FastMCP
import path moved in `mcp` 2.x.

### 2. Add API keys

Create a `keys.txt` with one key per line:

```
tvly-xxxxxxxxxxxxxxxx
tvly-yyyyyyyyyyyyyyyy
```

Then import them:

```bash
python cli.py add --from-file keys.txt
```

Or start the dashboard (next step) and paste them into the **Add API Keys**
form. Keys are stored plaintext in `tavily_keys.db` (SQLite) so the pool can
round-robin with zero startup cost — see [Security](#security).

### 3. Start the MCP server

For a **direct stdio MCP server** (any MCP client):

```bash
./run_mcp.sh                                # Linux/macOS
# or:  .venv\Scripts\python.exe mcp_server.py   (Windows)
```

The server announces seven tools; the public names in MCP-aware clients
look like `tavily_search`, `tavily_extract`, etc.

### 4. Start the dashboard (optional, independent process)

```bash
./run_dashboard.sh                          # default port 8000
# or:  .venv\Scripts\python.exe -m uvicorn dashboard:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000> in your browser. The dashboard is **CORS-enabled**
for loopback origins so an embedded settings panel in another UI can call it.

## MCP Tools

| Tool | Purpose |
|---|---|
| `tavily_search` | Web search (basic/advanced, topic, time range, include/exclude domains, country, etc.) |
| `tavily_extract` | Extract clean content from URLs |
| `tavily_crawl` | Crawl a website and extract content from multiple pages |
| `tavily_map` | Discover URLs on a site (faster than crawl) |
| `tavily_research` | AI deep research (30–120s+; uses background polling internally — see [Pitfall #2](#pitfall-2-tavily_research-async-and-bind-to-key)) |
| `tavily_pool_status` | Pool stats: active keys, total requests/errors/credits, recent 24h breakdown |
| `tavily_research_status(request_id)` | Fetch the result of an async research task that timed out |

## CLI

```bash
python cli.py list                 # all keys
python cli.py list --active        # only active
python cli.py stats                # JSON dump of pool state
python cli.py health               # probe every active key; deactivate dead ones
python cli.py recent -n 20         # recent request log
python cli.py add tvly-... [...]   # add one or more keys
python cli.py add --from-file keys.txt
python cli.py activate tvly-xx****yy     # masked id, see `list`
python cli.py deactivate tvly-xx****yy --reason "manually disabled"
python cli.py remove tvly-xx****yy
```

## Using with Claude Desktop / Cursor / other generic MCP clients

For any client that accepts an MCP stdio command:

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

Or **streamable HTTP** if your client supports it and you've wrapped the server
in an HTTP transport yourself — out of scope for this repo.

---

## DeepSeek Harness (DSH) Integration

> Tested with `@deepseek-ai/dsh` 0.1.0-rc.6 (web profile).

The DeepSeek Harness (`dsh`) uses the Cordis plugin framework and ships with
an official MCP client bridge (`@deepseek-ai/dsh-mcp-client`). The integration
is therefore very thin: one user-patch layer + an example browser-side
plugin (this repo's `examples/dsh-integration/client-tavily-panel/`).

### A. Register the Tavily MCP server in DSH

Edit `~/.dsh/profiles/web/cordis.patch.yml` (the user-patch layer applied
after every bundle). Add a new `insert` block — the values below assume the
repo lives at `C:\Users\ASUS\.dsh\tavily-pool\`:

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
        # research can take >2 minutes on big topics; the default 30s is too tight
        toolCallTimeoutMs: 600000
        failOnStartupError: false
```

Verify the merge with `dsh --profile web --dump-config` before restarting.
The MCP server appears then as `mcp__tavily__tavily_search` (etc.) in the
agent's tool list.

### B. (Optional) Embed the dashboard in DSH settings

Copy `examples/dsh-integration/client-tavily-panel/` anywhere on disk.
The example uses `@deepseek-ai/dsh-client-ui-slots`' `settings.section`
slot — the plugin registers a **Tavily 号池** panel that calls the dashboard
over fetch. To install:

1. **Place the package** (e.g. `~/.dsh/plugins/client-tavily-panel/`).
2. **Link it into the profile's `node_modules`** so `require.resolve` can find it
   (DSH loads client plugins through its package-name resolution chain):

   ```powershell
   New-Item -ItemType Junction `
     -Path "$env:DSH_HOME\profiles\node_modules\dsh-client-tavily-panel" `
     -Target "C:\Users\ASUS\.dsh\plugins\client-tavily-panel"
   ```

   Junction (not symlink) avoids needing admin rights. If you skip this and
   `pnpm add` the package locally, fine — but watch out: pnpm may stall on
   any other unrelated `file:` / GitHub-source dependencies in your profile.
3. **Add a roster entry** to `cordis.patch.yml`:

   ```yaml
   - insert:
       - id: client-tavily-panel
         name: 'dsh-client-tavily-panel'
   ```

4. **Restart dsh web.** (See Pitfall #6 — HMR is intentionally disabled for the
   web profile; patch changes only load on full restart.)

After restart, open ⚙️ Settings — the **Tavily 号池** entry appears in the
left navigation.

### Pitfalls hit during the DeepSeek integration

These are real errors I (the original integrator) hit. Read these **before**
you start, in the order below — each one wasted time.

#### Pitfall #1: `mcp` SDK versioning

`mcp_server.py` does `from mcp.server.fastmcp import FastMCP`. That module
**was removed in `mcp` 2.0** (the FastMCP implementation moved to a separate
`fastmcp` package with a different API). If you run `pip install mcp` and grab
the latest, the MCP server refuses to start:

```
ModuleNotFoundError: No module named 'mcp.server.fastmcp'
```

Pin it:

```
# requirements.txt
mcp>=1.0.0,<2.0.0
```

Tested with `mcp 1.29.0`.

#### Pitfall #2: `tavily_research` is async and **bound to the creating key**

Three sub-bugs in one:

- The `tavily-python` SDK renamed `research()`'s first positional arg from
  `query` to `input`. Calling `client.research(query=…)` fails with
  `missing 1 required positional argument: 'input'`.
- The SDK enforces `model ∈ {"mini", "pro", "auto"}` at runtime, but the
  Tavily REST API itself accepts `model=standard|pro`. Passing `standard`
  raises `model must be one of: mini, pro or auto`.
- `research()` returns a `status: pending` envelope immediately — the actual
  result arrives 30–120+ seconds later. You **must** poll `get_research(request_id)`
  until `status == "completed"`. Otherwise the tool always returns "pending"
  and your model thinks the call failed.
- **The research task is bound to the API key that created it.** Other keys
  in the pool cannot fetch the result (returns 404). Always poll with the
  **same** `TavilyClient` instance — do **not** re-call `pool.next_key()` on
  each poll iteration, or you'll keep hitting the wrong keys.

This repo's `tavily_research` already wraps the full lifecycle: poll for up to
~570s, then return a `status: timeout` envelope with the `request_id` so the
caller can fetch later. A second tool, `tavily_research_status(request_id)`,
walks the active-key list to find the right key for an ad-hoc fetch — needed
because the tool call may have timed out on a different process.

#### Pitfall #3: `dashboard.py` UTF-8 read bug on Windows

`dashboard.py` does:

```python
DASHBOARD_HTML = TPL.read_text()
```

`Path.read_text()` defaults to `locale.getpreferredencoding()`, which is **GBK
on Windows (zh-CN)**. The bundled `templates/dashboard.html` is UTF-8 and
contains CJK characters, so the dashboard raises:

```
UnicodeDecodeError: 'gbk' codec can't decode byte 0xb6 in position 4308
```

Fix:

```python
DASHBOARD_HTML = TPL.read_text(encoding="utf-8")
```

#### Pitfall #4: Cross-platform paths in `run_*.sh`

`run_mcp.sh` and `run_dashboard.sh` hard-code `.venv/bin/python3` (Linux
conventions) and were never tested on Windows. The script authors also
shipped a `systemd` unit using `/home/user/code/Tavily` — clearly Linux-only.

You do **not** need these scripts at all on Windows; just invoke the
`.venv\Scripts\python.exe` directly (see the YAML above). They're kept in the
repo for the original Linux use case.

#### Pitfall #5: DSH patch config is loaded only at startup

`cordis.patch.yml` is read when the `web` profile boots. Changes do **not**
hot-reload — the `hmr` row in the web-app bundle patch is intentionally
disabled:

```yaml
- id: hmr
  disabled: true
# TODO: Re-enable shared HMR for Web after its reload lifecycle is tested.
```

So after every edit to `cordis.patch.yml`, **restart `dsh web`** (see
Pitfall #6 for how to do this safely).

Use `dsh --profile web --dump-config` to verify your patch merges correctly
without actually booting the GUI. It's much faster than starting, checking the
GUI, killing, fixing, repeating.

#### Pitfall #6: How to restart `dsh web` without killing yourself

`dsh web` is the host process that **runs this conversation**, including
your tool process. If you naively run

```powershell
Stop-Process -Id <dsh-web-pid> -Force
Start-Process dsh.cmd web
```

from a pwsh that the same `dsh web` spawned, **you will kill yourself
mid-command** before the new instance ever starts. The first time I tried, the
PowerShell session aborted with `exit code 4294967295` and nothing happened.

The fix: hand the restart to **Windows Task Scheduler**, which runs the
script under `svchost` (not under `dsh web`):

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

Then you have ~8 seconds to return your final answer before the old instance
dies. Tell the user to refresh `http://127.0.0.1:3080` after 20–30 seconds.

#### Pitfall #7: Migrating the tool directory while the MCP server is running

DSH's `mcp-client` reconnects on connection loss with exponential backoff
(`initialDelayMs 500`, `maxAttempts 10`). Killing the Python child process
triggers a reconnect — which spawns a new child **immediately**. If you then
try to `Move-Item` the directory, the new `.venv\Scripts\python.exe` has the
file locked and robocopy fails with `[Result: 32]` / "being used by another
process".

Two viable strategies:

- **Copy first, then delete source.** `Copy-Item` reads locked files via
  Windows file-sharing; it does not need exclusive access. After the copy
  succeeds, kill the old MCP server + remove the source. `.venv` is fully
  relocatable as long as `pyvenv.cfg`'s `home =` line still points to the
  same base Python install.
- **Loop kill + robocopy /MOVE** until it succeeds within the backoff
  window. Ugly but works.

The original migration used:

```powershell
Copy-Item -Path D:\Downloads\Tavily -Destination C:\Users\ASUS\.dsh\tavily-pool -Recurse -Force
# verify copy
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'python.exe' -and $_.CommandLine -match 'mcp_server' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
# loop until deletion succeeds
for ($i=0; $i -lt 8; $i++) {
  Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'mcp_server' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  Start-Sleep -Milliseconds 200
  Remove-Item D:\Downloads\Tavily -Recurse -Force -ErrorAction SilentlyContinue
  if (-not (Test-Path D:\Downloads\Tavily)) { break }
  Start-Sleep -Seconds 2
}
```

#### Pitfall #8: `pnpm add` may stall on unrelated dependencies

When you run `dsh plugin --profile web add <dir>` to install a local plugin,
pnpm resolves **the whole profile workspace** — including any GitHub-sourced
or HTTP-sourced bundles your `package.json` lists. If your profile already
includes something like `dsh-files: https://codeload.github.com/...tar.gz/...`
and that download stalls (firewall, DNS, cold cache, registry quota),
**your local plugin never installs** and pnpm hangs for the full timeout.

Workaround: skip pnpm and create the resolution yourself:

```powershell
New-Item -ItemType Junction `
  -Path "$env:DSH_HOME\profiles\node_modules\dsh-client-tavily-panel" `
  -Target "<absolute path to your plugin package>"
```

Junctions (not symlinks) work without admin rights and behave identically for
`require.resolve`. The patch layer then references the package by its
`name` field, exactly as if pnpm had installed it.

#### Pitfall #9: Settings-panel client plugin format

If you write your own DSH client plugin (browser side), the runtime format is
**not** ESM, **not** Cordis-from-source. The `dsh-client-modules` plugin
hosts a small in-memory module loader and fetches each client bundle from
`/plugins/<id>/client.js`. The bundle must call:

```js
window.__ModuleLoader__.load({
  id: "your-package-name",   // matches package.json "name"
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;
    var react = require("react");           // available
    var jsx = require("react/jsx-runtime"); // available
    // ... define components ...
    function apply(ctx) {
      ctx.slots.inject("settings.section", () => ctx.slots.register({
        name: "settings.section",
        id: "your-id",
        order: 100,
        label: "Your Label"
      }, YourComponent));
    }
    exports.apply = apply;
    exports.inject = ["slots"];             // services you depend on
    return module.exports;
  }
});
```

And your `package.json` must include:

```json
{
  "main": "lib/index.js",
  "exports": { "./client": { "default": "./lib/client.js" } },
  "dsh": { "client": { "inject": ["@deepseek-ai/dsh-client-ui-slots"], "platform": "web" } }
}
```

`lib/index.js` is the **host** entry — it runs server-side; it can be a
no-op (`function apply() {}; export { apply };`).

---

## Security

- **Plaintext keys at rest.** `tavily_keys.db` stores your Tavily API keys
  in cleartext because the SQLite-backed pool is queried on every request.
  Protect the file with filesystem permissions (Linux: `chmod 600`).
  Never commit `tavily_keys.db` (see `.gitignore`).
- **Loopback-only dashboard by default.** `dashboard.py` binds `127.0.0.1:8000`.
  If you expose it on a LAN, add authentication immediately.
- **CORS is wide-open on purpose** — the dashboard is meant to be called by
  embedded UIs on the same host. This is safe because of the loopback bind,
  but if you change the bind address, narrow `CORSMiddleware.allow_origins`
  to match.
- **Rotating a leaked key**: `python cli.py remove tvly-xxxxxxxx****yyyy`,
  revoke it in the Tavily dashboard, repeat for each row in the pool.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `ModuleNotFoundError: No module named 'mcp.server.fastmcp'` | `mcp` is ≥ 2.0; pin to `<2.0` (Pitfall #1) |
| `TavilyClient.research() missing 1 required positional argument: 'input'` | Old-style call — `mcp_server.py` already uses `input=` (Pitfall #2) |
| `model must be one of: mini, pro or auto` | SDK-level restriction, mapped to `auto` in this repo (Pitfall #2) |
| Research always returns `pending` | Did you call `get_research` after `research`? This repo does it for you |
| `UnicodeDecodeError: 'gbk' codec can't decode…` | Dashboard HTML read bug (Pitfall #3); fixed in this repo |
| `node.exe` and `python.exe` files locked during move | Kill MCP server, copy first, delete after (Pitfall #7) |
| Tools registered but DSH session doesn't see them | Did you restart `dsh web`? Patches only load on startup (Pitfall #5) |
| `__DSH_BOOT__` doesn't list your plugin | Junction/require-resolve issue (Pitfall #8); verify with `dsh --profile web --dump-config` |

## Credits

The pool management code (`key_pool.py`, `dashboard.py`, the FastMCP
`mcp_server.py` skeleton, `cli.py`) was originally written by an
**unattributed** author and shared publicly. This repository adds:

- `mcp` 1.x compatibility (`query`→`input`, `model` mapping, research polling).
- A new `tavily_research_status` tool for async fetch.
- Windows cross-platform fixes (UTF-8 read in `dashboard.py`).
- A drop-in settings-panel client plugin for DSH, and the integration
  pitfall log above.

If you know the original author, please open an issue so I can add a credit.

## License

MIT. See `LICENSE`.