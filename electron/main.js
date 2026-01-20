const { app, BrowserWindow, ipcMain, Tray, Menu, nativeImage, systemPreferences, shell, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const readline = require('readline');

let mainWindow = null;
let pythonProcess = null;
let pythonReady = false;
let pendingRequests = new Map(); // id -> { resolve, reject, timeout }
let requestId = 0;
let tray = null;

// Get the data directory path (where notes, db, cache are stored)
function getDataPath() {
  const homeDir = app.getPath('home');

  // Check for override via environment variable
  if (process.env.TRACE_DATA_ROOT) {
    return process.env.TRACE_DATA_ROOT;
  }

  // Default: ~/Library/Application Support/Trace (Apple recommended)
  return path.join(homeDir, 'Library', 'Application Support', 'Trace');
}

// Get the path to the Python executable
function getPythonPath() {
  const homeDir = app.getPath('home');
  const dataPath = getDataPath();

  if (app.isPackaged) {
    // When packaged, use the bundled Python executable
    const bundledPython = path.join(
      process.resourcesPath,
      'python-dist',
      'trace',
      'trace'  // The PyInstaller executable name
    );

    // Check if bundled Python exists
    if (fs.existsSync(bundledPython)) {
      console.log(`Using bundled Python: ${bundledPython}`);
      return {
        command: bundledPython,
        args: ['serve'],
        cwd: dataPath,
        env: { TRACE_DATA_ROOT: dataPath },
      };
    }

    // Fallback to uv if bundled Python not found (development builds)
    console.log('Bundled Python not found, falling back to uv');
  }

  // Development mode or fallback: use uv
  const projectRoot = app.isPackaged
    ? (process.env.TRACE_PROJECT_ROOT || path.join(homeDir, 'Trace'))
    : path.join(__dirname, '..');

  // When launched from app icon, PATH may not include ~/.local/bin
  // Try to find uv in common locations
  const uvPaths = [
    path.join(homeDir, '.local', 'bin', 'uv'),
    path.join(homeDir, '.cargo', 'bin', 'uv'),
    '/usr/local/bin/uv',
    '/opt/homebrew/bin/uv',
    'uv', // fallback to PATH
  ];

  let uvCommand = 'uv';
  for (const uvPath of uvPaths) {
    if (uvPath !== 'uv' && fs.existsSync(uvPath)) {
      uvCommand = uvPath;
      break;
    }
  }

  return {
    command: uvCommand,
    args: ['run', 'python', '-m', 'src.trace_app.cli', 'serve'],
    cwd: projectRoot,
    env: { TRACE_DATA_ROOT: dataPath },
  };
}

function startPythonBackend() {
  const { command, args, cwd, env: customEnv } = getPythonPath();
  const isBundled = command.includes('python-dist');

  console.log(`Starting Python backend: ${command} ${args.join(' ')} in ${cwd}`);
  console.log(`Using bundled Python: ${isBundled}`);

  // For bundled Python, ensure data directory exists
  // For development mode, check for project directory
  if (isBundled) {
    // Ensure data directory exists
    if (!fs.existsSync(cwd)) {
      try {
        fs.mkdirSync(cwd, { recursive: true });
        console.log(`Created data directory: ${cwd}`);
      } catch (err) {
        console.error(`Failed to create data directory: ${cwd}`, err);
        dialog.showMessageBox({
          type: 'error',
          title: 'Data Directory Error',
          message: 'Could not create the data directory.',
          detail: `Location: ${cwd}\n\nError: ${err.message}`,
          buttons: ['OK'],
        });
        return;
      }
    }
  } else {
    // Development mode: check for project directory and pyproject.toml
    if (!fs.existsSync(cwd)) {
      console.error(`Project directory not found: ${cwd}`);
      dialog.showMessageBox({
        type: 'error',
        title: 'Project Not Found',
        message: 'Could not find the Trace project directory.',
        detail: `Expected location: ${cwd}\n\nMake sure the Trace project is installed at this location.`,
        buttons: ['OK'],
      });
      return;
    }

    const pyprojectPath = path.join(cwd, 'pyproject.toml');
    if (!fs.existsSync(pyprojectPath)) {
      console.error(`pyproject.toml not found in: ${cwd}`);
      dialog.showMessageBox({
        type: 'error',
        title: 'Invalid Project',
        message: 'The Trace project directory is missing pyproject.toml.',
        detail: `Location: ${cwd}\n\nThis doesn't appear to be a valid Trace project.`,
        buttons: ['OK'],
      });
      return;
    }
  }

  // Merge environment variables
  const spawnEnv = {
    ...process.env,
    PYTHONUNBUFFERED: '1',
    ...customEnv,
  };

  // Only set PYTHONPATH for development mode (not needed for bundled)
  if (!isBundled) {
    spawnEnv.PYTHONPATH = cwd;
  }

  pythonProcess = spawn(command, args, {
    cwd,
    stdio: ['pipe', 'pipe', 'pipe'],
    env: spawnEnv,
  });

  // Create readline interface for reading JSON lines from stdout
  const rl = readline.createInterface({
    input: pythonProcess.stdout,
    crlfDelay: Infinity,
  });

  rl.on('line', (line) => {
    try {
      const message = JSON.parse(line);

      if (message.type === 'ready') {
        pythonReady = true;
        console.log(`Python backend ready (version ${message.version})`);
        updateTrayMenu();
        return;
      }

      // Handle response to a pending request
      if (message.id && pendingRequests.has(message.id)) {
        const { resolve, reject, timeout } = pendingRequests.get(message.id);
        clearTimeout(timeout);
        pendingRequests.delete(message.id);

        if (message.success) {
          resolve(message.result);
        } else {
          reject(new Error(message.error || 'Unknown error'));
        }
      }
    } catch (err) {
      console.error('Failed to parse Python output:', line, err);
    }
  });

  // Log stderr for debugging
  pythonProcess.stderr.on('data', (data) => {
    console.error(`Python stderr: ${data}`);
  });

  pythonProcess.on('error', (err) => {
    console.error('Failed to start Python backend:', err);
    pythonReady = false;

    // Show error dialog to user
    dialog.showMessageBox({
      type: 'error',
      title: 'Backend Error',
      message: 'Failed to start the Python backend.',
      detail: `Error: ${err.message}\n\nMake sure 'uv' is installed and the Trace project is at ~/Trace`,
      buttons: ['OK'],
    });
  });

  pythonProcess.on('exit', (code, signal) => {
    console.log(`Python backend exited (code: ${code}, signal: ${signal})`);
    pythonReady = false;
    pythonProcess = null;

    // Reject all pending requests
    for (const [id, { reject, timeout }] of pendingRequests) {
      clearTimeout(timeout);
      reject(new Error('Python backend exited'));
    }
    pendingRequests.clear();
  });
}

function stopPythonBackend() {
  if (pythonProcess) {
    // Send shutdown command
    callPython('shutdown', {}).catch(() => {});

    // Give it a moment to shut down gracefully
    setTimeout(() => {
      if (pythonProcess) {
        pythonProcess.kill();
        pythonProcess = null;
      }
    }, 1000);
  }
}

function callPython(method, params = {}, timeoutMs = 30000) {
  return new Promise((resolve, reject) => {
    if (!pythonProcess || !pythonReady) {
      reject(new Error('Python backend not ready'));
      return;
    }

    const id = `req_${++requestId}`;
    const request = { id, method, params };

    const timeout = setTimeout(() => {
      if (pendingRequests.has(id)) {
        pendingRequests.delete(id);
        reject(new Error(`Request ${method} timed out`));
      }
    }, timeoutMs);

    pendingRequests.set(id, { resolve, reject, timeout });

    try {
      pythonProcess.stdin.write(JSON.stringify(request) + '\n');
    } catch (err) {
      clearTimeout(timeout);
      pendingRequests.delete(id);
      reject(err);
    }
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
    titleBarStyle: 'hiddenInset',
    vibrancy: 'under-window',
    visualEffectState: 'active',
    show: false,
    // macOS features
    fullscreenable: true,
    simpleFullscreen: false, // Use native macOS fullscreen
  });

  // Load the app
  const indexPath = path.join(__dirname, 'dist', 'index.html');
  console.log(`Loading app from: ${indexPath}`);
  console.log(`__dirname: ${__dirname}`);
  console.log(`app.isPackaged: ${app.isPackaged}`);

  if (process.env.NODE_ENV === 'development') {
    mainWindow.loadURL('http://localhost:5173');
  } else {
    mainWindow.loadFile(indexPath).catch(err => {
      console.error(`Failed to load index.html: ${err}`);
    });
  }

  // Open DevTools only in development
  if (process.env.NODE_ENV === 'development') {
    mainWindow.webContents.openDevTools();
  }

  // Show window when ready to prevent visual flash
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  // On macOS, hide window instead of closing when clicking red button
  mainWindow.on('close', (event) => {
    if (process.platform === 'darwin' && !app.isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// Check and request permissions on startup
async function checkAndRequestPermissions() {
  const screenStatus = systemPreferences.getMediaAccessStatus('screen');
  const accessibilityStatus = systemPreferences.isTrustedAccessibilityClient(false);

  console.log('Startup permission check - Screen:', screenStatus, 'Accessibility:', accessibilityStatus);

  // Request accessibility permission if not granted (shows system prompt)
  if (!accessibilityStatus) {
    console.log('Requesting accessibility permission on startup...');
    // This will show the macOS system prompt for accessibility
    systemPreferences.isTrustedAccessibilityClient(true);
  }

  // For screen recording, we can't request programmatically - show a dialog
  if (screenStatus !== 'granted') {
    console.log('Screen recording not granted - prompting user');
    const result = await dialog.showMessageBox({
      type: 'info',
      title: 'Screen Recording Permission Required',
      message: 'Trace needs Screen Recording permission to capture screenshots of your activity.',
      detail: 'Click "Open System Settings" to enable this permission, then restart Trace.',
      buttons: ['Open System Settings', 'Later'],
      defaultId: 0,
      cancelId: 1,
    });

    if (result.response === 0) {
      // User clicked "Open System Settings"
      shell.openExternal('x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture');
    }
  }

  return {
    screen_recording: screenStatus === 'granted',
    accessibility: accessibilityStatus,
  };
}

// This method will be called when Electron has finished
// initialization and is ready to create browser windows.
app.whenReady().then(async () => {
  // Start Python backend before creating window
  startPythonBackend();

  // Create system tray
  createTray();

  // Check and request permissions on startup
  const permissions = await checkAndRequestPermissions();
  console.log('Startup permissions:', permissions);

  createWindow();

  app.on('activate', () => {
    // On macOS it's common to re-create a window in the app when the
    // dock icon is clicked and there are no other windows open.
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.show();
      mainWindow.focus();
    } else {
      createWindow();
    }
  });
});

// Quit when all windows are closed, except on macOS.
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  app.isQuitting = true;
  stopPythonBackend();
});

// IPC handlers for renderer process
ipcMain.handle('ping', async () => {
  return 'pong';
});

// Python backend proxy handlers
ipcMain.handle('python:ping', async () => {
  return callPython('ping');
});

ipcMain.handle('python:status', async () => {
  return callPython('get_status');
});

ipcMain.handle('python:ready', async () => {
  return pythonReady;
});

// Generic Python call handler
ipcMain.handle('python:call', async (event, method, params) => {
  return callPython(method, params);
});

// Window control handlers
ipcMain.handle('window:minimize', () => {
  if (mainWindow) mainWindow.minimize();
});

ipcMain.handle('window:maximize', () => {
  if (mainWindow) {
    if (mainWindow.isMaximized()) {
      mainWindow.unmaximize();
    } else {
      mainWindow.maximize();
    }
  }
});

ipcMain.handle('window:close', () => {
  if (mainWindow) mainWindow.close();
});

// Native permission handlers (these run in the Electron main process)
ipcMain.handle('permissions:check', async () => {
  const screenStatus = systemPreferences.getMediaAccessStatus('screen');
  const accessibilityStatus = systemPreferences.isTrustedAccessibilityClient(false);

  console.log('Permission check - Screen:', screenStatus, 'Accessibility:', accessibilityStatus);

  return {
    screen_recording: {
      permission: 'screen_recording',
      status: screenStatus === 'granted' ? 'granted' : 'denied',
      required: true,
      can_request: false, // Screen recording can't be requested programmatically
    },
    accessibility: {
      permission: 'accessibility',
      status: accessibilityStatus ? 'granted' : 'denied',
      required: true,
      can_request: true,
    },
    location: {
      permission: 'location',
      status: 'not_determined', // Will be determined when requested
      required: false,
      can_request: false, // Requires code-signed app
    },
    all_granted: screenStatus === 'granted' && accessibilityStatus,
    requires_restart: false,
  };
});

ipcMain.handle('permissions:requestAccessibility', async () => {
  console.log('Requesting accessibility permission...');
  // This will show the system prompt for accessibility
  const result = systemPreferences.isTrustedAccessibilityClient(true);
  console.log('Accessibility request result:', result);
  return { success: true, granted: result };
});

ipcMain.handle('permissions:requestScreenRecording', async () => {
  // Screen recording can't be requested - open System Settings instead
  await shell.openExternal('x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture');
  return { success: true, opened: true };
});

ipcMain.handle('permissions:requestLocation', async () => {
  // Location permission is requested via the renderer process using navigator.geolocation
  // This handler just returns that the request should be made from renderer
  return { success: true, useRenderer: true };
});

ipcMain.handle('permissions:openSettings', async (event, permission) => {
  const urls = {
    screen_recording: 'x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture',
    accessibility: 'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility',
    location: 'x-apple.systempreferences:com.apple.preference.security?Privacy_LocationServices',
  };

  const url = urls[permission];
  if (url) {
    await shell.openExternal(url);
    return { success: true };
  }
  return { success: false, error: 'Unknown permission' };
});

// Dialog handlers for export
ipcMain.handle('dialog:showSaveDialog', async (event, options) => {
  const result = await dialog.showSaveDialog(mainWindow, options);
  return result;
});

ipcMain.handle('dialog:showOpenDialog', async (event, options) => {
  const result = await dialog.showOpenDialog(mainWindow, options);
  return result;
});

// Create system tray
function createTray() {
  // Create a simple tray icon (16x16 template image for macOS)
  // For production, use actual icon files
  const icon = nativeImage.createEmpty();

  // On macOS, use a template image for proper appearance in both light/dark mode
  // For now, create a simple filled circle icon programmatically
  const size = 16;
  const canvas = Buffer.alloc(size * size * 4);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const dx = x - size / 2;
      const dy = y - size / 2;
      const dist = Math.sqrt(dx * dx + dy * dy);
      const idx = (y * size + x) * 4;
      if (dist < size / 2 - 2) {
        // Inside the circle - white with some transparency
        canvas[idx] = 255;     // R
        canvas[idx + 1] = 255; // G
        canvas[idx + 2] = 255; // B
        canvas[idx + 3] = 200; // A
      } else if (dist < size / 2) {
        // Edge - anti-aliased
        const alpha = Math.max(0, (size / 2 - dist) / 2) * 255;
        canvas[idx] = 255;
        canvas[idx + 1] = 255;
        canvas[idx + 2] = 255;
        canvas[idx + 3] = Math.floor(alpha);
      } else {
        // Outside - transparent
        canvas[idx] = 0;
        canvas[idx + 1] = 0;
        canvas[idx + 2] = 0;
        canvas[idx + 3] = 0;
      }
    }
  }

  const trayIcon = nativeImage.createFromBuffer(canvas, { width: size, height: size });
  trayIcon.setTemplateImage(true); // For macOS menu bar

  tray = new Tray(trayIcon);
  tray.setToolTip('Trace - Digital Activity Tracker');

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Show Trace',
      click: () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        } else {
          createWindow();
        }
      }
    },
    {
      type: 'separator'
    },
    {
      label: 'Backend Status',
      sublabel: pythonReady ? 'Running' : 'Starting...',
      enabled: false
    },
    {
      type: 'separator'
    },
    {
      label: 'Quit Trace',
      click: () => {
        app.quit();
      }
    }
  ]);

  tray.setContextMenu(contextMenu);

  // Click on tray icon shows/hides window
  tray.on('click', () => {
    if (mainWindow) {
      if (mainWindow.isVisible()) {
        mainWindow.hide();
      } else {
        mainWindow.show();
        mainWindow.focus();
      }
    } else {
      createWindow();
    }
  });
}

// Update tray menu when backend status changes
function updateTrayMenu() {
  if (!tray) return;

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Show Trace',
      click: () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        } else {
          createWindow();
        }
      }
    },
    {
      type: 'separator'
    },
    {
      label: 'Backend Status',
      sublabel: pythonReady ? 'Running' : 'Starting...',
      enabled: false
    },
    {
      type: 'separator'
    },
    {
      label: 'Quit Trace',
      click: () => {
        app.quit();
      }
    }
  ]);

  tray.setContextMenu(contextMenu);
}
