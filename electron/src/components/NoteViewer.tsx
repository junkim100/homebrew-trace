import { useState, useEffect } from 'react';

interface NoteViewerProps {
  noteId: string | null;
  onClose: () => void;
}

interface NoteData {
  content: string;
  path: string;
}

export function NoteViewer({ noteId, onClose }: NoteViewerProps) {
  const [note, setNote] = useState<NoteData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!noteId) {
      setNote(null);
      return;
    }

    const loadNote = async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await window.traceAPI.notes.read(noteId);
        setNote(result);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load note');
      } finally {
        setLoading(false);
      }
    };

    loadNote();
  }, [noteId]);

  if (!noteId) {
    return null;
  }

  return (
    <div style={styles.overlay} onClick={onClose}>
      <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div style={styles.header}>
          <h2 style={styles.title}>{noteId}</h2>
          <button onClick={onClose} style={styles.closeButton}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18" />
              <path d="M6 6L18 18" />
            </svg>
          </button>
        </div>
        <div style={styles.content}>
          {loading && (
            <div style={styles.loading}>
              <div style={styles.spinner} />
              <span>Loading note...</span>
            </div>
          )}
          {error && (
            <div style={styles.error}>
              <p>{error}</p>
            </div>
          )}
          {note && !loading && (
            <div style={styles.markdown}>
              <pre style={styles.pre}>{note.content}</pre>
            </div>
          )}
        </div>
        {note && (
          <div style={styles.footer}>
            <span style={styles.path}>{note.path}</span>
          </div>
        )}
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  overlay: {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.7)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
    padding: '2rem',
  },
  modal: {
    backgroundColor: 'var(--bg-primary)',
    borderRadius: '12px',
    border: '1px solid var(--border)',
    width: '100%',
    maxWidth: '800px',
    maxHeight: '80vh',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '1rem 1.5rem',
    borderBottom: '1px solid var(--border)',
  },
  title: {
    fontSize: '1rem',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  closeButton: {
    backgroundColor: 'transparent',
    border: 'none',
    cursor: 'pointer',
    color: 'var(--text-secondary)',
    padding: '0.25rem',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: '4px',
  },
  content: {
    flex: 1,
    overflow: 'auto',
    padding: '1.5rem',
    minHeight: '200px',
  },
  loading: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '1rem',
    padding: '2rem',
    color: 'var(--text-secondary)',
  },
  spinner: {
    width: '24px',
    height: '24px',
    border: '2px solid var(--border)',
    borderTopColor: 'var(--accent)',
    borderRadius: '50%',
    animation: 'spin 1s linear infinite',
  },
  error: {
    backgroundColor: 'rgba(255, 59, 48, 0.1)',
    border: '1px solid rgba(255, 59, 48, 0.3)',
    borderRadius: '8px',
    padding: '1rem',
    color: '#ff3b30',
  },
  markdown: {
    color: 'var(--text-primary)',
    lineHeight: 1.6,
  },
  pre: {
    fontFamily: 'ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, Liberation Mono, monospace',
    fontSize: '0.85rem',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
    margin: 0,
    color: 'var(--text-primary)',
  },
  footer: {
    padding: '0.75rem 1.5rem',
    borderTop: '1px solid var(--border)',
    backgroundColor: 'var(--bg-secondary)',
  },
  path: {
    fontSize: '0.75rem',
    color: 'var(--text-secondary)',
    fontFamily: 'ui-monospace, SFMono-Regular, SF Mono, Menlo, monospace',
  },
};

export default NoteViewer;
