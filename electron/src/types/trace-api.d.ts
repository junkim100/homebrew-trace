/**
 * Type definitions for the Trace API exposed by preload.js
 */

export interface BackendStatus {
  version: string;
  running: boolean;
  uptime_seconds: number;
  python_version: string;
}

export interface PythonAPI {
  /** Check if Python backend is ready */
  isReady(): Promise<boolean>;

  /** Ping the Python backend */
  ping(): Promise<string>;

  /** Get Python backend status */
  getStatus(): Promise<BackendStatus>;

  /** Generic call to Python backend */
  call<T = unknown>(method: string, params?: Record<string, unknown>): Promise<T>;
}

/** Permission types */
export type PermissionType = 'screen_recording' | 'accessibility' | 'location';

/** Permission status */
export type PermissionStatusType = 'granted' | 'denied' | 'not_determined' | 'restricted';

/** State of a single permission */
export interface PermissionState {
  permission: PermissionType;
  status: PermissionStatusType;
  required: boolean;
  can_request: boolean;
}

/** State of all permissions */
export interface AllPermissionsState {
  screen_recording: PermissionState;
  accessibility: PermissionState;
  location: PermissionState;
  all_granted: boolean;
  requires_restart: boolean;
}

/** Instructions for granting a permission */
export interface PermissionInstructions {
  title: string;
  description: string;
  steps: string[];
  system_preferences_url: string;
  requires_restart: boolean;
}

/** Permission API methods */
export interface PermissionsAPI {
  /** Check all permissions */
  checkAll(): Promise<AllPermissionsState>;

  /** Check a specific permission */
  check(permission: PermissionType): Promise<PermissionState>;

  /** Get instructions for granting a permission */
  getInstructions(permission: PermissionType): Promise<PermissionInstructions>;

  /** Open system settings for a permission */
  openSettings(permission: PermissionType): Promise<{ success: boolean }>;

  /** Request accessibility permission (triggers system prompt) */
  requestAccessibility(): Promise<{ success: boolean }>;

  /** Request location permission (triggers system prompt) */
  requestLocation(): Promise<{ success: boolean }>;
}

export interface TraceAPI {
  /** Ping the Electron main process */
  ping(): Promise<string>;

  /** Current platform (darwin, win32, linux) */
  platform: string;

  /** Python backend methods */
  python: PythonAPI;

  /** Permission management */
  permissions: PermissionsAPI;
}

declare global {
  interface Window {
    traceAPI: TraceAPI;
  }
}
