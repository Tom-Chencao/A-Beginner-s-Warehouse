'use strict';

/**
 * DSH Desktop — DeepSeek Harness 的桌面外壳。
 *
 * 职责：
 *   1. 找到（或启动）DSH Web 服务 —— 若目标端口上已有 DSH 服务则直接复用
 *      （与命令行 `dsh web` 并存），否则用自带的 node.exe 后台拉起一个，
 *      应用退出时只杀掉自己拉起的那个。
 *   2. 在原生窗口中加载 DSH Web UI，并提供托盘图标、单实例锁、窗口状态记忆。
 *
 * 环境变量覆盖（均可选）：
 *   DSH_HOME                —— DSH 主目录（默认 %USERPROFILE%\.dsh）
 *   DSH_DESKTOP_PORT_BASE   —— 端口扫描起点（默认 3080）
 *   DSH_DESKTOP_HOST        —— 服务地址（默认 127.0.0.1）
 *   DSH_DESKTOP_NODE        —— node.exe 路径（默认应用自带 runtime/node.exe）
 *   DSH_DESKTOP_DSH_BIN     —— dsh bin.js 路径（默认应用自带包）
 *   DSH_DESKTOP_CWD         —— 服务进程的工作目录（默认用户主目录）
 *   DSH_DESKTOP_SMOKE=1     —— 冒烟模式：就绪后打印一行结果并退出
 */

const { app, BrowserWindow, Menu, Tray, dialog, nativeImage, shell, screen } = require('electron');
const { spawn, spawnSync } = require('node:child_process');
const http = require('node:http');
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');

const APP_ID = 'com.deepseekai.dshdesktop';
const APP_NAME = 'DSH Desktop';
const SMOKE = process.argv.includes('--smoke') || process.env.DSH_DESKTOP_SMOKE === '1';
const DSH_HOME = process.env.DSH_HOME || path.join(os.homedir(), '.dsh');
const HOST = process.env.DSH_DESKTOP_HOST || '127.0.0.1';
const PORT_BASE = Number.parseInt(process.env.DSH_DESKTOP_PORT_BASE || '3080', 10);
const MARKER = 'DeepSeek Harness';
const READY_TIMEOUT_MS = 180000;

let mainWindow = null;
let tray = null;
let child = null;
let logStream = null;
let quitting = false;
let spawnedPort = null; // 我们拉起的服务端口（退出时需要杀掉）
let activeUrl = null;

// ---------------------------------------------------------------------------
// 日志
// ---------------------------------------------------------------------------

function logFile() {
  return path.join(app.getPath('userData'), 'dsh-desktop.log');
}

function log(msg) {
  const line = `[${new Date().toISOString()}] ${msg}`;
  try {
    if (!logStream) {
      fs.mkdirSync(path.dirname(logFile()), { recursive: true });
      logStream = fs.createWriteStream(logFile(), { flags: 'a' });
    }
    logStream.write(line + '\n');
  } catch {
    /* 日志失败不影响主流程 */
  }
  console.log(line);
}

// ---------------------------------------------------------------------------
// 路径解析
// ---------------------------------------------------------------------------

function resolveNodeBinary() {
  const candidates = [];
  if (process.env.DSH_DESKTOP_NODE) candidates.push(process.env.DSH_DESKTOP_NODE);
  if (app.isPackaged) candidates.push(path.join(process.resourcesPath, 'runtime', 'node.exe'));
  candidates.push(path.join(app.getAppPath(), 'runtime', 'node.exe'));
  for (const c of candidates) {
    if (c && fs.existsSync(c)) return c;
  }
  return 'node'; // 最后回退到 PATH
}

function resolveDshBin() {
  if (process.env.DSH_DESKTOP_DSH_BIN) return process.env.DSH_DESKTOP_DSH_BIN;
  const c = path.join(app.getAppPath(), 'node_modules', '@deepseek-ai', 'dsh', 'lib', 'bin.js');
  return fs.existsSync(c) ? c : null;
}

// ---------------------------------------------------------------------------
// 端口探测：区分「DSH 服务」「被别的程序占用」「空闲」
// ---------------------------------------------------------------------------

function probe(port) {
  return new Promise((resolve) => {
    const req = http.get({ host: HOST, port, path: '/', timeout: 2500 }, (res) => {
      let body = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => {
        body += chunk;
        if (body.length > 65536) req.destroy();
      });
      res.on('end', () => resolve(body.includes(MARKER) ? 'dsh' : 'occupied'));
    });
    req.on('error', (err) => resolve(err.code === 'ECONNREFUSED' ? 'free' : 'occupied'));
    req.on('timeout', () => {
      req.destroy();
      resolve('occupied');
    });
  });
}

async function findTarget() {
  const last = PORT_BASE + 24;
  for (let p = PORT_BASE; p <= last; p++) {
    const status = await probe(p);
    if (status === 'dsh') {
      log(`端口 ${p} 已有 DSH 服务，直接复用`);
      return { port: p, reuse: true };
    }
    if (status === 'free') return { port: p, reuse: false };
  }
  return null;
}

// ---------------------------------------------------------------------------
// 服务进程管理
// ---------------------------------------------------------------------------

function startServer(port) {
  const nodeBin = resolveNodeBinary();
  const dshBin = resolveDshBin();
  if (!dshBin) {
    throw new Error(`找不到 DSH 启动器（@deepseek-ai/dsh/lib/bin.js），请重新安装 ${APP_NAME}`);
  }
  const env = { ...process.env, DSH_HOME };
  for (const k of ['DSH_SESSION_ID', 'DSH_SESSION_JSONL', 'DSH_WEB_URL', 'DSH_SHELL']) {
    delete env[k];
  }
  const cwd = process.env.DSH_DESKTOP_CWD || os.homedir();
  log(`启动 DSH Web 服务: ${nodeBin} ${dshBin} web --port ${port} (cwd=${cwd})`);
  child = spawn(nodeBin, [dshBin, 'web', '--port', String(port)], {
    cwd,
    env,
    stdio: logStream ? ['ignore', logStream, logStream] : 'ignore',
    windowsHide: true,
  });
  child.on('error', (err) => {
    log(`启动服务进程失败: ${err.message}`);
    child = null;
  });
  child.on('exit', (code, signal) => {
    log(`DSH Web 服务退出: code=${code} signal=${signal}`);
    const wasOurs = child !== null;
    child = null;
    if (!quitting && wasOurs && code !== 0 && spawnedPort !== null) {
      dialog.showErrorBox(
        APP_NAME,
        `DSH Web 服务异常退出（code=${code}）。\n\n日志文件：${logFile()}`
      );
    }
  });
}

function killChild() {
  if (!child || !child.pid) return;
  const pid = child.pid;
  log(`停止服务进程 pid=${pid}`);
  try {
    if (process.platform === 'win32') {
      spawnSync('taskkill', ['/pid', String(pid), '/T', '/F'], {
        windowsHide: true,
        stdio: 'ignore',
      });
    } else {
      child.kill();
    }
  } catch (err) {
    log(`停止进程失败: ${err.message}`);
  }
  child = null;
}

async function waitForReady(port, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (child === null && spawnedPort === port) return false; // 进程提前退出
    if ((await probe(port)) === 'dsh') return true;
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

// ---------------------------------------------------------------------------
// 窗口
// ---------------------------------------------------------------------------

function iconPath() {
  const p = path.join(app.getAppPath(), 'assets', 'icon.ico');
  return fs.existsSync(p) ? p : undefined;
}

function loadWindowState() {
  try {
    const p = path.join(app.getPath('userData'), 'window-state.json');
    const s = JSON.parse(fs.readFileSync(p, 'utf8'));
    if (Number.isInteger(s.width) && s.width >= 400 && Number.isInteger(s.height) && s.height >= 300) {
      const disp = screen.getDisplayMatching({ x: s.x, y: s.y, width: s.width, height: s.height });
      const area = disp.workArea;
      const width = Math.min(s.width, area.width);
      const height = Math.min(s.height, area.height);
      const x = Math.min(Math.max(s.x ?? area.x, area.x), area.x + area.width - width);
      const y = Math.min(Math.max(s.y ?? area.y, area.y), area.y + area.height - height);
      return { width, height, x, y };
    }
  } catch {
    /* 首次运行 */
  }
  return { width: 1440, height: 900 };
}

function saveWindowState() {
  try {
    if (!mainWindow || mainWindow.isMaximized() || mainWindow.isMinimized()) return;
    const p = path.join(app.getPath('userData'), 'window-state.json');
    fs.mkdirSync(path.dirname(p), { recursive: true });
    fs.writeFileSync(p, JSON.stringify(mainWindow.getBounds()));
  } catch {
    /* 忽略 */
  }
}

function offlineHtml(url) {
  return (
    '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>' +
    APP_NAME +
    '</title><style>body{font-family:"Segoe UI",sans-serif;background:#0b0e14;color:#cbd5e1;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}div{text-align:center}button{margin-top:16px;padding:10px 24px;font-size:15px;border-radius:8px;border:1px solid #334155;background:#1e293b;color:#e2e8f0;cursor:pointer}</style></head><body><div><h2>DSH Web 服务未响应</h2><p>正在等待服务恢复……</p><button onclick="location.href=' +
    JSON.stringify(url) +
    '">立即重试</button></div></body></html>'
  );
}

function pollRecovery(url, attempts) {
  if (quitting) return;
  const port = Number(new URL(url).port || '80');
  probe(port).then((status) => {
    if (quitting) return;
    if (status === 'dsh') {
      log(`服务已恢复，重新加载 ${url}`);
      if (mainWindow && !mainWindow.isDestroyed()) mainWindow.loadURL(url);
    } else {
      if (attempts === 0 && mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(offlineHtml(url)));
      }
      setTimeout(() => pollRecovery(url, attempts + 1), 2500);
    }
  });
}

function createWindow(url) {
  activeUrl = url;
  const st = loadWindowState();
  mainWindow = new BrowserWindow({
    ...st,
    minWidth: 960,
    minHeight: 620,
    title: APP_NAME,
    icon: iconPath(),
    autoHideMenuBar: true,
    backgroundColor: '#0b0e14',
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  Menu.setApplicationMenu(null);

  mainWindow.once('ready-to-show', () => mainWindow.show());
  mainWindow.on('close', saveWindowState);
  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  mainWindow.webContents.setWindowOpenHandler(({ url: u }) => {
    shell.openExternal(u);
    return { action: 'deny' };
  });

  mainWindow.webContents.on('did-fail-load', (event, code, desc, failedUrl) => {
    if (quitting || code === -3 || !/^https?:/.test(failedUrl)) return;
    log(`页面加载失败 (${code} ${desc})，开始轮询恢复: ${failedUrl}`);
    pollRecovery(failedUrl, 0);
  });

  mainWindow.loadURL(url);
}

// ---------------------------------------------------------------------------
// 托盘
// ---------------------------------------------------------------------------

function createTray() {
  const t = path.join(app.getAppPath(), 'assets', 'tray.png');
  if (!fs.existsSync(t)) return;
  tray = new Tray(nativeImage.createFromPath(t));
  tray.setToolTip(APP_NAME);
  tray.setContextMenu(
    Menu.buildFromTemplate([
      {
        label: '显示 DSH 窗口',
        click: () => {
          if (mainWindow) {
            if (mainWindow.isMinimized()) mainWindow.restore();
            mainWindow.show();
            mainWindow.focus();
          } else if (activeUrl) {
            createWindow(activeUrl);
          }
        },
      },
      {
        label: '在浏览器中打开',
        click: () => {
          if (activeUrl) shell.openExternal(activeUrl);
        },
      },
      { type: 'separator' },
      { label: '退出', click: () => app.quit() },
    ])
  );
  tray.on('double-click', () => {
    if (mainWindow) {
      mainWindow.show();
      mainWindow.focus();
    }
  });
}

// ---------------------------------------------------------------------------
// 生命周期
// ---------------------------------------------------------------------------

function cleanup() {
  quitting = true;
  if (spawnedPort !== null) killChild();
  try {
    if (logStream) logStream.end();
  } catch {
    /* 忽略 */
  }
}

app.on('before-quit', cleanup);
app.on('window-all-closed', () => app.quit());

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    app.setAppUserModelId(APP_ID);
    log(`${APP_NAME} 启动 (packaged=${app.isPackaged}, DSH_HOME=${DSH_HOME})`);

    let target;
    try {
      target = await findTarget();
    } catch (err) {
      log(`端口探测失败: ${err.message}`);
      dialog.showErrorBox(APP_NAME, `端口探测失败：${err.message}`);
      app.exit(1);
      return;
    }

    if (!target) {
      dialog.showErrorBox(APP_NAME, `端口 ${PORT_BASE}–${PORT_BASE + 24} 均被占用且没有可复用的 DSH 服务。`);
      app.exit(1);
      return;
    }

    if (!target.reuse) {
      spawnedPort = target.port;
      try {
        startServer(target.port);
      } catch (err) {
        log(`启动失败: ${err.message}`);
        dialog.showErrorBox(APP_NAME, err.message);
        app.exit(1);
        return;
      }
      const ok = await waitForReady(target.port, READY_TIMEOUT_MS);
      if (!ok) {
        log('服务启动超时或提前退出');
        dialog.showErrorBox(APP_NAME, `DSH Web 服务未能就绪。\n\n日志文件：${logFile()}`);
        cleanup();
        app.exit(1);
        return;
      }
      log(`服务就绪: http://${HOST}:${target.port}`);
    }

    const url = `http://${HOST}:${target.port}/`;
    createWindow(url);
    createTray();

    if (SMOKE) {
      console.log(`DSH_DESKTOP_SMOKE_OK port=${target.port} mode=${target.reuse ? 'reuse' : 'spawn'}`);
      setTimeout(() => {
        cleanup();
        app.exit(0);
      }, 500);
    }
  });
}
