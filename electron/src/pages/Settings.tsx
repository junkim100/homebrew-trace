import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import type { AppSettings, BlocklistEntry } from '../types/trace-api';

export function Settings() {
  const navigate = useNavigate();
  const [settings, setSettings] = useState<AppSettings | null>(null);
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
        const result = await window.traceAPI.settings.get();
        setSettings(result);
      } catch (err) {
        setMessage({ type: 'error', text: 'Failed to load settings' });
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
      const result = await window.traceAPI.settings.get();
      setSettings(result);
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to save API key' });
    } finally {
      setSaving(false);
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
          <h2 style={styles.sectionTitle}>Data Directories</h2>
          {settings && (
            <>
              <div style={styles.field}>
                <label style={styles.label}>Notes Directory</label>
                <p style={styles.pathValue}>{settings.notes_dir}</p>
              </div>
              <div style={styles.field}>
                <label style={styles.label}>Database Path</label>
                <p style={styles.pathValue}>{settings.db_path}</p>
              </div>
              <div style={styles.field}>
                <label style={styles.label}>Cache Directory</label>
                <p style={styles.pathValue}>{settings.cache_dir}</p>
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
  // Blocklist styles
  blocklistForm: {
    display: 'flex',
    gap: '0.5rem',
    marginBottom: '1rem',
    flexWrap: 'wrap',
  },
  select: {
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '8px',
    padding: '0.625rem 0.875rem',
    fontSize: '0.9rem',
    color: 'var(--text-primary)',
    outline: 'none',
    cursor: 'pointer',
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

export default Settings;
