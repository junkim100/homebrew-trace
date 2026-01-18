import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import type { BackendStatus, AllPermissionsState } from '../types/trace-api';

function Home() {
  const navigate = useNavigate();
  const [electronIpc, setElectronIpc] = useState<string>('Testing...');
  const [pythonReady, setPythonReady] = useState<boolean>(false);
  const [pythonPing, setPythonPing] = useState<string>('Waiting...');
  const [backendStatus, setBackendStatus] = useState<BackendStatus | null>(null);
  const [permissionsState, setPermissionsState] = useState<AllPermissionsState | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!window.traceAPI) {
      setElectronIpc('Not running in Electron');
      return;
    }

    // Test Electron IPC
    window.traceAPI
      .ping()
      .then((response) => {
        setElectronIpc(`OK: ${response}`);
      })
      .catch((err) => {
        setElectronIpc(`Error: ${err.message}`);
      });

    // Poll for Python backend readiness
    const checkPython = async () => {
      try {
        const ready = await window.traceAPI.python.isReady();
        setPythonReady(ready);

        if (ready) {
          // Test Python ping
          const pingResult = await window.traceAPI.python.ping();
          setPythonPing(`OK: ${pingResult}`);

          // Get backend status
          const status = await window.traceAPI.python.getStatus();
          setBackendStatus(status);

          // Check permissions
          const permissions = await window.traceAPI.permissions.checkAll();
          setPermissionsState(permissions);

          // Redirect to permissions page if not all granted
          if (!permissions.all_granted) {
            navigate('/permissions');
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      }
    };

    // Check immediately and then poll every 2 seconds until ready
    checkPython();
    const interval = setInterval(() => {
      if (!pythonReady) {
        checkPython();
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [pythonReady, navigate]);

  return (
    <div style={styles.container}>
      <div className="titlebar" />
      <main style={styles.main}>
        <h1 style={styles.title}>Trace</h1>
        <p style={styles.subtitle}>
          Your digital activity, organized and searchable.
        </p>

        <div style={styles.statusGrid}>
          <div style={styles.statusCard}>
            <h3 style={styles.cardTitle}>Electron IPC</h3>
            <p style={styles.statusValue}>{electronIpc}</p>
            <p style={styles.statusLabel}>
              Platform: {window.traceAPI?.platform || 'Browser'}
            </p>
          </div>

          <div style={styles.statusCard}>
            <h3 style={styles.cardTitle}>Python Backend</h3>
            <p style={{ ...styles.statusValue, color: pythonReady ? '#00d4ff' : '#ff6b6b' }}>
              {pythonReady ? 'Connected' : 'Connecting...'}
            </p>
            <p style={styles.statusLabel}>Ping: {pythonPing}</p>
          </div>

          {backendStatus && (
            <div style={styles.statusCard}>
              <h3 style={styles.cardTitle}>Backend Info</h3>
              <p style={styles.statusValue}>v{backendStatus.version}</p>
              <p style={styles.statusLabel}>
                Python {backendStatus.python_version}
              </p>
              <p style={styles.statusLabel}>
                Uptime: {Math.floor(backendStatus.uptime_seconds)}s
              </p>
            </div>
          )}

          {permissionsState && (
            <div style={styles.statusCard}>
              <h3 style={styles.cardTitle}>Permissions</h3>
              <p style={{ ...styles.statusValue, color: permissionsState.all_granted ? '#34c759' : '#ff9500' }}>
                {permissionsState.all_granted ? 'All Granted' : 'Setup Required'}
              </p>
              <p style={styles.statusLabel}>
                Screen: {permissionsState.screen_recording.status}
              </p>
              <p style={styles.statusLabel}>
                Accessibility: {permissionsState.accessibility.status}
              </p>
              <p style={styles.statusLabel}>
                Location: {permissionsState.location.status}
              </p>
              {!permissionsState.all_granted && (
                <button
                  style={styles.setupButton}
                  onClick={() => navigate('/permissions')}
                >
                  Setup Permissions
                </button>
              )}
            </div>
          )}
        </div>

        {error && (
          <div style={styles.errorCard}>
            <p style={styles.errorText}>{error}</p>
          </div>
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
  },
  main: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '2rem',
  },
  title: {
    fontSize: '3rem',
    fontWeight: 700,
    marginBottom: '0.5rem',
    background: 'linear-gradient(135deg, #007aff, #00d4ff)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
  },
  subtitle: {
    fontSize: '1.25rem',
    color: '#a0a0a0',
    marginBottom: '2rem',
  },
  statusGrid: {
    display: 'flex',
    gap: '1rem',
    flexWrap: 'wrap',
    justifyContent: 'center',
  },
  statusCard: {
    background: '#2a2a2a',
    borderRadius: '12px',
    padding: '1.5rem',
    border: '1px solid #3a3a3a',
    minWidth: '200px',
  },
  cardTitle: {
    fontSize: '0.875rem',
    color: '#707070',
    marginBottom: '0.5rem',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  statusValue: {
    fontSize: '1.25rem',
    color: '#00d4ff',
    marginBottom: '0.5rem',
  },
  statusLabel: {
    fontSize: '0.875rem',
    color: '#707070',
  },
  errorCard: {
    background: '#3a2020',
    borderRadius: '12px',
    padding: '1rem',
    border: '1px solid #5a3030',
    marginTop: '1rem',
  },
  errorText: {
    color: '#ff6b6b',
    fontSize: '0.875rem',
  },
  setupButton: {
    backgroundColor: '#007aff',
    color: '#fff',
    border: 'none',
    borderRadius: '8px',
    padding: '0.5rem 1rem',
    fontSize: '0.75rem',
    fontWeight: 500,
    cursor: 'pointer',
    marginTop: '0.5rem',
    width: '100%',
  },
};

export default Home;
