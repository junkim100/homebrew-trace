import type { ChatResponse } from '../types/trace-api';

interface AnswerProps {
  response: ChatResponse | null;
  loading?: boolean;
  error?: string | null;
  onCitationClick?: (noteId: string) => void;
}

export function Answer({ response, loading = false, error = null, onCitationClick }: AnswerProps) {
  if (loading) {
    return (
      <div style={styles.container}>
        <div style={styles.loading}>
          <div style={styles.spinner} />
          <span>Thinking...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={styles.container}>
        <div style={styles.error}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 8v4" />
            <path d="M12 16h.01" />
          </svg>
          <span>{error}</span>
        </div>
      </div>
    );
  }

  if (!response) {
    return (
      <div style={styles.container}>
        <div style={styles.placeholder}>
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ opacity: 0.3 }}>
            <circle cx="11" cy="11" r="8" />
            <path d="M21 21l-4.35-4.35" />
          </svg>
          <p style={styles.placeholderText}>Ask a question about your activity</p>
          <div style={styles.suggestions}>
            <span style={styles.suggestionLabel}>Try:</span>
            <span style={styles.suggestion}>&ldquo;What did I work on today?&rdquo;</span>
            <span style={styles.suggestion}>&ldquo;What were my most used apps this week?&rdquo;</span>
            <span style={styles.suggestion}>&ldquo;Tell me about Python&rdquo;</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      <div style={styles.answer}>
        <p style={styles.answerText}>{response.answer}</p>

        {response.citations.length > 0 && (
          <div style={styles.citations}>
            <span style={styles.citationsLabel}>Sources:</span>
            <div style={styles.citationsList}>
              {response.citations.map((citation, idx) => (
                <button
                  key={idx}
                  onClick={() => onCitationClick?.(citation.note_id)}
                  style={styles.citationButton}
                  title={citation.quote}
                >
                  [{idx + 1}] {citation.note_id}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div style={styles.meta}>
        {response.time_filter && (
          <span style={styles.metaItem}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 6v6l4 2" />
            </svg>
            {response.time_filter.description}
          </span>
        )}
        <span style={styles.metaItem}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
            <polyline points="22 4 12 14.01 9 11.01" />
          </svg>
          {Math.round(response.confidence * 100)}% confident
        </span>
        <span style={styles.metaItem}>
          {response.processing_time_ms.toFixed(0)}ms
        </span>
      </div>

      {response.aggregates.length > 0 && (
        <div style={styles.aggregates}>
          <h4 style={styles.aggregatesTitle}>Top Activity</h4>
          <div style={styles.aggregatesList}>
            {response.aggregates.slice(0, 5).map((agg, idx) => (
              <div key={idx} style={styles.aggregateItem}>
                <span style={styles.aggregateKey}>{agg.key}</span>
                <span style={styles.aggregateValue}>
                  {formatValue(agg.value, agg.key_type)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function formatValue(value: number, _keyType: string): string {
  // Value is typically in minutes
  if (value >= 60) {
    const hours = Math.floor(value / 60);
    const mins = Math.round(value % 60);
    return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
  }
  return `${Math.round(value)}m`;
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    minHeight: 0,
  },
  loading: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    padding: '1.5rem',
    color: 'var(--text-secondary)',
  },
  spinner: {
    width: '20px',
    height: '20px',
    border: '2px solid var(--border)',
    borderTopColor: 'var(--accent)',
    borderRadius: '50%',
    animation: 'spin 1s linear infinite',
  },
  error: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    padding: '1rem',
    backgroundColor: 'rgba(255, 59, 48, 0.1)',
    border: '1px solid rgba(255, 59, 48, 0.3)',
    borderRadius: '8px',
    color: '#ff3b30',
  },
  placeholder: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '2rem',
    textAlign: 'center',
  },
  placeholderText: {
    fontSize: '1.1rem',
    color: 'var(--text-secondary)',
    marginTop: '1rem',
  },
  suggestions: {
    marginTop: '1.5rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
    alignItems: 'center',
  },
  suggestionLabel: {
    fontSize: '0.85rem',
    color: 'var(--text-secondary)',
    marginBottom: '0.5rem',
  },
  suggestion: {
    fontSize: '0.85rem',
    color: 'var(--accent)',
    opacity: 0.8,
  },
  answer: {
    padding: '1.5rem',
    backgroundColor: 'var(--bg-secondary)',
    borderRadius: '12px',
    border: '1px solid var(--border)',
    marginBottom: '1rem',
  },
  answerText: {
    fontSize: '1rem',
    lineHeight: 1.6,
    color: 'var(--text-primary)',
    whiteSpace: 'pre-wrap',
  },
  citations: {
    marginTop: '1rem',
    paddingTop: '1rem',
    borderTop: '1px solid var(--border)',
  },
  citationsLabel: {
    fontSize: '0.75rem',
    color: 'var(--text-secondary)',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  citationsList: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '0.5rem',
    marginTop: '0.5rem',
  },
  citationButton: {
    backgroundColor: 'rgba(0, 122, 255, 0.1)',
    border: '1px solid rgba(0, 122, 255, 0.2)',
    borderRadius: '4px',
    padding: '0.25rem 0.5rem',
    fontSize: '0.75rem',
    color: 'var(--accent)',
    cursor: 'pointer',
    transition: 'background-color 0.2s',
  },
  meta: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '1rem',
    marginBottom: '1rem',
  },
  metaItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.375rem',
    fontSize: '0.8rem',
    color: 'var(--text-secondary)',
  },
  aggregates: {
    backgroundColor: 'var(--bg-secondary)',
    borderRadius: '8px',
    border: '1px solid var(--border)',
    padding: '1rem',
  },
  aggregatesTitle: {
    fontSize: '0.75rem',
    fontWeight: 600,
    color: 'var(--text-secondary)',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    marginBottom: '0.75rem',
  },
  aggregatesList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  aggregateItem: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '0.375rem 0',
  },
  aggregateKey: {
    fontSize: '0.85rem',
    color: 'var(--text-primary)',
  },
  aggregateValue: {
    fontSize: '0.85rem',
    color: 'var(--accent)',
    fontWeight: 500,
  },
};

export default Answer;
