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

  // Dashboard methods
  dashboard: {
    // Get all dashboard data
    getData: (daysBack = 7) =>
      ipcRenderer.invoke('python:call', 'dashboard.data', { days_back: daysBack }),

    // Get productivity summary
    getSummary: (daysBack = 7) =>
      ipcRenderer.invoke('python:call', 'dashboard.summary', { days_back: daysBack }),

    // Get app usage statistics
    getAppUsage: (daysBack = 7, limit = 10) =>
      ipcRenderer.invoke('python:call', 'dashboard.appUsage', { days_back: daysBack, limit }),

    // Get topic usage statistics
    getTopicUsage: (daysBack = 7, limit = 10) =>
      ipcRenderer.invoke('python:call', 'dashboard.topicUsage', { days_back: daysBack, limit }),

    // Get activity trend
    getActivityTrend: (daysBack = 30) =>
      ipcRenderer.invoke('python:call', 'dashboard.activityTrend', { days_back: daysBack }),

    // Get activity heatmap
    getHeatmap: (daysBack = 30) =>
      ipcRenderer.invoke('python:call', 'dashboard.heatmap', { days_back: daysBack }),
  },

  // Weekly digest methods
  digest: {
    // Get current week digest
    getCurrent: () =>
      ipcRenderer.invoke('python:call', 'digest.current', {}),

    // Get digest for a specific week
    getWeek: (weekOffset = 1) =>
      ipcRenderer.invoke('python:call', 'digest.week', { week_offset: weekOffset }),

    // Send digest notification
    sendNotification: (weekOffset = 1) =>
      ipcRenderer.invoke('python:call', 'digest.notify', { week_offset: weekOffset }),

    // Get digest history
    getHistory: (weeks = 4) =>
      ipcRenderer.invoke('python:call', 'digest.history', { weeks }),
  },

  // Pattern detection methods
  patterns: {
    // Get all detected patterns
    getAll: (daysBack = 30) =>
      ipcRenderer.invoke('python:call', 'patterns.all', { days_back: daysBack }),

    // Get insights summary (top 3 patterns)
    getSummary: (daysBack = 30) =>
      ipcRenderer.invoke('python:call', 'patterns.summary', { days_back: daysBack }),

    // Get time of day patterns
    getTimeOfDay: (daysBack = 30) =>
      ipcRenderer.invoke('python:call', 'patterns.timeOfDay', { days_back: daysBack }),

    // Get day of week patterns
    getDayOfWeek: (daysBack = 30) =>
      ipcRenderer.invoke('python:call', 'patterns.dayOfWeek', { days_back: daysBack }),

    // Get app usage patterns
    getApps: (daysBack = 30) =>
      ipcRenderer.invoke('python:call', 'patterns.apps', { days_back: daysBack }),

    // Get focus session patterns
    getFocus: (daysBack = 30) =>
      ipcRenderer.invoke('python:call', 'patterns.focus', { days_back: daysBack }),
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
    // Get all settings with metadata (config, options, defaults, paths)
    getAll: () => ipcRenderer.invoke('python:call', 'settings.get_all', {}),

    // Get current settings (legacy compatibility)
    get: () => ipcRenderer.invoke('python:call', 'settings.get', {}),

    // Set one or more settings (can be nested or flat key paths)
    set: (settings) =>
      ipcRenderer.invoke('python:call', 'settings.set', { settings }),

    // Set a single setting value by key path (e.g., "capture.summarization_interval_minutes")
    setValue: (key, value) =>
      ipcRenderer.invoke('python:call', 'settings.set_value', { key, value }),

    // Set API key
    setApiKey: (apiKey) =>
      ipcRenderer.invoke('python:call', 'settings.set_api_key', { api_key: apiKey }),

    // Validate API key (tests against OpenAI API)
    validateApiKey: (apiKey) =>
      ipcRenderer.invoke('python:call', 'settings.validate_api_key', { api_key: apiKey }),

    // Appearance settings (dock visibility, launch at login)
    getAppearance: () => ipcRenderer.invoke('python:call', 'settings.get_appearance', {}),
    setAppearance: (settings) =>
      ipcRenderer.invoke('python:call', 'settings.set_appearance', settings),

    // Capture settings (intervals, blocklist)
    getCapture: () => ipcRenderer.invoke('python:call', 'settings.get_capture', {}),
    setCapture: (settings) =>
      ipcRenderer.invoke('python:call', 'settings.set_capture', settings),

    // Notification settings (weekly digest)
    getNotifications: () => ipcRenderer.invoke('python:call', 'settings.get_notifications', {}),
    setNotifications: (settings) =>
      ipcRenderer.invoke('python:call', 'settings.set_notifications', settings),

    // Keyboard shortcut settings
    getShortcuts: () => ipcRenderer.invoke('python:call', 'settings.get_shortcuts', {}),
    setShortcuts: (settings) =>
      ipcRenderer.invoke('python:call', 'settings.set_shortcuts', settings),

    // Data management settings (retention)
    getData: () => ipcRenderer.invoke('python:call', 'settings.get_data', {}),
    setData: (settings) =>
      ipcRenderer.invoke('python:call', 'settings.set_data', settings),

    // Reset all settings to defaults
    reset: () => ipcRenderer.invoke('python:call', 'settings.reset', {}),
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

  // Spotlight integration methods
  spotlight: {
    // Get Spotlight indexing status
    status: () =>
      ipcRenderer.invoke('python:call', 'spotlight.status', {}),

    // Reindex all notes for Spotlight
    reindex: () =>
      ipcRenderer.invoke('python:call', 'spotlight.reindex', {}),

    // Index a single note for Spotlight
    indexNote: (notePath, options = {}) =>
      ipcRenderer.invoke('python:call', 'spotlight.indexNote', {
        notePath,
        title: options.title,
        summary: options.summary,
        entities: options.entities,
      }),

    // Trigger Spotlight to reindex using mdimport
    triggerReindex: () =>
      ipcRenderer.invoke('python:call', 'spotlight.triggerReindex', {}),
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

  // Appearance methods (dock visibility, launch at login)
  appearance: {
    // Get current appearance settings
    get: () => ipcRenderer.invoke('appearance:get'),

    // Set dock visibility (macOS)
    setDockVisibility: (showInDock) => ipcRenderer.invoke('appearance:setDockVisibility', showInDock),

    // Set launch at login
    setLaunchAtLogin: (launchAtLogin) => ipcRenderer.invoke('appearance:setLaunchAtLogin', launchAtLogin),
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

  // Global keyboard shortcuts
  shortcuts: {
    // Get current shortcut bindings
    get: () => ipcRenderer.invoke('shortcuts:get'),

    // Set a shortcut binding
    set: (name, accelerator) => ipcRenderer.invoke('shortcuts:set', name, accelerator),

    // Reset shortcuts to defaults
    reset: () => ipcRenderer.invoke('shortcuts:reset'),

    // Listen for shortcut events (e.g., quickCapture)
    onQuickCapture: (callback) => {
      ipcRenderer.on('shortcut:quickCapture', callback);
      return () => ipcRenderer.removeListener('shortcut:quickCapture', callback);
    },
  },

  // Tray menu event listeners
  tray: {
    // Listen for open note from tray
    onOpenNote: (callback) => {
      ipcRenderer.on('tray:openNote', (event, noteId) => callback(noteId));
      return () => ipcRenderer.removeAllListeners('tray:openNote');
    },

    // Listen for open graph from tray
    onOpenGraph: (callback) => {
      ipcRenderer.on('tray:openGraph', callback);
      return () => ipcRenderer.removeAllListeners('tray:openGraph');
    },

    // Listen for open settings from tray
    onOpenSettings: (callback) => {
      ipcRenderer.on('tray:openSettings', callback);
      return () => ipcRenderer.removeAllListeners('tray:openSettings');
    },
  },
});
