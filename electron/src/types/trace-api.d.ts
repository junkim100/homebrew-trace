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

/** Shortcut names */
export type ShortcutName = 'toggleWindow' | 'quickCapture';

/** Shortcut bindings */
export interface ShortcutBindings {
  toggleWindow: string;
  quickCapture: string;
}

/** Shortcut set result */
export interface ShortcutSetResult {
  success: boolean;
  shortcut?: string;
  accelerator?: string;
  error?: string;
}

/** Global shortcuts API */
export interface ShortcutsAPI {
  /** Get current shortcut bindings */
  get(): Promise<ShortcutBindings>;

  /** Set a shortcut binding */
  set(name: ShortcutName, accelerator: string): Promise<ShortcutSetResult>;

  /** Reset shortcuts to defaults */
  reset(): Promise<ShortcutBindings>;

  /** Listen for quick capture shortcut events */
  onQuickCapture(callback: () => void): () => void;
}

/** Tray menu event listeners */
export interface TrayAPI {
  /** Listen for open note events from tray menu */
  onOpenNote(callback: (noteId: string) => void): () => void;

  /** Listen for open graph events from tray menu */
  onOpenGraph(callback: () => void): () => void;

  /** Listen for open settings events from tray menu */
  onOpenSettings(callback: () => void): () => void;
}

/** Graph node for visualization */
export interface GraphNode {
  id: string;
  label: string;
  type: string;
  noteCount: number;
  edgeCount: number;
}

/** Graph edge for visualization */
export interface GraphEdge {
  source: string;
  target: string;
  type: string;
  weight: number;
}

/** Graph data response */
export interface GraphDataResponse {
  success: boolean;
  nodes: GraphNode[];
  edges: GraphEdge[];
  nodeCount: number;
  edgeCount: number;
  error?: string;
}

/** Entity type with count */
export interface EntityTypeCount {
  type: string;
  count: number;
}

/** Entity types response */
export interface EntityTypesResponse {
  success: boolean;
  types: EntityTypeCount[];
  error?: string;
}

/** Related entity in details view */
export interface RelatedEntityInfo {
  id: string;
  direction: 'incoming' | 'outgoing';
  edgeType: string;
  weight: number;
  name: string;
  type: string;
}

/** Note reference in entity details */
export interface EntityNoteRef {
  noteId: string;
  path: string;
  timestamp: string;
  summary: string;
  strength: number;
}

/** Entity details response */
export interface EntityDetailsResponse {
  success: boolean;
  entity?: {
    id: string;
    type: string;
    name: string;
    aliases: string[];
  };
  related?: RelatedEntityInfo[];
  notes?: EntityNoteRef[];
  error?: string;
}

/** Graph data options */
export interface GraphDataOptions {
  daysBack?: number;
  entityTypes?: string[];
  minEdgeWeight?: number;
  limit?: number;
}

/** Graph API methods */
export interface GraphAPI {
  /** Get graph data for visualization */
  getData(options?: GraphDataOptions): Promise<GraphDataResponse>;

  /** Get entity types with counts */
  getEntityTypes(): Promise<EntityTypesResponse>;

  /** Get entity details */
  getEntityDetails(entityId: string): Promise<EntityDetailsResponse>;
}

/** Open loop entry */
export interface OpenLoop {
  loop_id: string;
  description: string;
  source_note_id: string;
  source_note_path: string;
  detected_at: string;
  context: string | null;
  completed: boolean;
}

/** Open loops list response */
export interface OpenLoopsListResponse {
  success: boolean;
  loops: OpenLoop[];
  count: number;
  error?: string;
}

/** Open loops summary response */
export interface OpenLoopsSummaryResponse {
  success: boolean;
  total_count: number;
  today_count: number;
  this_week_count: number;
  days_with_loops: number;
  recent_loops: Array<{
    loop_id: string;
    description: string;
    source_note_id: string;
    detected_at: string;
    context: string | null;
  }>;
  error?: string;
}

/** Open loops list options */
export interface OpenLoopsListOptions {
  daysBack?: number;
  limit?: number;
}

/** Open Loops API methods */
export interface OpenLoopsAPI {
  /** List open loops from recent notes */
  list(options?: OpenLoopsListOptions): Promise<OpenLoopsListResponse>;

  /** Get open loops summary */
  summary(): Promise<OpenLoopsSummaryResponse>;
}

/** Blocklist entry */
export interface BlocklistEntry {
  blocklist_id: string;
  block_type: 'app' | 'domain';
  pattern: string;
  display_name: string | null;
  enabled: boolean;
  block_screenshots: boolean;
  block_events: boolean;
  created_ts: string;
  updated_ts: string;
}

/** Blocklist API response */
export interface BlocklistListResponse {
  success: boolean;
  entries: BlocklistEntry[];
  count: number;
}

/** Blocklist add response */
export interface BlocklistAddResponse {
  success: boolean;
  entry?: BlocklistEntry;
  error?: string;
}

/** Blocklist operation response */
export interface BlocklistOperationResponse {
  success: boolean;
  removed?: boolean;
  updated?: boolean;
  added?: number;
  error?: string;
}

/** Blocklist check response */
export interface BlocklistCheckResponse {
  success: boolean;
  blocked: boolean;
  reason: string | null;
  error?: string;
}

/** Export summary */
export interface ExportSummary {
  success: boolean;
  notes_in_db: number;
  markdown_files: number;
  entities: number;
  edges: number;
  aggregates: number;
  estimated_markdown_size_bytes: number;
  error?: string;
}

/** Export result */
export interface ExportResult {
  success: boolean;
  format?: string;
  notes_count?: number;
  entities_count?: number;
  edges_count?: number;
  export_path?: string;
  export_size_bytes?: number;
  export_time_seconds?: number;
  canceled?: boolean;
  error?: string;
}

/** Export API methods */
export interface ExportAPI {
  /** Get summary of exportable data */
  summary(): Promise<ExportSummary>;

  /** Export to JSON format */
  toJson(outputPath: string): Promise<ExportResult>;

  /** Export to Markdown directory */
  toMarkdown(outputPath: string): Promise<ExportResult>;

  /** Export to ZIP archive */
  toArchive(outputPath: string): Promise<ExportResult>;

  /** Show save dialog and export to archive */
  saveArchive(): Promise<ExportResult>;
}

/** Spotlight indexing status */
export interface SpotlightStatus {
  success: boolean;
  indexed: boolean;
  notes_count: number;
  directory: string;
  excluded?: boolean;
  error?: string;
}

/** Spotlight reindex result */
export interface SpotlightReindexResult {
  success: boolean;
  total: number;
  errors: number;
  error?: string;
}

/** Spotlight index note options */
export interface SpotlightIndexNoteOptions {
  title?: string;
  summary?: string;
  entities?: string[];
}

/** Spotlight API methods */
export interface SpotlightAPI {
  /** Get Spotlight indexing status */
  status(): Promise<SpotlightStatus>;

  /** Reindex all notes for Spotlight */
  reindex(): Promise<SpotlightReindexResult>;

  /** Index a single note for Spotlight */
  indexNote(notePath: string, options?: SpotlightIndexNoteOptions): Promise<{ success: boolean }>;

  /** Trigger Spotlight to reindex using mdimport */
  triggerReindex(): Promise<{ success: boolean }>;
}

/** Blocklist API methods */
export interface BlocklistAPI {
  /** List all blocklist entries */
  list(includeDisabled?: boolean): Promise<BlocklistListResponse>;

  /** Add an app to the blocklist */
  addApp(
    bundleId: string,
    displayName?: string | null,
    blockScreenshots?: boolean,
    blockEvents?: boolean
  ): Promise<BlocklistAddResponse>;

  /** Add a domain to the blocklist */
  addDomain(
    domain: string,
    displayName?: string | null,
    blockScreenshots?: boolean,
    blockEvents?: boolean
  ): Promise<BlocklistAddResponse>;

  /** Remove an entry from the blocklist */
  remove(blocklistId: string): Promise<BlocklistOperationResponse>;

  /** Enable or disable a blocklist entry */
  setEnabled(blocklistId: string, enabled: boolean): Promise<BlocklistOperationResponse>;

  /** Initialize default blocklist entries */
  initDefaults(): Promise<BlocklistOperationResponse>;

  /** Check if an app or URL is blocked */
  check(bundleId?: string | null, url?: string | null): Promise<BlocklistCheckResponse>;
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

  /** Export API */
  export: ExportAPI;

  /** Graph API */
  graph: GraphAPI;

  /** Open Loops API */
  openLoops: OpenLoopsAPI;

  /** Spotlight API */
  spotlight: SpotlightAPI;

  /** Blocklist API */
  blocklist: BlocklistAPI;

  /** Window control */
  window: WindowAPI;

  /** Global shortcuts */
  shortcuts: ShortcutsAPI;

  /** Tray menu events */
  tray: TrayAPI;
}

declare global {
  interface Window {
    traceAPI: TraceAPI;
  }
}
