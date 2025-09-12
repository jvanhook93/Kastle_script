const { app, BrowserWindow } = require("electron");
const path = require("path");
const { spawn } = require("child_process");

let flaskProcess;

function createWindow() {
  const win = new BrowserWindow({
    width: 800,
    height: 600,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
  });

  win.loadFile(path.join(__dirname, "frontend", "index.html"));
}

app.whenReady().then(() => {
  const backendPath = path.join(__dirname, "backend", "app.py");
  flaskProcess = spawn("python", [backendPath], { shell: true });

  flaskProcess.stdout.on("data", (data) => {
    console.log(`Flask: ${data}`);
  });

  flaskProcess.stderr.on("data", (data) => {
    console.error(`Flask error: ${data}`);
  });

  createWindow();
});

app.on("window-all-closed", () => {
  if (flaskProcess) flaskProcess.kill();
  if (process.platform !== "darwin") app.quit();
});
