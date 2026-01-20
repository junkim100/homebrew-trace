import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

interface ProductivitySummary {
  totalMinutes: number;
  totalHours: number;
  uniqueApps: number;
  notesGenerated: number;
  entitiesExtracted: number;
  mostProductiveHour: number | null;
  daysAnalyzed: number;
}

interface AppUsage {
  appName: string;
  bundleId: string;
  totalMinutes: number;
  sessionCount: number;
  percentage: number;
}

interface TopicUsage {
  topic: string;
  entityType: string;
  noteCount: number;
  mentionStrength: number;
}

interface ActivityTrend {
  date: string;
  eventCount: number;
  uniqueApps: number;
}

interface HeatmapCell {
  hour: number;
  dayOfWeek: number;
  activityCount: number;
}

interface DashboardData {
  success: boolean;
  summary: ProductivitySummary;
  appUsage: AppUsage[];
  topicUsage: TopicUsage[];
  activityTrend: ActivityTrend[];
  activityHeatmap: HeatmapCell[];
}

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export function Dashboard() {
  const navigate = useNavigate();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [daysBack, setDaysBack] = useState(7);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await window.traceAPI.dashboard.getData(daysBack);
      if (result.success) {
        setData(result);
      } else {
        setError(result.error || 'Failed to load dashboard data');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  }, [daysBack]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const getHeatmapColor = (count: number, maxCount: number): string => {
    if (count === 0) return 'var(--bg-secondary)';
    const intensity = Math.min(count / Math.max(maxCount, 1), 1);
    const alpha = 0.2 + intensity * 0.8;
    return `rgba(0, 212, 255, ${alpha})`;
  };

  const maxHeatmapValue = data?.activityHeatmap
    ? Math.max(...data.activityHeatmap.map((c) => c.activityCount))
    : 0;

  return (
    <div style={styles.container}>
      {/* Titlebar */}
      <div className="titlebar" style={styles.titlebar}>
        <button onClick={() => navigate('/chat')} style={styles.backButton}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
        </button>
        <h1 style={styles.title}>Activity Dashboard</h1>
        <div style={styles.timeSelector}>
          {[7, 14, 30].map((days) => (
            <button
              key={days}
              onClick={() => setDaysBack(days)}
              style={{
                ...styles.timeButton,
                ...(daysBack === days ? styles.timeButtonActive : {}),
              }}
            >
              {days}d
            </button>
          ))}
        </div>
      </div>

      <main style={styles.main}>
        {loading && (
          <div style={styles.loading}>
            <div style={styles.spinner} />
            <span>Loading dashboard...</span>
          </div>
        )}

        {error && (
          <div style={styles.error}>
            <p>{error}</p>
            <button onClick={fetchData} style={styles.retryButton}>
              Retry
            </button>
          </div>
        )}

        {data && !loading && (
          <>
            {/* Summary Cards */}
            <div style={styles.summaryGrid}>
              <div style={styles.summaryCard}>
                <div style={styles.summaryValue}>{data.summary.totalHours.toFixed(1)}h</div>
                <div style={styles.summaryLabel}>Total Active Time</div>
              </div>
              <div style={styles.summaryCard}>
                <div style={styles.summaryValue}>{data.summary.uniqueApps}</div>
                <div style={styles.summaryLabel}>Apps Used</div>
              </div>
              <div style={styles.summaryCard}>
                <div style={styles.summaryValue}>{data.summary.notesGenerated}</div>
                <div style={styles.summaryLabel}>Notes Generated</div>
              </div>
              <div style={styles.summaryCard}>
                <div style={styles.summaryValue}>
                  {data.summary.mostProductiveHour !== null
                    ? `${data.summary.mostProductiveHour}:00`
                    : 'N/A'}
                </div>
                <div style={styles.summaryLabel}>Peak Hour</div>
              </div>
            </div>

            <div style={styles.chartsGrid}>
              {/* App Usage Chart */}
              <div style={styles.chartCard}>
                <h3 style={styles.chartTitle}>Top Apps</h3>
                <div style={styles.barChart}>
                  {data.appUsage.slice(0, 8).map((app, idx) => (
                    <div key={app.bundleId} style={styles.barRow}>
                      <div style={styles.barLabel}>{app.appName}</div>
                      <div style={styles.barContainer}>
                        <div
                          style={{
                            ...styles.bar,
                            width: `${app.percentage}%`,
                            backgroundColor: `hsl(${190 + idx * 20}, 80%, 50%)`,
                          }}
                        />
                      </div>
                      <div style={styles.barValue}>{app.totalMinutes.toFixed(0)}m</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Topic Usage */}
              <div style={styles.chartCard}>
                <h3 style={styles.chartTitle}>Top Topics</h3>
                <div style={styles.topicList}>
                  {data.topicUsage.slice(0, 8).map((topic) => (
                    <div key={topic.topic} style={styles.topicRow}>
                      <span style={styles.topicName}>{topic.topic}</span>
                      <span style={styles.topicType}>{topic.entityType}</span>
                      <span style={styles.topicCount}>{topic.noteCount} notes</span>
                    </div>
                  ))}
                  {data.topicUsage.length === 0 && (
                    <div style={styles.emptyState}>No topics found</div>
                  )}
                </div>
              </div>

              {/* Activity Trend */}
              <div style={styles.chartCard}>
                <h3 style={styles.chartTitle}>Activity Trend</h3>
                <div style={styles.trendChart}>
                  {data.activityTrend.length > 0 ? (
                    <svg viewBox={`0 0 ${data.activityTrend.length * 20} 100`} style={styles.trendSvg}>
                      {/* Line */}
                      <polyline
                        fill="none"
                        stroke="var(--accent)"
                        strokeWidth="2"
                        points={data.activityTrend
                          .map((point, idx) => {
                            const maxEvents = Math.max(...data.activityTrend.map((p) => p.eventCount));
                            const y = 90 - (point.eventCount / Math.max(maxEvents, 1)) * 80;
                            return `${idx * 20 + 10},${y}`;
                          })
                          .join(' ')}
                      />
                      {/* Points */}
                      {data.activityTrend.map((point, idx) => {
                        const maxEvents = Math.max(...data.activityTrend.map((p) => p.eventCount));
                        const y = 90 - (point.eventCount / Math.max(maxEvents, 1)) * 80;
                        return (
                          <circle
                            key={point.date}
                            cx={idx * 20 + 10}
                            cy={y}
                            r="3"
                            fill="var(--accent)"
                          />
                        );
                      })}
                    </svg>
                  ) : (
                    <div style={styles.emptyState}>No activity data</div>
                  )}
                </div>
              </div>

              {/* Activity Heatmap */}
              <div style={styles.chartCard}>
                <h3 style={styles.chartTitle}>Activity Heatmap</h3>
                <div style={styles.heatmapContainer}>
                  <div style={styles.heatmapLabels}>
                    <div style={styles.heatmapCorner} />
                    {Array.from({ length: 24 }, (_, h) => (
                      <div key={h} style={styles.heatmapHourLabel}>
                        {h % 6 === 0 ? `${h}` : ''}
                      </div>
                    ))}
                  </div>
                  {DAYS.map((day, dayIdx) => (
                    <div key={day} style={styles.heatmapRow}>
                      <div style={styles.heatmapDayLabel}>{day}</div>
                      {Array.from({ length: 24 }, (_, hour) => {
                        const cell = data.activityHeatmap.find(
                          (c) => c.hour === hour && c.dayOfWeek === dayIdx
                        );
                        const count = cell?.activityCount || 0;
                        return (
                          <div
                            key={hour}
                            style={{
                              ...styles.heatmapCell,
                              backgroundColor: getHeatmapColor(count, maxHeatmapValue),
                            }}
                            title={`${day} ${hour}:00 - ${count} activities`}
                          />
                        );
                      })}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    height: '100vh',
    overflow: 'hidden',
  },
  titlebar: {
    display: 'flex',
    alignItems: 'center',
    padding: '0 1rem',
    gap: '1rem',
    borderBottom: '1px solid var(--border)',
  },
  backButton: {
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
  title: {
    flex: 1,
    fontSize: '1rem',
    fontWeight: 600,
    color: 'var(--text)',
    margin: 0,
  },
  timeSelector: {
    display: 'flex',
    gap: '0.25rem',
  },
  timeButton: {
    padding: '0.25rem 0.5rem',
    border: '1px solid var(--border)',
    borderRadius: '4px',
    backgroundColor: 'transparent',
    color: 'var(--text-secondary)',
    cursor: 'pointer',
    fontSize: '0.75rem',
  },
  timeButtonActive: {
    backgroundColor: 'var(--accent)',
    borderColor: 'var(--accent)',
    color: 'white',
  },
  main: {
    flex: 1,
    overflow: 'auto',
    padding: '1.5rem',
  },
  loading: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    gap: '1rem',
    color: 'var(--text-secondary)',
  },
  spinner: {
    width: '32px',
    height: '32px',
    border: '3px solid var(--border)',
    borderTopColor: 'var(--accent)',
    borderRadius: '50%',
    animation: 'spin 1s linear infinite',
  },
  error: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    gap: '1rem',
    color: 'var(--error)',
  },
  retryButton: {
    padding: '0.5rem 1rem',
    backgroundColor: 'var(--accent)',
    color: 'white',
    border: 'none',
    borderRadius: '6px',
    cursor: 'pointer',
  },
  summaryGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(4, 1fr)',
    gap: '1rem',
    marginBottom: '1.5rem',
  },
  summaryCard: {
    backgroundColor: 'var(--bg-secondary)',
    borderRadius: '12px',
    padding: '1.25rem',
    textAlign: 'center',
  },
  summaryValue: {
    fontSize: '1.75rem',
    fontWeight: 700,
    color: 'var(--accent)',
    marginBottom: '0.25rem',
  },
  summaryLabel: {
    fontSize: '0.75rem',
    color: 'var(--text-secondary)',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  chartsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, 1fr)',
    gap: '1rem',
  },
  chartCard: {
    backgroundColor: 'var(--bg-secondary)',
    borderRadius: '12px',
    padding: '1.25rem',
    minHeight: '250px',
  },
  chartTitle: {
    fontSize: '0.875rem',
    fontWeight: 600,
    color: 'var(--text)',
    marginBottom: '1rem',
    margin: '0 0 1rem 0',
  },
  barChart: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  barRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
  },
  barLabel: {
    width: '100px',
    fontSize: '0.75rem',
    color: 'var(--text)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  barContainer: {
    flex: 1,
    height: '16px',
    backgroundColor: 'var(--bg)',
    borderRadius: '4px',
    overflow: 'hidden',
  },
  bar: {
    height: '100%',
    borderRadius: '4px',
    transition: 'width 0.3s ease',
  },
  barValue: {
    width: '50px',
    fontSize: '0.75rem',
    color: 'var(--text-secondary)',
    textAlign: 'right',
  },
  topicList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  topicRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    padding: '0.5rem',
    backgroundColor: 'var(--bg)',
    borderRadius: '6px',
  },
  topicName: {
    flex: 1,
    fontSize: '0.875rem',
    color: 'var(--text)',
  },
  topicType: {
    fontSize: '0.625rem',
    color: 'var(--text-secondary)',
    textTransform: 'uppercase',
    padding: '0.125rem 0.375rem',
    backgroundColor: 'var(--bg-secondary)',
    borderRadius: '4px',
  },
  topicCount: {
    fontSize: '0.75rem',
    color: 'var(--text-secondary)',
  },
  emptyState: {
    color: 'var(--text-secondary)',
    fontSize: '0.875rem',
    textAlign: 'center',
    padding: '2rem',
  },
  trendChart: {
    height: '150px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  trendSvg: {
    width: '100%',
    height: '100%',
  },
  heatmapContainer: {
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
  },
  heatmapLabels: {
    display: 'flex',
    gap: '2px',
    paddingLeft: '32px',
  },
  heatmapCorner: {
    width: '32px',
  },
  heatmapHourLabel: {
    width: '10px',
    fontSize: '0.5rem',
    color: 'var(--text-secondary)',
    textAlign: 'center',
  },
  heatmapRow: {
    display: 'flex',
    gap: '2px',
    alignItems: 'center',
  },
  heatmapDayLabel: {
    width: '32px',
    fontSize: '0.625rem',
    color: 'var(--text-secondary)',
  },
  heatmapCell: {
    width: '10px',
    height: '10px',
    borderRadius: '2px',
  },
};

export default Dashboard;
