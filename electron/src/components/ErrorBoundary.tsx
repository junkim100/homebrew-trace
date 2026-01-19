import { Component, ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // Log error to console in development
    if (process.env.NODE_ENV === 'development') {
      console.error('ErrorBoundary caught an error:', error, errorInfo);
    }
  }

  handleReload = () => {
    window.location.reload();
  };

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div style={styles.container}>
          <div style={styles.content}>
            <div style={styles.icon}>
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <circle cx="12" cy="12" r="10" />
                <path d="M12 8v4" />
                <path d="M12 16h.01" />
              </svg>
            </div>
            <h1 style={styles.title}>Something went wrong</h1>
            <p style={styles.message}>
              The application encountered an unexpected error.
            </p>
            {this.state.error && (
              <pre style={styles.errorDetails}>
                {this.state.error.message}
              </pre>
            )}
            <div style={styles.buttons}>
              <button onClick={this.handleReset} style={styles.secondaryButton}>
                Try Again
              </button>
              <button onClick={this.handleReload} style={styles.primaryButton}>
                Reload App
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: '100vh',
    backgroundColor: '#1a1a1a',
    padding: '2rem',
  },
  content: {
    textAlign: 'center',
    maxWidth: '400px',
  },
  icon: {
    color: '#ff3b30',
    marginBottom: '1rem',
  },
  title: {
    fontSize: '1.5rem',
    fontWeight: 600,
    color: '#fff',
    marginBottom: '0.5rem',
  },
  message: {
    fontSize: '0.95rem',
    color: '#a0a0a0',
    marginBottom: '1rem',
  },
  errorDetails: {
    backgroundColor: '#2a2020',
    border: '1px solid #3a3030',
    borderRadius: '8px',
    padding: '1rem',
    fontSize: '0.8rem',
    color: '#ff6b6b',
    textAlign: 'left',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
    marginBottom: '1.5rem',
    maxHeight: '150px',
    overflow: 'auto',
  },
  buttons: {
    display: 'flex',
    gap: '0.75rem',
    justifyContent: 'center',
  },
  primaryButton: {
    backgroundColor: '#007aff',
    color: '#fff',
    border: 'none',
    borderRadius: '8px',
    padding: '0.625rem 1.25rem',
    fontSize: '0.9rem',
    fontWeight: 500,
    cursor: 'pointer',
  },
  secondaryButton: {
    backgroundColor: 'transparent',
    color: '#007aff',
    border: '1px solid #007aff',
    borderRadius: '8px',
    padding: '0.625rem 1.25rem',
    fontSize: '0.9rem',
    fontWeight: 500,
    cursor: 'pointer',
  },
};

export default ErrorBoundary;
