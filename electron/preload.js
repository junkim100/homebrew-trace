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

  // Permission methods (native - handled by Electron main process)
  permissions: {
    // Check all permissions (native)
    checkAll: () => ipcRenderer.invoke('permissions:check'),

    // Check a specific permission (uses native check)
    check: (permission) => ipcRenderer.invoke('permissions:check').then(state => state[permission]),

    // Get instructions for a permission
    getInstructions: (permission) => {
      const instructions = {
        screen_recording: {
          title: 'Screen Recording',
          description: 'Trace needs screen recording permission to capture screenshots of your activity.',
          steps: [
            'Click "Open System Settings" below',
            'Find Trace in the list and enable it',
            'If Trace is not listed, click the + button and add it',
            'Restart Trace after enabling the permission',
          ],
          requires_restart: true,
        },
        accessibility: {
          title: 'Accessibility',
          description: 'Trace needs accessibility permission to detect which app and window you are using.',
          steps: [
            'Click "Request Permission" to show the system prompt',
            'Or click "Open System Settings" to enable manually',
          ],
          requires_restart: false,
        },
        location: {
          title: 'Location Services (Optional)',
          description: 'Trace can optionally capture your location to add context to your notes. Note: Location requires a code-signed app to work properly.',
          steps: [
            'This feature requires the app to be code-signed',
            'You can skip this permission - the app works without it',
          ],
          requires_restart: false,
        },
      };
      return Promise.resolve(instructions[permission] || {});
    },

    // Open system settings for a permission (native)
    openSettings: (permission) => ipcRenderer.invoke('permissions:openSettings', permission),

    // Request accessibility permission prompt (native - shows system dialog)
    requestAccessibility: () => ipcRenderer.invoke('permissions:requestAccessibility'),

    // Request location permission prompt (triggers via geolocation API)
    requestLocation: async () => {
      return new Promise((resolve) => {
        navigator.geolocation.getCurrentPosition(
          () => resolve({ success: true, granted: true }),
          async (error) => {
            // If denied, open System Settings for Location Services
            if (error.code === error.PERMISSION_DENIED) {
              await ipcRenderer.invoke('permissions:openSettings', 'location');
              resolve({ success: true, granted: false, openedSettings: true });
            } else {
              resolve({ success: true, granted: false, error: error.message });
            }
          },
          { timeout: 10000 }
        );
      });
    },

    // Request screen recording (just opens settings - can't be requested programmatically)
    requestScreenRecording: () => ipcRenderer.invoke('permissions:requestScreenRecording'),
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

  // Export methods (for backup/export)
  export: {
    // Get summary of exportable data
    summary: () =>
      ipcRenderer.invoke('python:call', 'export.summary', {}),

    // Export to JSON format
    toJson: (outputPath) =>
      ipcRenderer.invoke('python:call', 'export.json', { output_path: outputPath }),

    // Export to Markdown directory
    toMarkdown: (outputPath) =>
      ipcRenderer.invoke('python:call', 'export.markdown', { output_path: outputPath }),

    // Export to ZIP archive
    toArchive: (outputPath) =>
      ipcRenderer.invoke('python:call', 'export.archive', { output_path: outputPath }),

    // Show save dialog and export
    saveArchive: async () => {
      const result = await ipcRenderer.invoke('dialog:showSaveDialog', {
        title: 'Export Trace Data',
        defaultPath: `trace-export-${new Date().toISOString().split('T')[0]}.zip`,
        filters: [
          { name: 'ZIP Archive', extensions: ['zip'] },
        ],
      });
      if (result.canceled || !result.filePath) {
        return { success: false, canceled: true };
      }
      return ipcRenderer.invoke('python:call', 'export.archive', { output_path: result.filePath });
    },
  },

  // Graph visualization methods
  graph: {
    // Get graph data for visualization
    getData: (options = {}) =>
      ipcRenderer.invoke('python:call', 'graph.data', {
        days_back: options.daysBack ?? 30,
        entity_types: options.entityTypes,
        min_edge_weight: options.minEdgeWeight ?? 0.3,
        limit: options.limit ?? 100,
      }),

    // Get entity types with counts
    getEntityTypes: () =>
      ipcRenderer.invoke('python:call', 'graph.entity_types', {}),

    // Get entity details
    getEntityDetails: (entityId) =>
      ipcRenderer.invoke('python:call', 'graph.entity_details', { entity_id: entityId }),
  },

  // Open loops methods (for incomplete tasks tracking)
  openLoops: {
    // List open loops from recent notes
    list: (options = {}) =>
      ipcRenderer.invoke('python:call', 'openloops.list', {
        days_back: options.daysBack ?? 7,
        limit: options.limit ?? 50,
      }),

    // Get open loops summary
    summary: () =>
      ipcRenderer.invoke('python:call', 'openloops.summary', {}),
  },

  // Blocklist methods (for blocking apps/domains from capture)
  blocklist: {
    // List all blocklist entries
    list: (includeDisabled = true) =>
      ipcRenderer.invoke('python:call', 'blocklist.list', { include_disabled: includeDisabled }),

    // Add an app to the blocklist
    addApp: (bundleId, displayName = null, blockScreenshots = true, blockEvents = true) =>
      ipcRenderer.invoke('python:call', 'blocklist.add_app', {
        bundle_id: bundleId,
        display_name: displayName,
        block_screenshots: blockScreenshots,
        block_events: blockEvents,
      }),

    // Add a domain to the blocklist
    addDomain: (domain, displayName = null, blockScreenshots = true, blockEvents = true) =>
      ipcRenderer.invoke('python:call', 'blocklist.add_domain', {
        domain: domain,
        display_name: displayName,
        block_screenshots: blockScreenshots,
        block_events: blockEvents,
      }),

    // Remove an entry from the blocklist
    remove: (blocklistId) =>
      ipcRenderer.invoke('python:call', 'blocklist.remove', { blocklist_id: blocklistId }),

    // Enable or disable a blocklist entry
    setEnabled: (blocklistId, enabled) =>
      ipcRenderer.invoke('python:call', 'blocklist.set_enabled', {
        blocklist_id: blocklistId,
        enabled: enabled,
      }),

    // Initialize default blocklist entries (password managers, banking sites)
    initDefaults: () =>
      ipcRenderer.invoke('python:call', 'blocklist.init_defaults', {}),

    // Check if an app or URL is blocked
    check: (bundleId = null, url = null) =>
      ipcRenderer.invoke('python:call', 'blocklist.check', {
        bundle_id: bundleId,
        url: url,
      }),
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
