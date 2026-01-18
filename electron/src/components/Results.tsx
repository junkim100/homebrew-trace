import type { NoteMatch } from '../types/trace-api';

interface ResultsProps {
  notes: NoteMatch[];
  onNoteClick: (noteId: string) => void;
  loading?: boolean;
}

export function Results({ notes, onNoteClick, loading = false }: ResultsProps) {
  if (loading) {
    return (
      <div style={styles.container}>
        <div style={styles.loading}>
          <div style={styles.spinner} />
          <span>Searching...</span>
        </div>
      </div>
    );
  }

  if (notes.length === 0) {
    return (
      <div style={styles.container}>
        <div style={styles.empty}>
          <p style={styles.emptyText}>No results found</p>
          <p style={styles.emptyHint}>Try adjusting your search or time filter</p>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      <h3 style={styles.title}>Related Notes ({notes.length})</h3>
      <div style={styles.list}>
        {notes.map((note) => (
          <button
            key={note.note_id}
            onClick={() => onNoteClick(note.note_id)}
            style={styles.noteCard}
          >
            <div style={styles.noteHeader}>
              <span style={styles.noteTitle}>{note.title || note.note_id}</span>
              <span style={styles.noteScore}>
                {Math.round(note.similarity * 100)}% match
              </span>
            </div>
            <p style={styles.noteSummary}>{note.summary}</p>
            <div style={styles.noteFooter}>
              <span style={styles.noteTimestamp}>
                {formatTimestamp(note.timestamp)}
              </span>
              {note.entities.length > 0 && (
                <div style={styles.entityTags}>
                  {note.entities.slice(0, 3).map((entity, idx) => (
                    <span key={idx} style={styles.entityTag}>
                      {entity.name}
                    </span>
                  ))}
                  {note.entities.length > 3 && (
                    <span style={styles.entityMore}>
                      +{note.entities.length - 3}
                    </span>
                  )}
                </div>
              )}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function formatTimestamp(timestamp: string): string {
  try {
    const date = new Date(timestamp);
    return date.toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  } catch {
    return timestamp;
  }
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    minHeight: 0,
  },
  title: {
    fontSize: '0.875rem',
    fontWeight: 600,
    color: 'var(--text-secondary)',
    marginBottom: '0.75rem',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  list: {
    flex: 1,
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  noteCard: {
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: '8px',
    padding: '0.875rem',
    cursor: 'pointer',
    textAlign: 'left',
    transition: 'border-color 0.2s, background-color 0.2s',
    width: '100%',
  },
  noteHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: '0.5rem',
  },
  noteTitle: {
    fontSize: '0.9rem',
    fontWeight: 500,
    color: 'var(--text-primary)',
  },
  noteScore: {
    fontSize: '0.75rem',
    color: 'var(--accent)',
    fontWeight: 500,
  },
  noteSummary: {
    fontSize: '0.85rem',
    color: 'var(--text-secondary)',
    lineHeight: 1.4,
    marginBottom: '0.5rem',
    display: '-webkit-box',
    WebkitLineClamp: 2,
    WebkitBoxOrient: 'vertical',
    overflow: 'hidden',
  },
  noteFooter: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: '0.5rem',
  },
  noteTimestamp: {
    fontSize: '0.75rem',
    color: 'var(--text-secondary)',
  },
  entityTags: {
    display: 'flex',
    gap: '0.25rem',
    flexWrap: 'wrap',
  },
  entityTag: {
    backgroundColor: 'rgba(0, 122, 255, 0.15)',
    color: 'var(--accent)',
    fontSize: '0.7rem',
    padding: '0.125rem 0.375rem',
    borderRadius: '4px',
  },
  entityMore: {
    fontSize: '0.7rem',
    color: 'var(--text-secondary)',
    padding: '0.125rem 0.25rem',
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
  empty: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '2rem',
    textAlign: 'center',
  },
  emptyText: {
    fontSize: '1rem',
    color: 'var(--text-secondary)',
    marginBottom: '0.5rem',
  },
  emptyHint: {
    fontSize: '0.85rem',
    color: 'var(--text-secondary)',
    opacity: 0.7,
  },
};

export default Results;
