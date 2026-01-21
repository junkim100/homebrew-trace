import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import type { AppSettings, BlocklistEntry } from '../types/trace-api';

interface AllSettings {
  config: {
    appearance: { show_in_dock: boolean; launch_at_login: boolean };
    capture: {
      summarization_interval_minutes: number;
      daily_revision_hour: number;
      blocked_apps: string[];
      blocked_domains: string[];
    };
    notifications: { weekly_digest_enabled: boolean; weekly_digest_day: string };
    shortcuts: { open_trace: string };
    data: { retention_months: number | null };
    api_key: string | null;
  };
  options: {
    summarization_intervals: number[];
    daily_revision_hours: number[];
    weekly_digest_days: string[];
    retention_months: (number | null)[];
  };
  has_api_key: boolean;
  paths: {
    data_dir: string;
    notes_dir: string;
    db_path: string;
    cache_dir: string;
  };
}

export function Settings() {
  const navigate = useNavigate();
  const [settings, setSettings] = useState<AllSettings | null>(null);
  const [apiKey, setApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [loading, setLoading] = useState(true);

  // Blocklist state
  const [blocklistEntries, setBlocklistEntries] = useState<BlocklistEntry[]>([]);
  const [blocklistLoading, setBlocklistLoading] = useState(false);
  const [newBlockType, setNewBlockType] = useState<'app' | 'domain'>('domain');
  const [newBlockPattern, setNewBlockPattern] = useState('');
  const [newBlockName, setNewBlockName] = useState('');

  // Export state
  const [exportLoading, setExportLoading] = useState(false);
  const [exportSummary, setExportSummary] = useState<{
    notes_in_db: number;
    markdown_files: number;
    entities: number;
    edges: number;
  } | null>(null);

  const loadBlocklist = async () => {
    setBlocklistLoading(true);
    try {
      const result = await window.traceAPI.blocklist.list(true);
      if (result.success) {
        setBlocklistEntries(result.entries);
      }
    } catch (err) {
      console.error('Failed to load blocklist:', err);
    } finally {
      setBlocklistLoading(false);
    }
  };

  useEffect(() => {
    const loadSettings = async () => {
      try {
        const result = await window.traceAPI.settings.getAll();
        setSettings(result as AllSettings);
      } catch (err) {
        console.error('Failed to load all settings:', err);
        // Fallback to legacy get
        try {
          const legacyResult = await window.traceAPI.settings.get();
          // Map legacy result to new structure
          setSettings({
            config: {
              appearance: { show_in_dock: true, launch_at_login: false },
              capture: {
                summarization_interval_minutes: 60,
                daily_revision_hour: 3,
                blocked_apps: [],
                blocked_domains: [],
              },
              notifications: { weekly_digest_enabled: true, weekly_digest_day: 'sunday' },
              shortcuts: { open_trace: 'CommandOrControl+Shift+T' },
              data: { retention_months: null },
              api_key: null,
            },
            options: {
              summarization_intervals: [30, 60, 120, 240],
              daily_revision_hours: Array.from({ length: 24 }, (_, i) => i),
              weekly_digest_days: ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'],
              retention_months: [null, 6, 12, 24],
            },
            has_api_key: (legacyResult as AppSettings).has_api_key,
            paths: {
              data_dir: (legacyResult as AppSettings).data_dir,
              notes_dir: (legacyResult as AppSettings).notes_dir,
              db_path: (legacyResult as AppSettings).db_path,
              cache_dir: (legacyResult as AppSettings).cache_dir,
            },
          });
        } catch (fallbackErr) {
          setMessage({ type: 'error', text: 'Failed to load settings' });
        }
      } finally {
        setLoading(false);
      }
    };

    loadSettings();
    loadBlocklist();
    loadExportSummary();
  }, []);

  const loadExportSummary = async () => {
    try {
      const result = await window.traceAPI.export.summary();
      if (result.success) {
        setExportSummary({
          notes_in_db: result.notes_in_db,
          markdown_files: result.markdown_files,
          entities: result.entities,
          edges: result.edges,
        });
      }
    } catch (err) {
      console.error('Failed to load export summary:', err);
    }
  };

  const handleSaveApiKey = async () => {
    if (!apiKey.trim()) return;

    setSaving(true);
    setMessage(null);
    try {
      await window.traceAPI.settings.setApiKey(apiKey.trim());
      setMessage({ type: 'success', text: 'API key saved successfully' });
      setApiKey('');
      // Refresh settings
      const result = await window.traceAPI.settings.getAll();
      setSettings(result as AllSettings);
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to save API key' });
    } finally {
      setSaving(false);
    }
  };

  const handleSettingChange = async (key: string, value: unknown) => {
    try {
      const result = await window.traceAPI.settings.setValue(key, value);
      if (result.success) {
        // Refresh settings
        const updated = await window.traceAPI.settings.getAll();
        setSettings(updated as AllSettings);

        // Apply appearance changes immediately
        if (key === 'appearance.show_in_dock') {
          await window.traceAPI.appearance.setDockVisibility(value as boolean);
        } else if (key === 'appearance.launch_at_login') {
          await window.traceAPI.appearance.setLaunchAtLogin(value as boolean);
        }
      }
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to save setting' });
    }
  };

  const handleAddBlocklistEntry = async () => {
    if (!newBlockPattern.trim()) return;

    try {
      const result = newBlockType === 'app'
        ? await window.traceAPI.blocklist.addApp(newBlockPattern.trim(), newBlockName.trim() || null)
        : await window.traceAPI.blocklist.addDomain(newBlockPattern.trim(), newBlockName.trim() || null);

      if (result.success) {
        setMessage({ type: 'success', text: `Added ${newBlockType} to blocklist` });
        setNewBlockPattern('');
        setNewBlockName('');
        loadBlocklist();
      } else {
        setMessage({ type: 'error', text: result.error || 'Failed to add to blocklist' });
      }
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to add to blocklist' });
    }
  };

  const handleRemoveBlocklistEntry = async (blocklistId: string) => {
    try {
      const result = await window.traceAPI.blocklist.remove(blocklistId);
      if (result.success) {
        loadBlocklist();
      }
    } catch (err) {
      console.error('Failed to remove blocklist entry:', err);
    }
  };

  const handleToggleBlocklistEntry = async (blocklistId: string, enabled: boolean) => {
    try {
      const result = await window.traceAPI.blocklist.setEnabled(blocklistId, enabled);
      if (result.success) {
        loadBlocklist();
      }
    } catch (err) {
      console.error('Failed to toggle blocklist entry:', err);
    }
  };

  const handleInitDefaults = async () => {
    try {
      const result = await window.traceAPI.blocklist.initDefaults();
      if (result.success) {
        setMessage({ type: 'success', text: `Added ${result.added} default blocklist entries` });
        loadBlocklist();
      }
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to initialize defaults' });
    }
  };

  const handleExport = async () => {
    setExportLoading(true);
    setMessage(null);
    try {
      const result = await window.traceAPI.export.saveArchive();
      if (result.canceled) {
        // User cancelled the dialog
        return;
      }
      if (result.success) {
        setMessage({
          type: 'success',
          text: `Exported ${result.notes_count} notes to ${result.export_path}`,
        });
      } else {
        setMessage({ type: 'error', text: result.error || 'Export failed' });
      }
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Export failed' });
    } finally {
      setExportLoading(false);
    }
  };

  const formatHour = (hour: number) => {
    if (hour === 0) return '12:00 AM';
    if (hour === 12) return '12:00 PM';
    if (hour < 12) return `${hour}:00 AM`;
    return `${hour - 12}:00 PM`;
  };

  const formatInterval = (minutes: number) => {
    if (minutes < 60) return `${minutes} minutes`;
    if (minutes === 60) return '1 hour';
    return `${minutes / 60} hours`;
  };

  const formatRetention = (months: number | null) => {
    if (months === null) return 'Forever';
    if (months === 12) return '1 year';
    if (months === 24) return '2 years';
    return `${months} months`;
  };

  if (loading) {
    return (
      <div style={styles.container}>
        <div className="titlebar" />
        <main style={styles.main}>
          <div style={styles.loading}>Loading settings...</div>
        </main>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      <div className="titlebar" />
      <main style={styles.main}>
        <div style={styles.header}>
          <button onClick={() => navigate(-1)} style={styles.backButton}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5" />
              <path d="M12 19l-7-7 7-7" />
            </svg>
            Back
          </button>
          <h1 style={styles.title}>Settings</h1>
        </div>

        {message && (
          <div style={{
            ...styles.message,
            ...(message.type === 'success' ? styles.messageSuccess : styles.messageError),
          }}>
            {message.text}
          </div>
        )}

        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>API Configuration</h2>
          <div style={styles.field}>
            <label style={styles.label}>OpenAI API Key</label>
            <p style={styles.description}>
              Required for generating summaries and answering queries.
              {settings?.has_api_key && (
                <span style={styles.status}> (Currently set)</span>
              )}
            </p>
            <div style={styles.inputRow}>
              <input
                type={showApiKey ? 'text' : 'password'}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={settings?.has_api_key ? '••••••••••••••••' : 'sk-...'}
                style={styles.input}
              />
              <button
                onClick={() => setShowApiKey(!showApiKey)}
                style={styles.toggleButton}
                type="button"
              >
                {showApiKey ? 'Hide' : 'Show'}
              </button>
              <button
                onClick={handleSaveApiKey}
                disabled={!apiKey.trim() || saving}
                style={{
                  ...styles.saveButton,
                  ...(!apiKey.trim() || saving ? styles.saveButtonDisabled : {}),
                }}
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </section>

        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>Appearance</h2>
          <div style={styles.field}>
            <div style={styles.toggleRow}>
              <div>
                <label style={styles.label}>Show in Dock</label>
                <p style={styles.description}>When off, Trace only appears in the menu bar.</p>
              </div>
              <label className="settings-switch" style={styles.switch}>
                <input
                  type="checkbox"
                  checked={settings?.config.appearance.show_in_dock ?? true}
                  onChange={(e) => handleSettingChange('appearance.show_in_dock', e.target.checked)}
                />
                <span style={styles.slider}></span>
              </label>
            </div>
          </div>
          <div style={styles.field}>
            <div style={styles.toggleRow}>
              <div>
                <label style={styles.label}>Launch at Login</label>
                <p style={styles.description}>Start Trace automatically when you log in.</p>
              </div>
              <label className="settings-switch" style={styles.switch}>
                <input
                  type="checkbox"
                  checked={settings?.config.appearance.launch_at_login ?? false}
                  onChange={(e) => handleSettingChange('appearance.launch_at_login', e.target.checked)}
                />
                <span style={styles.slider}></span>
              </label>
            </div>
          </div>
        </section>

        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>Capture & Processing</h2>
          <div style={styles.field}>
            <label style={styles.label}>Summarization Interval</label>
            <p style={styles.description}>How often to generate hourly summary notes.</p>
            <select
              value={settings?.config.capture.summarization_interval_minutes ?? 60}
              onChange={(e) => handleSettingChange('capture.summarization_interval_minutes', Number(e.target.value))}
              style={styles.select}
            >
              {settings?.options.summarization_intervals.map((interval) => (
                <option key={interval} value={interval}>
                  {formatInterval(interval)}
                </option>
              ))}
            </select>
          </div>
          <div style={styles.field}>
            <label style={styles.label}>Daily Revision Time</label>
            <p style={styles.description}>When to run daily processing (revision, cleanup).</p>
            <select
              value={settings?.config.capture.daily_revision_hour ?? 3}
              onChange={(e) => handleSettingChange('capture.daily_revision_hour', Number(e.target.value))}
              style={styles.select}
            >
              {settings?.options.daily_revision_hours.map((hour) => (
                <option key={hour} value={hour}>
                  {formatHour(hour)}
                </option>
              ))}
            </select>
          </div>
        </section>

        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>Notifications</h2>
          <div style={styles.field}>
            <div style={styles.toggleRow}>
              <div>
                <label style={styles.label}>Weekly Digest</label>
                <p style={styles.description}>Receive a weekly summary notification.</p>
              </div>
              <label className="settings-switch" style={styles.switch}>
                <input
                  type="checkbox"
                  checked={settings?.config.notifications.weekly_digest_enabled ?? true}
                  onChange={(e) => handleSettingChange('notifications.weekly_digest_enabled', e.target.checked)}
                />
                <span style={styles.slider}></span>
              </label>
            </div>
          </div>
          {settings?.config.notifications.weekly_digest_enabled && (
            <div style={styles.field}>
              <label style={styles.label}>Digest Day</label>
              <p style={styles.description}>Day of the week to send the weekly digest.</p>
              <select
                value={settings?.config.notifications.weekly_digest_day ?? 'sunday'}
                onChange={(e) => handleSettingChange('notifications.weekly_digest_day', e.target.value)}
                style={styles.select}
              >
                {settings?.options.weekly_digest_days.map((day) => (
                  <option key={day} value={day}>
                    {day.charAt(0).toUpperCase() + day.slice(1)}
                  </option>
                ))}
              </select>
            </div>
          )}
        </section>

        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>Keyboard Shortcuts</h2>
          <div style={styles.field}>
            <label style={styles.label}>Open Trace</label>
            <p style={styles.description}>Global shortcut to show/hide the Trace window.</p>
            <div style={styles.shortcutDisplay}>
              {settings?.config.shortcuts.open_trace?.replace('CommandOrControl', '⌘').replace('+', ' + ') ?? '⌘ + Shift + T'}
            </div>
          </div>
          <div style={styles.field}>
            <label style={styles.label}>Open Settings</label>
            <p style={styles.description}>Open settings from anywhere in the app.</p>
            <div style={styles.shortcutDisplay}>⌘ + ,</div>
          </div>
        </section>

        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>Data Management</h2>
          <div style={styles.field}>
            <label style={styles.label}>Data Retention</label>
            <p style={styles.description}>How long to keep notes and data. Older data will be automatically deleted.</p>
            <select
              value={settings?.config.data.retention_months ?? ''}
              onChange={(e) => handleSettingChange('data.retention_months', e.target.value === '' ? null : Number(e.target.value))}
              style={styles.select}
            >
              {settings?.options.retention_months.map((months) => (
                <option key={months ?? 'forever'} value={months ?? ''}>
                  {formatRetention(months)}
                </option>
              ))}
            </select>
          </div>
        </section>

        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>Data Directories</h2>
          {settings && (
            <>
              <div style={styles.field}>
                <label style={styles.label}>Notes Directory</label>
                <p style={styles.pathValue}>{settings.paths.notes_dir}</p>
              </div>
              <div style={styles.field}>
                <label style={styles.label}>Database Path</label>
                <p style={styles.pathValue}>{settings.paths.db_path}</p>
              </div>
              <div style={styles.field}>
                <label style={styles.label}>Cache Directory</label>
                <p style={styles.pathValue}>{settings.paths.cache_dir}</p>
              </div>
            </>
          )}
        </section>

        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>Privacy Blocklist</h2>
          <p style={styles.description}>
            Block specific apps and websites from being captured.
            Use this to protect sensitive activities like banking, medical, or password managers.
          </p>

          {/* Add new entry form */}
          <div style={styles.blocklistForm}>
            <select
              value={newBlockType}
              onChange={(e) => setNewBlockType(e.target.value as 'app' | 'domain')}
              style={styles.select}
            >
              <option value="domain">Domain</option>
              <option value="app">App</option>
            </select>
            <input
              type="text"
              value={newBlockPattern}
              onChange={(e) => setNewBlockPattern(e.target.value)}
              placeholder={newBlockType === 'domain' ? 'example.com' : 'com.example.app'}
              style={styles.input}
            />
            <input
              type="text"
              value={newBlockName}
              onChange={(e) => setNewBlockName(e.target.value)}
              placeholder="Display name (optional)"
              style={{ ...styles.input, flex: 0.7 }}
            />
            <button
              onClick={handleAddBlocklistEntry}
              disabled={!newBlockPattern.trim()}
              style={{
                ...styles.saveButton,
                ...(!newBlockPattern.trim() ? styles.saveButtonDisabled : {}),
              }}
            >
              Add
            </button>
          </div>

          {/* Initialize defaults button */}
          {blocklistEntries.length === 0 && (
            <button
              onClick={handleInitDefaults}
              style={styles.initDefaultsButton}
            >
              Add Default Blocklist (Banking, Password Managers)
            </button>
          )}

          {/* Blocklist entries */}
          {blocklistLoading ? (
            <div style={styles.loading}>Loading blocklist...</div>
          ) : blocklistEntries.length === 0 ? (
            <p style={styles.emptyState}>No blocked apps or domains yet.</p>
          ) : (
            <div style={styles.blocklistEntries}>
              {blocklistEntries.map((entry) => (
                <div key={entry.blocklist_id} style={styles.blocklistEntry}>
                  <div style={styles.entryInfo}>
                    <span style={styles.entryType}>{entry.block_type}</span>
                    <span style={styles.entryPattern}>
                      {entry.display_name || entry.pattern}
                    </span>
                    {entry.display_name && (
                      <span style={styles.entryPatternSub}>{entry.pattern}</span>
                    )}
                  </div>
                  <div style={styles.entryActions}>
                    <button
                      onClick={() => handleToggleBlocklistEntry(entry.blocklist_id, !entry.enabled)}
                      style={{
                        ...styles.toggleButton,
                        ...(entry.enabled ? styles.toggleEnabled : styles.toggleDisabled),
                      }}
                    >
                      {entry.enabled ? 'Enabled' : 'Disabled'}
                    </button>
                    <button
                      onClick={() => handleRemoveBlocklistEntry(entry.blocklist_id)}
                      style={styles.removeButton}
                    >
                      Remove
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>Export & Backup</h2>
          <p style={styles.description}>
            Export your data as a ZIP archive containing all notes, entities, and relationships.
          </p>

          {exportSummary && (
            <div style={styles.exportSummary}>
              <div style={styles.summaryItem}>
                <span style={styles.summaryLabel}>Notes</span>
                <span style={styles.summaryValue}>{exportSummary.notes_in_db}</span>
              </div>
              <div style={styles.summaryItem}>
                <span style={styles.summaryLabel}>Markdown Files</span>
                <span style={styles.summaryValue}>{exportSummary.markdown_files}</span>
              </div>
              <div style={styles.summaryItem}>
                <span style={styles.summaryLabel}>Entities</span>
                <span style={styles.summaryValue}>{exportSummary.entities}</span>
              </div>
              <div style={styles.summaryItem}>
                <span style={styles.summaryLabel}>Relationships</span>
                <span style={styles.summaryValue}>{exportSummary.edges}</span>
              </div>
            </div>
          )}

          <button
            onClick={handleExport}
            disabled={exportLoading}
            style={{
              ...styles.exportButton,
              ...(exportLoading ? styles.saveButtonDisabled : {}),
            }}
          >
            {exportLoading ? 'Exporting...' : 'Export to ZIP Archive'}
          </button>
        </section>

        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>About</h2>
          <div style={styles.field}>
            <p style={styles.aboutText}>
              Trace is a macOS app that captures your digital activity,
              generates Markdown notes, builds a relationship graph,
              and provides time-aware chat and search.
            </p>
          </div>
        </section>
      </main>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
  },
  main: {
    flex: 1,
    padding: '2rem',
    maxWidth: '600px',
    width: '100%',
    margin: '0 auto',
    overflowY: 'auto',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: '1rem',
    marginBottom: '2rem',
  },
  backButton: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    backgroundColor: 'transparent',
    border: 'none',
    color: 'var(--accent)',
    fontSize: '0.9rem',
    cursor: 'pointer',
    padding: '0.5rem',
    borderRadius: '6px',
  },
  title: {
    fontSize: '1.5rem',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  loading: {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    height: '200px',
    color: 'var(--text-secondary)',
  },
  message: {
    padding: '0.75rem 1rem',
    borderRadius: '8px',
    marginBottom: '1.5rem',
    fontSize: '0.9rem',
  },
  messageSuccess: {
    backgroundColor: 'rgba(52, 199, 89, 0.15)',
    border: '1px solid rgba(52, 199, 89, 0.3)',
    color: '#34c759',
  },
  messageError: {
    backgroundColor: 'rgba(255, 59, 48, 0.15)',
    border: '1px solid rgba(255, 59, 48, 0.3)',
    color: '#ff3b30',
  },
  section: {
    marginBottom: '2rem',
  },
  sectionTitle: {
    fontSize: '0.875rem',
    fontWeight: 600,
    color: 'var(--text-secondary)',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    marginBottom: '1rem',
  },
  field: {
    marginBottom: '1rem',
  },
  label: {
    display: 'block',
    fontSize: '0.95rem',
    fontWeight: 500,
    color: 'var(--text-primary)',
    marginBottom: '0.25rem',
  },
  description: {
    fontSize: '0.85rem',
    color: 'var(--text-secondary)',
    marginBottom: '0.75rem',
  },
  status: {
    color: '#34c759',
    fontWeight: 500,
  },
  inputRow: {
    display: 'flex',
    gap: '0.5rem',
  },
  input: {
    flex: 1,
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '8px',
    padding: '0.625rem 0.875rem',
    fontSize: '0.9rem',
    color: 'var(--text-primary)',
    outline: 'none',
  },
  toggleButton: {
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '8px',
    padding: '0.625rem 0.875rem',
    fontSize: '0.85rem',
    color: 'var(--text-secondary)',
    cursor: 'pointer',
  },
  saveButton: {
    backgroundColor: 'var(--accent)',
    border: 'none',
    borderRadius: '8px',
    padding: '0.625rem 1.25rem',
    fontSize: '0.9rem',
    fontWeight: 500,
    color: 'white',
    cursor: 'pointer',
  },
  saveButtonDisabled: {
    backgroundColor: '#404040',
    cursor: 'not-allowed',
    opacity: 0.5,
  },
  pathValue: {
    fontFamily: 'ui-monospace, SFMono-Regular, SF Mono, Menlo, monospace',
    fontSize: '0.85rem',
    color: 'var(--text-secondary)',
    backgroundColor: 'var(--bg-secondary)',
    padding: '0.5rem 0.75rem',
    borderRadius: '6px',
    wordBreak: 'break-all',
  },
  aboutText: {
    fontSize: '0.9rem',
    color: 'var(--text-secondary)',
    lineHeight: 1.6,
  },
  // Toggle switch styles
  toggleRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: '1rem',
  },
  switch: {
    position: 'relative',
    display: 'inline-block',
    width: '44px',
    height: '24px',
    flexShrink: 0,
  },
  slider: {
    position: 'absolute',
    cursor: 'pointer',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    transition: '.2s',
    borderRadius: '24px',
  },
  // Select styles
  select: {
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '8px',
    padding: '0.625rem 0.875rem',
    fontSize: '0.9rem',
    color: 'var(--text-primary)',
    outline: 'none',
    cursor: 'pointer',
    minWidth: '200px',
    WebkitAppearance: 'menulist',
  },
  // Shortcut display
  shortcutDisplay: {
    display: 'inline-block',
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '6px',
    padding: '0.5rem 0.75rem',
    fontSize: '0.9rem',
    fontFamily: 'ui-monospace, SFMono-Regular, SF Mono, Menlo, monospace',
    color: 'var(--text-primary)',
  },
  // Blocklist styles
  blocklistForm: {
    display: 'flex',
    gap: '0.5rem',
    marginBottom: '1rem',
    flexWrap: 'wrap',
  },
  initDefaultsButton: {
    backgroundColor: 'transparent',
    border: '1px solid var(--border)',
    borderRadius: '8px',
    padding: '0.625rem 1rem',
    fontSize: '0.85rem',
    color: 'var(--text-secondary)',
    cursor: 'pointer',
    marginBottom: '1rem',
  },
  emptyState: {
    fontSize: '0.85rem',
    color: 'var(--text-secondary)',
    fontStyle: 'italic',
  },
  blocklistEntries: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  blocklistEntry: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '8px',
    padding: '0.75rem 1rem',
  },
  entryInfo: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    flexWrap: 'wrap',
    flex: 1,
  },
  entryType: {
    fontSize: '0.7rem',
    fontWeight: 600,
    textTransform: 'uppercase',
    backgroundColor: 'var(--accent)',
    color: 'white',
    padding: '0.2rem 0.5rem',
    borderRadius: '4px',
  },
  entryPattern: {
    fontSize: '0.9rem',
    color: 'var(--text-primary)',
    fontWeight: 500,
  },
  entryPatternSub: {
    fontSize: '0.8rem',
    color: 'var(--text-secondary)',
    fontFamily: 'ui-monospace, SFMono-Regular, SF Mono, Menlo, monospace',
  },
  entryActions: {
    display: 'flex',
    gap: '0.5rem',
  },
  toggleEnabled: {
    backgroundColor: 'rgba(52, 199, 89, 0.15)',
    border: '1px solid rgba(52, 199, 89, 0.3)',
    color: '#34c759',
  },
  toggleDisabled: {
    backgroundColor: 'rgba(142, 142, 147, 0.15)',
    border: '1px solid rgba(142, 142, 147, 0.3)',
    color: '#8e8e93',
  },
  removeButton: {
    backgroundColor: 'transparent',
    border: '1px solid rgba(255, 59, 48, 0.3)',
    borderRadius: '6px',
    padding: '0.4rem 0.75rem',
    fontSize: '0.8rem',
    color: '#ff3b30',
    cursor: 'pointer',
  },
  // Export styles
  exportSummary: {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, 1fr)',
    gap: '0.75rem',
    marginBottom: '1rem',
  },
  summaryItem: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '8px',
    padding: '0.75rem 1rem',
  },
  summaryLabel: {
    fontSize: '0.85rem',
    color: 'var(--text-secondary)',
  },
  summaryValue: {
    fontSize: '1rem',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  exportButton: {
    backgroundColor: 'var(--accent)',
    border: 'none',
    borderRadius: '8px',
    padding: '0.75rem 1.5rem',
    fontSize: '0.9rem',
    fontWeight: 500,
    color: 'white',
    cursor: 'pointer',
    width: '100%',
  },
};

// Add global CSS for switch styling (checkboxes)
const styleTag = document.createElement('style');
styleTag.textContent = `
  .settings-switch input {
    opacity: 0;
    width: 0;
    height: 0;
  }
  .settings-switch input:checked + span {
    background-color: var(--accent);
  }
  .settings-switch span:before {
    position: absolute;
    content: "";
    height: 18px;
    width: 18px;
    left: 2px;
    bottom: 2px;
    background-color: white;
    transition: .2s;
    border-radius: 50%;
  }
  .settings-switch input:checked + span:before {
    transform: translateX(20px);
  }
`;
if (!document.head.querySelector('style[data-settings]')) {
  styleTag.setAttribute('data-settings', 'true');
  document.head.appendChild(styleTag);
}

export default Settings;
