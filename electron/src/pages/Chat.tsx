import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChatInput } from '../components/ChatInput';
import { TimeFilter, TimePreset, getTimeFilterHint } from '../components/TimeFilter';
import { Results } from '../components/Results';
import { Answer } from '../components/Answer';
import { NoteViewer } from '../components/NoteViewer';
import { OpenLoops } from '../components/OpenLoops';
import type { ChatResponse } from '../types/trace-api';

export function Chat() {
  const navigate = useNavigate();
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [timePreset, setTimePreset] = useState<TimePreset>('all');
  const [customStart, setCustomStart] = useState<string>();
  const [customEnd, setCustomEnd] = useState<string>();
  const [selectedNoteId, setSelectedNoteId] = useState<string | null>(null);

  const handleQuery = useCallback(async (query: string) => {
    setLoading(true);
    setError(null);

    try {
      const timeFilter = getTimeFilterHint(timePreset, customStart, customEnd);
      const result = await window.traceAPI.chat.query(query, {
        timeFilter,
        includeGraphExpansion: true,
        includeAggregates: true,
        maxResults: 10,
      });
      setResponse(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
      setResponse(null);
    } finally {
      setLoading(false);
    }
  }, [timePreset, customStart, customEnd]);

  const handleTimeFilterChange = useCallback((
    preset: TimePreset,
    start?: string,
    end?: string
  ) => {
    setTimePreset(preset);
    setCustomStart(start);
    setCustomEnd(end);
  }, []);

  return (
    <div style={styles.container}>
      {/* Titlebar area for dragging - leaves space for traffic lights */}
      <div className="titlebar" style={styles.titlebar}>
        <div style={styles.titlebarSpacer} />
        <button
          onClick={() => navigate('/dashboard')}
          style={styles.settingsButton}
          title="Activity Dashboard"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="7" height="7" />
            <rect x="14" y="3" width="7" height="7" />
            <rect x="3" y="14" width="7" height="7" />
            <rect x="14" y="14" width="7" height="7" />
          </svg>
        </button>
        <button
          onClick={() => navigate('/graph')}
          style={styles.settingsButton}
          title="Knowledge Graph"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="6" cy="6" r="3" />
            <circle cx="18" cy="6" r="3" />
            <circle cx="6" cy="18" r="3" />
            <circle cx="18" cy="18" r="3" />
            <line x1="8.5" y1="7.5" x2="15.5" y2="16.5" />
            <line x1="15.5" y1="7.5" x2="8.5" y2="16.5" />
          </svg>
        </button>
        <button
          onClick={() => navigate('/settings')}
          style={styles.settingsButton}
          title="Settings"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
        </button>
      </div>

      <main style={styles.main}>
        <div style={styles.sidebar}>
          <div style={styles.filterSection}>
            <h3 style={styles.sectionTitle}>Time Range</h3>
            <TimeFilter
              value={timePreset}
              customStart={customStart}
              customEnd={customEnd}
              onChange={handleTimeFilterChange}
            />
          </div>

          <div style={styles.openLoopsSection}>
            <OpenLoops
              onViewNote={(noteId) => setSelectedNoteId(noteId)}
              maxItems={5}
              compact
            />
          </div>

          <div style={styles.resultsSection}>
            <Results
              notes={response?.notes || []}
              onNoteClick={setSelectedNoteId}
              loading={loading}
            />
          </div>

          {/* Logo at bottom of sidebar */}
          <div style={styles.sidebarFooter}>
            <span style={styles.logoText}>TRACE</span>
          </div>
        </div>

        <div style={styles.content}>
          <div style={styles.answerArea}>
            <Answer
              response={response}
              loading={loading}
              error={error}
              onCitationClick={setSelectedNoteId}
            />
          </div>
          <ChatInput
            onSubmit={handleQuery}
            disabled={loading}
            placeholder="Ask about your activity..."
          />
        </div>
      </main>

      <NoteViewer
        noteId={selectedNoteId}
        onClose={() => setSelectedNoteId(null)}
      />
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    height: '100vh',
  },
  titlebar: {
    display: 'flex',
    justifyContent: 'flex-end',
    alignItems: 'center',
    padding: '0 1rem',
  },
  titlebarSpacer: {
    flex: 1,
  },
  logoText: {
    fontSize: '1.25rem',
    fontWeight: 700,
    letterSpacing: '0.15em',
    background: 'linear-gradient(135deg, #00d4ff 0%, #7b68ee 50%, #ff6b9d 100%)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    backgroundClip: 'text',
  },
  sidebarFooter: {
    flexShrink: 0,
    paddingTop: '1rem',
    borderTop: '1px solid var(--border)',
  },
  settingsButton: {
    backgroundColor: 'transparent',
    border: 'none',
    cursor: 'pointer',
    color: 'var(--text-secondary)',
    padding: '0.5rem',
    borderRadius: '6px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  main: {
    flex: 1,
    display: 'flex',
    overflow: 'hidden',
  },
  sidebar: {
    width: '320px',
    borderRight: '1px solid var(--border)',
    display: 'flex',
    flexDirection: 'column',
    padding: '1rem',
    gap: '1rem',
  },
  filterSection: {
    flexShrink: 0,
  },
  openLoopsSection: {
    flexShrink: 0,
  },
  sectionTitle: {
    fontSize: '0.75rem',
    fontWeight: 600,
    color: 'var(--text-secondary)',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    marginBottom: '0.75rem',
  },
  resultsSection: {
    flex: 1,
    minHeight: 0,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'auto',
  },
  content: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    minWidth: 0,
  },
  answerArea: {
    flex: 1,
    overflow: 'auto',
    padding: '1.5rem',
  },
};

export default Chat;
