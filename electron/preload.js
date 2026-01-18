const { contextBridge, ipcRenderer } = require('electron');

// Expose a safe API to the renderer process
contextBridge.exposeInMainWorld('traceAPI', {
  // Ping the Electron main process (for testing IPC)
  ping: () => ipcRenderer.invoke('ping'),

  // Platform info
  platform: process.platform,

  // Python backend methods
  python: {
    // Check if Python backend is ready
    isReady: () => ipcRenderer.invoke('python:ready'),

    // Ping the Python backend
    ping: () => ipcRenderer.invoke('python:ping'),

    // Get Python backend status
    getStatus: () => ipcRenderer.invoke('python:status'),

    // Generic call to Python backend
    call: (method, params) => ipcRenderer.invoke('python:call', method, params),
  },

  // Permission methods
  permissions: {
    // Check all permissions
    checkAll: () => ipcRenderer.invoke('python:call', 'permissions.check_all', {}),

    // Check a specific permission
    check: (permission) =>
      ipcRenderer.invoke('python:call', 'permissions.check', { permission }),

    // Get instructions for a permission
    getInstructions: (permission) =>
      ipcRenderer.invoke('python:call', 'permissions.get_instructions', { permission }),

    // Open system settings for a permission
    openSettings: (permission) =>
      ipcRenderer.invoke('python:call', 'permissions.open_settings', { permission }),

    // Request accessibility permission prompt
    requestAccessibility: () =>
      ipcRenderer.invoke('python:call', 'permissions.request_accessibility', {}),

    // Request location permission prompt
    requestLocation: () =>
      ipcRenderer.invoke('python:call', 'permissions.request_location', {}),
  },
});
