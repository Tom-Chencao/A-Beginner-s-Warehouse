# DSH Desktop

**DeepSeek Harness 桌面客户端** —— 把 `dsh web` 的浏览器界面装进一个独立的桌面应用窗口，双击图标即可使用，不需要打开任何命令行。

## 它是怎么工作的

DSH 本身是一个本地 Web 服务（`dsh web`，默认端口 `3080`）。DSH Desktop 是一个原生外壳（Electron），负责：

1. **找服务**：扫描端口（默认从 `3080` 开始），如果该端口上已经有一个 DSH 服务（比如你从命令行跑过 `dsh web`），就直接复用；否则用**应用自带的 node.exe** 在后台拉起一个。
2. **开窗口**：服务就绪后，在一个无地址栏的原生窗口里加载 DSH Web UI。
3. **收尾**：退出应用时，只关闭应用自己拉起的服务进程；复用的服务不受影响。

桌面外壳额外提供：单实例锁（重复双击只会聚焦已有窗口）、托盘图标、窗口大小/位置记忆、断线自动重连。

## 运行

```bat
:: 开发模式（需要先 npm install）
npm start

:: 冒烟测试：就绪后打印 DSH_DESKTOP_SMOKE_OK ... 并退出
npm run smoke

:: 打包：生成安装包 + 便携版（输出到 dist\）
npm run dist
```

## 打包产物

| 文件 | 说明 |
|---|---|
| `DSH-Desktop-Setup-0.1.0.exe` | NSIS 安装包，可选安装目录，自动创建桌面/开始菜单快捷方式 |
| `DSH-Desktop-Portable-0.1.0.exe` | 便携版，单文件、免安装，双击即用 |

> 未做代码签名：Windows SmartScreen 首次运行可能提示“未知发布者”，点“仍要运行”即可。

## 首次运行（新机器上）

- 应用自带 node.exe 运行时和 `@deepseek-ai/dsh` 启动器，**不要求机器上有 Node.js**。
- DSH 的 web profile 首次使用时会自动初始化：需要机器上装有 **pnpm** 且能联网（安装 profile 依赖）。初始化完成后即可离线使用。
- 用户配置（模型凭证、设置、会话历史）沿用 DSH 自己的目录 `%USERPROFILE%\.dsh`，与命令行版完全共享。

## 环境变量（可选覆盖）

| 变量 | 默认值 | 作用 |
|---|---|---|
| `DSH_HOME` | `%USERPROFILE%\.dsh` | DSH 主目录 |
| `DSH_DESKTOP_PORT_BASE` | `3080` | 端口扫描起点 |
| `DSH_DESKTOP_HOST` | `127.0.0.1` | 服务地址 |
| `DSH_DESKTOP_NODE` | 应用自带 `runtime\node.exe` | node.exe 路径 |
| `DSH_DESKTOP_DSH_BIN` | 应用自带包 | dsh `bin.js` 路径 |
| `DSH_DESKTOP_CWD` | 用户主目录 | 服务进程工作目录（会话默认工作区根） |
| `DSH_DESKTOP_SMOKE` | 关 | `1` = 冒烟模式 |

## 目录结构

```
dsh-desktop\
├─ main.cjs          桌面外壳主进程（服务管理 + 窗口 + 托盘）
├─ package.json      依赖与 electron-builder 打包配置
├─ runtime\node.exe  打包进应用的 Node 运行时（构建时生成）
├─ assets\           icon.ico / tray.png
└─ dist\             打包产物（构建时生成）
```

## 与命令行版的关系

- 不冲突：如果命令行已有 `dsh web` 在跑（占用 3080），桌面版会直接连上去；关掉桌面版不会影响它。
- 独立：如果 3080 空闲，桌面版自己拉起服务，退出时自动关闭。
- 会话共享：两边使用同一份 `~/.dsh` 数据。
