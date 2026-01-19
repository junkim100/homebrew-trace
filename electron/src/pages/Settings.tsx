import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import type { AppSettings } from '../types/trace-api';

export function Settings() {
  const navigate = useNavigate();
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [apiKey, setApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [loading, setLoading] = useState(true);

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
  }, []);

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
};

export default Settings;
