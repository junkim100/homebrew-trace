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

  // Chat methods
  chat: {
    // Send a query and get a response with answer, citations, notes
    query: (query, options = {}) =>
      ipcRenderer.invoke('python:call', 'chat.query', {
        query,
        time_filter: options.timeFilter,
        include_graph_expansion: options.includeGraphExpansion ?? true,
        include_aggregates: options.includeAggregates ?? true,
        max_results: options.maxResults ?? 10,
      }),
  },

  // Notes methods
  notes: {
    // Read a specific note by ID
    read: (noteId) =>
      ipcRenderer.invoke('python:call', 'notes.read', { note_id: noteId }),

    // List available notes
    list: (options = {}) =>
      ipcRenderer.invoke('python:call', 'notes.list', {
        start_date: options.startDate,
        end_date: options.endDate,
        limit: options.limit ?? 50,
      }),
  },

  // Settings methods
  settings: {
    // Get current settings
    get: () => ipcRenderer.invoke('python:call', 'settings.get', {}),

    // Set API key
    setApiKey: (apiKey) =>
      ipcRenderer.invoke('python:call', 'settings.set_api_key', { api_key: apiKey }),
  },

  // Window control methods
  window: {
    // Minimize window
    minimize: () => ipcRenderer.invoke('window:minimize'),

    // Maximize window
    maximize: () => ipcRenderer.invoke('window:maximize'),

    // Close window
    close: () => ipcRenderer.invoke('window:close'),
  },
});
