import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import type { BackendStatus } from '../types/trace-api';

type SetupStep = 'loading' | 'api_key' | 'permissions' | 'ready';

function Home() {
  const navigate = useNavigate();
  const [step, setStep] = useState<SetupStep>('loading');
  const [pythonReady, setPythonReady] = useState<boolean>(false);
  const [backendStatus, setBackendStatus] = useState<BackendStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  // API Key form state
  const [apiKey, setApiKey] = useState<string>('');
  const [apiKeyError, setApiKeyError] = useState<string | null>(null);
  const [validating, setValidating] = useState<boolean>(false);

  useEffect(() => {
    if (!window.traceAPI) {
      setError('Not running in Electron');
      return;
    }

    // Poll for Python backend readiness
    const checkPython = async () => {
      try {
        const ready = await window.traceAPI.python.isReady();
        setPythonReady(ready);

        if (ready) {
          // Get backend status
          const status = await window.traceAPI.python.getStatus();
          setBackendStatus(status);

          // Check if API key is set
          const settings = await window.traceAPI.settings.get();

          if (!settings.has_api_key) {
            setStep('api_key');
            return;
          }

          // API key exists, check permissions
          const permissions = await window.traceAPI.permissions.checkAll();

          if (!permissions.all_granted) {
            navigate('/permissions');
          } else {
            // All good - go to chat
            navigate('/chat');
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

  const handleApiKeySubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setApiKeyError(null);
    setValidating(true);

    try {
      // Validate the API key
      const validation = await window.traceAPI.settings.validateApiKey(apiKey);

      if (!validation.valid) {
        setApiKeyError(validation.error || 'Invalid API key');
        setValidating(false);
        return;
      }

      // Save the API key
      const saveResult = await window.traceAPI.settings.setApiKey(apiKey);

      if (!saveResult.success) {
        setApiKeyError('Failed to save API key');
        setValidating(false);
        return;
      }

      // Check permissions next
      const permissions = await window.traceAPI.permissions.checkAll();

      if (!permissions.all_granted) {
        navigate('/permissions');
      } else {
        navigate('/chat');
      }
    } catch (err) {
      setApiKeyError(err instanceof Error ? err.message : 'Failed to validate API key');
    } finally {
      setValidating(false);
    }
  };

  // Loading state
  if (!pythonReady) {
    return (
      <div style={styles.container}>
        <div className="titlebar" />
        <main style={styles.main}>
          <h1 style={styles.logoText}>TRACE</h1>
          <p style={styles.subtitle}>
            Your digital activity, organized and searchable.
          </p>
          <div style={styles.loadingContainer}>
            <div style={styles.spinner} />
            <p style={styles.loadingText}>Starting backend...</p>
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

  // API Key entry
  if (step === 'api_key') {
    return (
      <div style={styles.container}>
        <div className="titlebar" />
        <main style={styles.main}>
          <h1 style={styles.logoText}>TRACE</h1>
          <p style={styles.subtitle}>
            Your digital activity, organized and searchable.
          </p>

          <div style={styles.apiKeyCard}>
            <h2 style={styles.apiKeyTitle}>OpenAI API Key Required</h2>
            <p style={styles.apiKeyDescription}>
              Trace uses OpenAI&apos;s API to analyze your activity and generate summaries.
              Your API key is stored locally and never shared.
            </p>

            <form onSubmit={handleApiKeySubmit} style={styles.apiKeyForm}>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="sk-..."
                style={styles.apiKeyInput}
                disabled={validating}
                autoFocus
              />

              {apiKeyError && (
                <p style={styles.apiKeyError}>{apiKeyError}</p>
              )}

              <button
                type="submit"
                style={styles.apiKeyButton}
                disabled={validating || !apiKey.trim()}
              >
                {validating ? 'Validating...' : 'Continue'}
              </button>
            </form>

            <p style={styles.apiKeyHelp}>
              Don&apos;t have an API key?{' '}
              <a
                href="https://platform.openai.com/api-keys"
                target="_blank"
                rel="noopener noreferrer"
                style={styles.apiKeyLink}
              >
                Get one from OpenAI
              </a>
            </p>
          </div>

          {backendStatus && (
            <p style={styles.versionText}>v{backendStatus.version}</p>
          )}
        </main>
      </div>
    );
  }

  // Default/loading permissions
  return (
    <div style={styles.container}>
      <div className="titlebar" />
      <main style={styles.main}>
        <h1 style={styles.logoText}>TRACE</h1>
        <p style={styles.subtitle}>
          Your digital activity, organized and searchable.
        </p>
        <div style={styles.loadingContainer}>
          <div style={styles.spinner} />
          <p style={styles.loadingText}>Checking setup...</p>
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
    minHeight: '100vh',
  },
  main: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '2rem',
  },
  logoText: {
    fontSize: '3rem',
    fontWeight: 700,
    letterSpacing: '0.15em',
    marginBottom: '0.5rem',
    background: 'linear-gradient(135deg, #00d4ff 0%, #7b68ee 50%, #ff6b9d 100%)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    backgroundClip: 'text',
  },
  subtitle: {
    fontSize: '1.25rem',
    color: '#a0a0a0',
    marginBottom: '2rem',
  },
  loadingContainer: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '1rem',
  },
  spinner: {
    width: '32px',
    height: '32px',
    border: '3px solid var(--border)',
    borderTopColor: 'var(--accent)',
    borderRadius: '50%',
    animation: 'spin 1s linear infinite',
  },
  loadingText: {
    color: '#707070',
    fontSize: '0.9rem',
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
  apiKeyCard: {
    background: '#2a2a2a',
    borderRadius: '16px',
    padding: '2rem',
    border: '1px solid #3a3a3a',
    maxWidth: '400px',
    width: '100%',
    textAlign: 'center',
  },
  apiKeyTitle: {
    fontSize: '1.25rem',
    fontWeight: 600,
    color: '#ffffff',
    marginBottom: '0.75rem',
  },
  apiKeyDescription: {
    fontSize: '0.9rem',
    color: '#a0a0a0',
    marginBottom: '1.5rem',
    lineHeight: 1.5,
  },
  apiKeyForm: {
    display: 'flex',
    flexDirection: 'column',
    gap: '1rem',
  },
  apiKeyInput: {
    backgroundColor: '#1a1a1a',
    border: '1px solid #3a3a3a',
    borderRadius: '8px',
    padding: '0.75rem 1rem',
    fontSize: '1rem',
    color: '#ffffff',
    outline: 'none',
    fontFamily: 'monospace',
  },
  apiKeyError: {
    color: '#ff6b6b',
    fontSize: '0.85rem',
    textAlign: 'left',
    margin: 0,
  },
  apiKeyButton: {
    backgroundColor: '#007aff',
    color: '#ffffff',
    border: 'none',
    borderRadius: '8px',
    padding: '0.75rem 1.5rem',
    fontSize: '1rem',
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'background-color 0.2s',
  },
  apiKeyHelp: {
    fontSize: '0.85rem',
    color: '#707070',
    marginTop: '1.5rem',
  },
  apiKeyLink: {
    color: '#00d4ff',
    textDecoration: 'none',
  },
  versionText: {
    fontSize: '0.8rem',
    color: '#505050',
    marginTop: '2rem',
  },
};

export default Home;
