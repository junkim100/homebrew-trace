import { useState, useEffect } from 'react';
import type { OpenLoop } from '../types/trace-api';

interface OpenLoopsProps {
  /** Called when user clicks on a loop to view its source note */
  onViewNote?: (noteId: string, notePath: string) => void;
  /** Maximum number of loops to show */
  maxItems?: number;
  /** Whether to show in compact mode */
  compact?: boolean;
}

export function OpenLoops({ onViewNote, maxItems = 10, compact = false }: OpenLoopsProps) {
  const [loops, setLoops] = useState<OpenLoop[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [daysBack, setDaysBack] = useState(7);

  const loadLoops = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await window.traceAPI.openLoops.list({
        daysBack,
        limit: maxItems,
      });
      if (result.success) {
        setLoops(result.loops);
      } else {
        setError(result.error || 'Failed to load open loops');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load open loops');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLoops();
  }, [daysBack, maxItems]);

  const formatDate = (isoString: string) => {
    const date = new Date(isoString);
    const now = new Date();
    const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));

    if (diffDays === 0) {
      return `Today at ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    } else if (diffDays === 1) {
      return `Yesterday at ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    } else if (diffDays < 7) {
      return `${diffDays} days ago`;
    } else {
      return date.toLocaleDateString();
    }
  };

  if (loading) {
    return (
      <div style={styles.container}>
        <div style={styles.header}>
          <h3 style={styles.title}>Open Loops</h3>
        </div>
        <div style={styles.loading}>Loading...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={styles.container}>
        <div style={styles.header}>
          <h3 style={styles.title}>Open Loops</h3>
        </div>
        <div style={styles.error}>{error}</div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h3 style={styles.title}>Open Loops</h3>
        {!compact && (
          <select
            value={daysBack}
            onChange={(e) => setDaysBack(parseInt(e.target.value))}
            style={styles.select}
          >
            <option value={3}>Last 3 days</option>
            <option value={7}>Last 7 days</option>
            <option value={14}>Last 14 days</option>
            <option value={30}>Last 30 days</option>
          </select>
        )}
      </div>

      {loops.length === 0 ? (
        <div style={styles.emptyState}>
          <p style={styles.emptyText}>No open loops found.</p>
          <p style={styles.emptySubtext}>
            Open loops are incomplete tasks or follow-ups detected in your notes.
          </p>
        </div>
      ) : (
        <div style={styles.loopsList}>
          {loops.map((loop) => (
            <div
              key={loop.loop_id}
              style={styles.loopItem}
              onClick={() => onViewNote?.(loop.source_note_id, loop.source_note_path)}
            >
              <div style={styles.loopContent}>
                <div style={styles.loopIcon}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="10" />
                  </svg>
                </div>
                <div style={styles.loopText}>
                  <span style={styles.loopDescription}>{loop.description}</span>
                  {!compact && loop.context && (
                    <span style={styles.loopContext}>{loop.context}</span>
                  )}
                </div>
              </div>
              <div style={styles.loopMeta}>
                <span style={styles.loopDate}>{formatDate(loop.detected_at)}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {!compact && loops.length > 0 && (
        <div style={styles.footer}>
          <span style={styles.footerText}>
            {loops.length} open loop{loops.length !== 1 ? 's' : ''} found
          </span>
        </div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    backgroundColor: 'var(--bg-secondary)',
    borderRadius: '12px',
    border: '1px solid var(--border)',
    overflow: 'hidden',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '0.75rem 1rem',
    borderBottom: '1px solid var(--border)',
  },
  title: {
    fontSize: '0.9rem',
    fontWeight: 600,
    color: 'var(--text-primary)',
    margin: 0,
  },
  select: {
    backgroundColor: 'var(--bg-tertiary)',
    border: '1px solid var(--border)',
    borderRadius: '6px',
    padding: '0.375rem 0.625rem',
    fontSize: '0.8rem',
    color: 'var(--text-secondary)',
    cursor: 'pointer',
    outline: 'none',
  },
  loading: {
    padding: '2rem',
    textAlign: 'center',
    color: 'var(--text-secondary)',
    fontSize: '0.85rem',
  },
  error: {
    padding: '1rem',
    textAlign: 'center',
    color: '#ff3b30',
    fontSize: '0.85rem',
  },
  emptyState: {
    padding: '2rem 1rem',
    textAlign: 'center',
  },
  emptyText: {
    fontSize: '0.9rem',
    color: 'var(--text-secondary)',
    marginBottom: '0.5rem',
  },
  emptySubtext: {
    fontSize: '0.8rem',
    color: 'var(--text-tertiary)',
  },
  loopsList: {
    display: 'flex',
    flexDirection: 'column',
  },
  loopItem: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    padding: '0.75rem 1rem',
    borderBottom: '1px solid var(--border)',
    cursor: 'pointer',
    transition: 'background-color 0.15s',
  },
  loopContent: {
    display: 'flex',
    gap: '0.75rem',
    flex: 1,
    minWidth: 0,
  },
  loopIcon: {
    color: 'var(--accent)',
    flexShrink: 0,
    marginTop: '0.125rem',
  },
  loopText: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.25rem',
    flex: 1,
    minWidth: 0,
  },
  loopDescription: {
    fontSize: '0.9rem',
    color: 'var(--text-primary)',
    lineHeight: 1.4,
  },
  loopContext: {
    fontSize: '0.8rem',
    color: 'var(--text-tertiary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  loopMeta: {
    display: 'flex',
    alignItems: 'center',
    flexShrink: 0,
    marginLeft: '0.75rem',
  },
  loopDate: {
    fontSize: '0.75rem',
    color: 'var(--text-tertiary)',
    whiteSpace: 'nowrap',
  },
  footer: {
    padding: '0.625rem 1rem',
    borderTop: '1px solid var(--border)',
  },
  footerText: {
    fontSize: '0.75rem',
    color: 'var(--text-tertiary)',
  },
};

export default OpenLoops;
