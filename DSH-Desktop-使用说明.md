# DSH Desktop 使用说明

**DSH Desktop** 是把 DeepSeek Harness 网页界面包装成桌面应用的项目。
双击图标即可打开 Harness 窗口，**不需要打开任何命令行**。

## 一、安装与启动

### 方式 A：安装版（推荐）
1. 双击 `dsh-desktop\dist\DSH-Desktop-Setup-0.1.0.exe`
2. 按向导安装（可自选目录，自动创建桌面 + 开始菜单快捷方式）
3. 双击桌面上的 **DSH Desktop** 图标

### 方式 B：便携版
1. 双击 `dsh-desktop\dist\DSH-Desktop-Portable-0.1.0.exe` 直接运行（免安装、单文件）

> 首次运行 Windows SmartScreen 可能提示"未知发布者"（未做代码签名），
> 点 **更多信息 → 仍要运行** 即可。

## 二、它做了什么

| 步骤 | 行为 |
|---|---|
| 启动 | 扫描端口（从 3080 开始）寻找 DSH Web 服务 |
| 已存在 | 直接复用（比如你命令行开着的 `dsh web`），不重复启动 |
| 不存在 | 用**应用自带的 node.exe** 在后台启动一个，窗口打开后即可用 |
| 退出 | 只关闭自己启动的服务；复用别人的服务不受影响 |

其他特性：
- **单实例**：重复双击只会把已有窗口带到前台
- **托盘图标**：右键可显示窗口 / 在浏览器打开 / 退出
- **记忆窗口**：大小和位置自动保存
- **断线重连**：服务挂掉会自动轮询恢复

## 三、它共享哪些数据

- DSH 主目录沿用 `C:\Users\<你>\.dsh`（模型凭证、设置、会话历史）
- 与命令行版 `dsh web` **完全共享**：桌面里开的会话，命令行里也能看到

## 四、在别的电脑上用（首次运行要求）

- 应用自带 Node 运行时和 DSH 启动器，**不需要装 Node.js**
- 首次启动会自动初始化 DSH 的 web profile，此时需要：
  - 装有 **pnpm**（`npm install -g pnpm`）
  - 能联网（下载 profile 依赖，约几百 MB）
- 初始化完成后即可离线使用

## 五、配置（可选环境变量）

| 变量 | 默认 | 作用 |
|---|---|---|
| `DSH_HOME` | `%USERPROFILE%\.dsh` | DSH 主目录 |
| `DSH_DESKTOP_PORT_BASE` | `3080` | 端口扫描起点 |
| `DSH_DESKTOP_CWD` | 用户主目录 | 服务工作目录（会话默认工作区根） |

## 六、常见问题

**Q：模型密钥在哪配？**
A：和命令行版一样，在 DSH 的设置页面配置，或编辑 `~/.dsh/.credentials.yaml`。

**Q：窗口打开了但空白/提示服务未响应？**
A：服务可能启动失败。看日志：`%APPDATA%\DSH Desktop\dsh-desktop.log`。

**Q：怎么重新打包？**
A：项目目录 `dsh-desktop` 下执行 `npm run dist`，产物在 `dist\`。

## 七、项目结构

```
小项目\dsh-desktop\
├─ main.cjs                桌面外壳主进程（约 400 行，含完整注释）
├─ package.json            依赖 + electron-builder 打包配置
├─ runtime\node.exe        打包进应用的 Node 运行时
├─ assets\icon.ico         应用图标（脚本生成：scripts\make-icon.ps1）
├─ scripts\make-icon.ps1   图标生成脚本
├─ dist\                   打包产物（安装包 + 便携版）
└─ README.md               开发说明
```
