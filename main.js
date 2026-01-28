// main.js
const { app, BrowserWindow, ipcMain } = require("electron");
const path = require("path");
const { spawn } = require("child_process");
const http = require("http");
const fs = require("fs");
const { autoUpdater } = require("electron-updater");

let backendProcess = null;
let mainWindow = null;

// Track last known status so renderer can request it
let lastBackendStatus = { status: "starting", detail: "Launching backend…" };

function logToFile(msg) {
  try {
    const p = path.join(app.getPath("userData"), "inet-report.log");
    fs.appendFileSync(p, `[${new Date().toISOString()}] ${msg}\n`);
  } catch {}
}

function httpGet(url) {
  return new Promise((resolve, reject) => {
    const req = http.get(url, (res) => {
      res.resume();
      resolve(res.statusCode);
    });
    req.on("error", reject);
  });
}

function setBackendStatus(status, detail = "") {
  lastBackendStatus = { status, detail };

  try {
    if (mainWindow && !mainWindow.isDestroyed()) {
      // send even if devtools open, etc.
      mainWindow.webContents.send("backend:status", lastBackendStatus);
    }
  } catch {}
}

async function waitForBackendDetailed({ tries = 60, delayMs = 250 } = {}) {
  const url = "http://127.0.0.1:5000/ping";
  for (let i = 0; i < tries; i++) {
    setBackendStatus("checking", `Attempt ${i + 1}/${tries}`);
    try {
      const code = await httpGet(url);
      if (code === 200) return true;
    } catch (_) {}
    await new Promise((r) => setTimeout(r, delayMs));
  }
  return false;
}

function getBackendExePath() {
  return app.isPackaged
    ? path.join(process.resourcesPath, "backend", "kastle_backend.exe")
    : path.join(__dirname, "backend", "dist", "kastle_backend.exe");
}

function killBackend() {
  if (!backendProcess || backendProcess.killed) return;

  try {
    if (process.platform === "win32" && backendProcess.pid) {
      spawn("taskkill", ["/PID", String(backendProcess.pid), "/T", "/F"], {
        windowsHide: true,
        shell: false,
      });
    } else {
      backendProcess.kill("SIGTERM");
    }
  } catch (_) {
    // ignore
  } finally {
    backendProcess = null;
  }
}

function startBackend() {
  if (backendProcess && !backendProcess.killed) return;

  const backendExe = getBackendExePath();
  if (!fs.existsSync(backendExe)) {
    throw new Error(`Backend executable not found: ${backendExe}`);
  }

  backendProcess = spawn(backendExe, [], {
    cwd: path.dirname(backendExe),
    windowsHide: true,
    shell: false,
  });

  logToFile(`Backend started pid=${backendProcess.pid}`);

  backendProcess.on("exit", (code) => {
    logToFile(`Backend exited code=${code}`);
    setBackendStatus("error", `Backend exited (code ${code})`);
  });

  backendProcess.stdout?.on("data", (d) => logToFile(`Backend: ${String(d).trim()}`));
  backendProcess.stderr?.on("data", (d) => logToFile(`BackendERR: ${String(d).trim()}`));
}

function setupAutoUpdates() {
  if (!app.isPackaged) return;

  autoUpdater.autoDownload = true;

  autoUpdater.on("checking-for-update", () => logToFile("UPDATER: checking"));
  autoUpdater.on("update-available", (info) => logToFile(`UPDATER: available ${info?.version}`));
  autoUpdater.on("update-not-available", () => logToFile("UPDATER: none"));
  autoUpdater.on("error", (err) => logToFile(`UPDATER: error ${err?.message || err}`));
  autoUpdater.on("download-progress", (p) =>
    logToFile(`UPDATER: ${Math.round(p.percent || 0)}%`)
  );
  autoUpdater.on("update-downloaded", () => {
    logToFile("UPDATER: downloaded -> quitAndInstall()");
    autoUpdater.quitAndInstall();
  });

  autoUpdater.checkForUpdatesAndNotify();
}

function createWindow() {
  const iconPath = app.isPackaged
    ? path.join(process.resourcesPath, "assets", "icon.ico")
    : path.join(__dirname, "assets", "icon.ico");

  const win = new BrowserWindow({
    width: 1000,
    height: 700,
    title: "Inet Report Software",
    icon: iconPath,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, "preload.js"),
    },
  });

  win.loadFile(path.join(__dirname, "frontend", "index.html"));

  // Prevent navigation away from local UI
  win.webContents.on("will-navigate", (event) => event.preventDefault());
  win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));

  win.on("closed", () => {
    mainWindow = null;
    killBackend();
  });

  // ✅ Once the renderer is ready, push latest status (fixes stuck splash)
  win.webContents.on("did-finish-load", () => {
    try {
      win.webContents.send("backend:status", lastBackendStatus);
    } catch {}
  });

  return win;
}

// Renderer can request current status (optional but useful)
ipcMain.on("backend:requestStatus", (evt) => {
  evt.reply("backend:status", lastBackendStatus);
});

// Prevent multiple instances (prevents multiple backends)
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
}

app.whenReady().then(async () => {
  logToFile(`START appVersion=${app.getVersion()} packaged=${app.isPackaged}`);

  mainWindow = createWindow();

  setBackendStatus("starting", "Launching backend…");

  try {
    startBackend();
  } catch (err) {
    const msg = err?.message || String(err);
    logToFile(`Backend start error: ${msg}`);
    setBackendStatus("error", msg);
    return;
  }

  const ready = await waitForBackendDetailed();
  logToFile(`Backend ready=${ready}`);

  if (ready) setBackendStatus("ready", "Backend online");
  else setBackendStatus("error", "Backend did not respond on /ping");

  setupAutoUpdates();
});

// Ensure backend is killed no matter how app exits
app.on("before-quit", () => killBackend());
app.on("will-quit", () => killBackend());
app.on("quit", () => killBackend());

app.on("window-all-closed", () => {
  killBackend();
  if (process.platform !== "darwin") app.quit();
});

process.on("exit", () => killBackend());
process.on("SIGINT", () => {
  killBackend();
  process.exit(0);
});
process.on("SIGTERM", () => {
  killBackend();
  process.exit(0);
});
