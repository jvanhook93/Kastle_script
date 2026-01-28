const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("inet", {
  onBackendStatus: (cb) => {
    ipcRenderer.removeAllListeners("backend:status");
    ipcRenderer.on("backend:status", (_evt, data) => cb(data));
  },
  requestBackendStatus: () => ipcRenderer.send("backend:requestStatus"),
});
