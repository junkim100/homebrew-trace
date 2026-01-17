import { useState, useEffect } from 'react';

declare global {
  interface Window {
    traceAPI: {
      ping: () => Promise<string>;
      platform: string;
    };
  }
}

function Home() {
  const [ipcStatus, setIpcStatus] = useState<string>('Testing...');

  useEffect(() => {
    // Test IPC communication on mount
    if (window.traceAPI) {
      window.traceAPI
        .ping()
        .then((response) => {
          setIpcStatus(`IPC working: ${response}`);
        })
        .catch((err) => {
          setIpcStatus(`IPC error: ${err.message}`);
        });
    } else {
      setIpcStatus('Not running in Electron');
    }
  }, []);

  return (
    <div style={styles.container}>
      <div className="titlebar" />
      <main style={styles.main}>
        <h1 style={styles.title}>Trace</h1>
        <p style={styles.subtitle}>
          Your digital activity, organized and searchable.
        </p>
        <div style={styles.statusCard}>
          <p style={styles.statusText}>{ipcStatus}</p>
          <p style={styles.platformText}>
            Platform: {window.traceAPI?.platform || 'Browser'}
          </p>
        </div>
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
  statusCard: {
    background: '#2a2a2a',
    borderRadius: '12px',
    padding: '1.5rem 2rem',
    border: '1px solid #3a3a3a',
  },
  statusText: {
    fontSize: '1rem',
    color: '#00d4ff',
    marginBottom: '0.5rem',
  },
  platformText: {
    fontSize: '0.875rem',
    color: '#707070',
  },
};

export default Home;
