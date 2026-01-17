const { contextBridge, ipcRenderer } = require('electron');

// Expose a safe API to the renderer process
contextBridge.exposeInMainWorld('traceAPI', {
  // Ping the main process (for testing IPC)
  ping: () => ipcRenderer.invoke('ping'),

  // Platform info
  platform: process.platform,

  // Future IPC methods will be added here for:
  // - Python backend communication
  // - Chat queries
  // - Note retrieval
  // - Settings management
  // - Permission status checks
});
