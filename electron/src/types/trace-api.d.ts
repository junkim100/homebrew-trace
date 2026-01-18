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

/** Citation from a note */
export interface Citation {
  note_id: string;
  note_path: string;
  quote: string;
  timestamp: string;
}

/** Note match from search */
export interface NoteMatch {
  note_id: string;
  path: string;
  title: string;
  timestamp: string;
  similarity: number;
  summary: string;
  entities: Array<{ name: string; type: string }>;
}

/** Related entity from graph expansion */
export interface RelatedEntity {
  entity_id: string;
  entity_type: string;
  canonical_name: string;
  edge_type: string;
  weight: number;
  source_entity_id: string;
  source_entity_name: string;
  direction: 'to' | 'from';
}

/** Aggregate item (e.g., most used app) */
export interface AggregateItem {
  key: string;
  key_type: string;
  value: number;
  period_type: string;
  period_start: string;
  period_end: string;
}

/** Time filter parsed from query */
export interface TimeFilter {
  start: string;
  end: string;
  description: string;
}

/** Chat response */
export interface ChatResponse {
  answer: string;
  citations: Citation[];
  notes: NoteMatch[];
  time_filter: TimeFilter | null;
  related_entities: RelatedEntity[];
  aggregates: AggregateItem[];
  query_type: string;
  confidence: number;
  processing_time_ms: number;
}

/** Chat query options */
export interface ChatQueryOptions {
  timeFilter?: string;
  includeGraphExpansion?: boolean;
  includeAggregates?: boolean;
  maxResults?: number;
}

/** Chat API methods */
export interface ChatAPI {
  /** Send a query and get a response */
  query(query: string, options?: ChatQueryOptions): Promise<ChatResponse>;
}

/** Note listing item */
export interface NoteListItem {
  note_id: string;
  type: 'hourly' | 'daily';
  path: string;
  date: string;
}

/** Note content */
export interface NoteContent {
  content: string;
  path: string;
}

/** Notes list options */
export interface NotesListOptions {
  startDate?: string;
  endDate?: string;
  limit?: number;
}

/** Notes API methods */
export interface NotesAPI {
  /** Read a specific note by ID */
  read(noteId: string): Promise<NoteContent>;

  /** List available notes */
  list(options?: NotesListOptions): Promise<{ notes: NoteListItem[] }>;
}

/** Application settings */
export interface AppSettings {
  data_dir: string;
  notes_dir: string;
  db_path: string;
  cache_dir: string;
  has_api_key: boolean;
}

/** Settings API methods */
export interface SettingsAPI {
  /** Get current settings */
  get(): Promise<AppSettings>;

  /** Set API key */
  setApiKey(apiKey: string): Promise<{ success: boolean }>;
}

/** Window control methods */
export interface WindowAPI {
  /** Minimize window */
  minimize(): Promise<void>;

  /** Maximize/unmaximize window */
  maximize(): Promise<void>;

  /** Close window */
  close(): Promise<void>;
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

  /** Chat/query API */
  chat: ChatAPI;

  /** Notes API */
  notes: NotesAPI;

  /** Settings API */
  settings: SettingsAPI;

  /** Window control */
  window: WindowAPI;
}

declare global {
  interface Window {
    traceAPI: TraceAPI;
  }
}
