# dsh-files 插件安装记录

安装时间：2026-08-17

## 装了什么

社区插件 [taxueseek/dsh-files](https://github.com/taxueseek/dsh-files)（v0.2.0，GitHub main 分支 tarball），DeepSeek Harness 双面插件：

- **服务端面**：`read_document` 工具 —— 读取文本 / PDF / DOCX / XLSX，内容嗅探（不信任扩展名）、GB18030 中文编码回退、行号 + offset/limit 分页、LRU 解析缓存
- **客户端面**：Web 输入框回形针上传按钮，浮动彩色卡片，按会话隔离存储到 `<会话工作区>/.dsh-filess/`，TTL 7 天自动清扫

## 安装方式

```bat
:: 1. 安装 pnpm（dsh plugin 依赖它）
npm install -g pnpm

:: 2. 把插件加入 web profile（GitHub 无 git 也可用 tarball URL）
dsh plugin --profile web add https://codeload.github.com/taxueseek/dsh-files/tar.gz/refs/heads/main

:: 3. 重启 dsh web 生效
```

安装后 `~/.dsh/profiles/web/package.json` 的 `dsh.profile.bundles` 变为：
`@deepseek-ai/dsh-base` → `@deepseek-ai/dsh-web-app` → `dsh-files`

## 更新 / 卸载

```bat
dsh plugin --profile web update dsh-files   :: 更新到 main 最新
dsh plugin --profile web remove dsh-files   :: 卸载
:: 之后同样需要重启 dsh web
```

## 验证结果（2026-08-18）

- [x] `dsh web --dump-config`：组合树含 `files-toolkit` 行（name: dsh-files）
- [x] 独立实例（:3099）真实启动无报错
- [x] 前端 boot manifest 注入 `dsh-files` 客户端入口，`/plugins/dsh-files/client.js` 返回 200
- [x] 主服务（:3080）已重启（新 PID 15688），boot manifest 含 `dsh-files`，client.js 200
- [x] `read_document` 工具实测：读取文本文件，格式嗅探 + 行号分页 + 中文内容正常

> 注：`dsh web` 内置的 `read`/`write`/`edit`/`glob`/`grep` 工具（`dsh-tool-fs` / `dsh-tool-fs-search`）本来就随 dsh-base 启用；本插件额外提供的是 **PDF/DOCX/XLSX 等文档读取** 与 **Web 上传** 能力。

## 重启小记（踩坑）

重启通过 WMI 创建脱离进程（`Invoke-CimMethod Win32_Process Create`）执行 `web-restart.ps1` 完成：
杀旧服务 → 以原工作目录 `H:\Deepseek Harness\小项目` 拉起新 `dsh web` → 轮询 3080 验证 manifest。
踩坑：Windows PowerShell 5.1 按 ANSI 解析 .ps1，脚本里含中文（且引号被破坏）会解析失败秒退；脚本保持纯 ASCII（中文路径用 `[char]` 码点拼接）即可。日志留在 `%USERPROFILE%\.dsh\web-restart.log`。
