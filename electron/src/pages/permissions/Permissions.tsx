import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import type {
  AllPermissionsState,
  PermissionType,
  PermissionState,
  PermissionInstructions,
  PermissionStatusType,
} from '../../types/trace-api';

interface PermissionCardProps {
  permission: PermissionState;
  instructions: PermissionInstructions | null;
  onOpenSettings: () => void;
  onRequest?: () => void;
  isLoading: boolean;
}

function PermissionCard({
  permission,
  instructions,
  onOpenSettings,
  onRequest,
  isLoading,
}: PermissionCardProps) {
  const statusColors: Record<PermissionStatusType, string> = {
    granted: '#34c759',
    denied: '#ff3b30',
    not_determined: '#ff9500',
    restricted: '#8e8e93',
  };

  const statusLabels: Record<PermissionStatusType, string> = {
    granted: 'Granted',
    denied: 'Denied',
    not_determined: 'Not Set',
    restricted: 'Restricted',
  };

  const statusColor = statusColors[permission.status] || '#8e8e93';
  const statusLabel = statusLabels[permission.status] || 'Unknown';

  return (
    <div style={styles.permissionCard}>
      <div style={styles.cardHeader}>
        <div style={styles.titleRow}>
          <h3 style={styles.permissionTitle}>{instructions?.title || permission.permission}</h3>
          {permission.required && (
            <span style={styles.requiredBadge}>Required</span>
          )}
        </div>
        <div style={{ ...styles.statusBadge, backgroundColor: statusColor }}>
          {statusLabel}
        </div>
      </div>

      <p style={styles.description}>
        {instructions?.description || 'Loading...'}
      </p>

      {permission.status !== 'granted' && instructions && (
        <div style={styles.stepsContainer}>
          <h4 style={styles.stepsTitle}>Steps to enable:</h4>
          <ol style={styles.stepsList}>
            {instructions.steps.map((step, index) => (
              <li key={index} style={styles.step}>{step}</li>
            ))}
          </ol>
        </div>
      )}

      {permission.status !== 'granted' && (
        <div style={styles.buttonRow}>
          <button
            style={styles.primaryButton}
            onClick={onOpenSettings}
            disabled={isLoading}
          >
            Open System Settings
          </button>
          {onRequest && permission.can_request && (
            <button
              style={styles.secondaryButton}
              onClick={onRequest}
              disabled={isLoading}
            >
              Request Permission
            </button>
          )}
        </div>
      )}

      {permission.status === 'granted' && (
        <div style={styles.grantedMessage}>
          <span style={styles.checkmark}>&#10003;</span> Permission granted
        </div>
      )}

      {instructions?.requires_restart && permission.status === 'denied' && (
        <p style={styles.restartWarning}>
          Note: You may need to restart Trace after granting this permission.
        </p>
      )}
    </div>
  );
}

// Polling interval when actively waiting for permission changes
const ACTIVE_POLL_INTERVAL = 1000; // 1 second
// Polling interval when idle (just checking periodically)
const IDLE_POLL_INTERVAL = 5000; // 5 seconds

function Permissions() {
  const navigate = useNavigate();
  const [permissionsState, setPermissionsState] = useState<AllPermissionsState | null>(null);
  const [instructions, setInstructions] = useState<Record<PermissionType, PermissionInstructions | null>>({
    screen_recording: null,
    accessibility: null,
    location: null,
  });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pythonReady, setPythonReady] = useState(false);
  const [isActivelyWaiting, setIsActivelyWaiting] = useState(false);

  const checkPermissions = useCallback(async (silent = false) => {
    if (!window.traceAPI?.permissions) return;

    try {
      if (!silent) setIsLoading(true);
      const state = await window.traceAPI.permissions.checkAll();

      setPermissionsState(state);
      setError(null);

      // If all permissions are now granted, stop active polling
      if (state.all_granted) {
        setIsActivelyWaiting(false);
      }
    } catch (err) {
      if (!silent) {
        setError(err instanceof Error ? err.message : 'Failed to check permissions');
      }
    } finally {
      if (!silent) setIsLoading(false);
    }
  }, []);

  const loadInstructions = useCallback(async () => {
    if (!window.traceAPI?.permissions) return;

    const permissions: PermissionType[] = ['screen_recording', 'accessibility', 'location'];

    for (const perm of permissions) {
      try {
        const instr = await window.traceAPI.permissions.getInstructions(perm);
        setInstructions(prev => ({ ...prev, [perm]: instr }));
      } catch (err) {
        console.error(`Failed to load instructions for ${perm}:`, err);
      }
    }
  }, []);

  // Check permissions and load instructions on mount
  useEffect(() => {
    if (!window.traceAPI) return;

    checkPermissions();
    loadInstructions();
  }, [checkPermissions, loadInstructions]);

  // Poll for Python backend readiness
  useEffect(() => {
    if (!window.traceAPI || pythonReady) return;

    const checkPython = async () => {
      try {
        const ready = await window.traceAPI.python.isReady();
        if (ready) setPythonReady(true);
      } catch {
        // Ignore errors during polling
      }
    };

    checkPython();
    const interval = setInterval(checkPython, 2000);

    return () => clearInterval(interval);
  }, [pythonReady]);

  // Active polling when waiting for permission changes
  useEffect(() => {
    if (permissionsState?.all_granted) return;

    const pollInterval = isActivelyWaiting ? ACTIVE_POLL_INTERVAL : IDLE_POLL_INTERVAL;

    const interval = setInterval(() => {
      checkPermissions(true);
    }, pollInterval);

    return () => clearInterval(interval);
  }, [isActivelyWaiting, permissionsState?.all_granted, checkPermissions]);

  const handleOpenSettings = async (permission: PermissionType) => {
    if (!window.traceAPI?.permissions) return;

    try {
      await window.traceAPI.permissions.openSettings(permission);
      // Start active polling - user is interacting with settings
      setIsActivelyWaiting(true);
      // Also do an immediate check after a short delay
      setTimeout(() => checkPermissions(true), 500);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to open settings');
    }
  };

  const handleRequestAccessibility = async () => {
    if (!window.traceAPI?.permissions) return;

    try {
      await window.traceAPI.permissions.requestAccessibility();
      setIsActivelyWaiting(true);
      setTimeout(() => checkPermissions(true), 500);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to request permission');
    }
  };

  const handleRequestLocation = async () => {
    if (!window.traceAPI?.permissions) return;

    try {
      await window.traceAPI.permissions.requestLocation();
      setIsActivelyWaiting(true);
      setTimeout(() => checkPermissions(true), 500);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to request permission');
    }
  };

  const handleContinue = () => {
    // Navigate to chat page using React Router
    navigate('/chat');
  };

  if (!window.traceAPI) {
    return (
      <div style={styles.container}>
        <div style={styles.content}>
          <h1 style={styles.title}>Permissions</h1>
          <p style={styles.subtitle}>Not running in Electron</p>
        </div>
      </div>
    );
  }

  if (!pythonReady) {
    return (
      <div style={styles.container}>
        <div style={styles.content}>
          <h1 style={styles.title}>Permissions</h1>
          <p style={styles.subtitle}>Connecting to backend...</p>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      <div className="titlebar" />
      <div style={styles.content}>
        <h1 style={styles.title}>Permissions Required</h1>
        <p style={styles.subtitle}>
          Trace needs some permissions to capture your digital activity.
        </p>


        {error && (
          <div style={styles.errorCard}>
            <p style={styles.errorText}>{error}</p>
          </div>
        )}

        <div style={styles.permissionsList}>
          {permissionsState && (
            <>
              <PermissionCard
                permission={permissionsState.screen_recording}
                instructions={instructions.screen_recording}
                onOpenSettings={() => handleOpenSettings('screen_recording')}
                isLoading={isLoading}
              />

              <PermissionCard
                permission={permissionsState.accessibility}
                instructions={instructions.accessibility}
                onOpenSettings={() => handleOpenSettings('accessibility')}
                onRequest={handleRequestAccessibility}
                isLoading={isLoading}
              />

              <PermissionCard
                permission={permissionsState.location}
                instructions={instructions.location}
                onOpenSettings={() => handleOpenSettings('location')}
                onRequest={handleRequestLocation}
                isLoading={isLoading}
              />
            </>
          )}
        </div>

        <div style={styles.footer}>
          <button
            style={{
              ...styles.continueButton,
              opacity: permissionsState?.all_granted ? 1 : 0.5,
            }}
            onClick={handleContinue}
            disabled={!permissionsState?.all_granted}
          >
            {permissionsState?.all_granted ? 'Continue to Trace' : 'Grant Required Permissions'}
          </button>
          <div style={styles.pollingInfo}>
            {isActivelyWaiting && !permissionsState?.all_granted && (
              <span style={styles.pollingIndicator}>
                <span style={styles.pollingDot} />
                Checking for permission changes...
              </span>
            )}
            <button
              style={styles.refreshButton}
              onClick={() => checkPermissions()}
              disabled={isLoading}
            >
              {isLoading ? 'Checking...' : 'Refresh Status'}
            </button>
          </div>
        </div>

        {permissionsState?.requires_restart && (
          <p style={styles.restartNote}>
            Some permissions may require restarting Trace to take effect.
          </p>
        )}
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    minHeight: '100vh',
    backgroundColor: '#1a1a1a',
  },
  content: {
    flex: 1,
    padding: '2rem',
    maxWidth: '800px',
    margin: '0 auto',
    width: '100%',
  },
  title: {
    fontSize: '2rem',
    fontWeight: 700,
    marginBottom: '0.5rem',
    background: 'linear-gradient(135deg, #007aff, #00d4ff)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    textAlign: 'center',
  },
  subtitle: {
    fontSize: '1rem',
    color: '#a0a0a0',
    marginBottom: '2rem',
    textAlign: 'center',
  },
  permissionsList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '1rem',
  },
  permissionCard: {
    background: '#2a2a2a',
    borderRadius: '12px',
    padding: '1.5rem',
    border: '1px solid #3a3a3a',
  },
  cardHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: '0.75rem',
  },
  titleRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
  },
  permissionTitle: {
    fontSize: '1.25rem',
    fontWeight: 600,
    color: '#fff',
    margin: 0,
  },
  requiredBadge: {
    fontSize: '0.75rem',
    color: '#ff9500',
    padding: '0.125rem 0.5rem',
    borderRadius: '4px',
    border: '1px solid #ff9500',
  },
  statusBadge: {
    fontSize: '0.75rem',
    color: '#fff',
    padding: '0.25rem 0.75rem',
    borderRadius: '12px',
    fontWeight: 500,
  },
  description: {
    fontSize: '0.875rem',
    color: '#a0a0a0',
    marginBottom: '1rem',
    lineHeight: 1.5,
  },
  stepsContainer: {
    backgroundColor: '#222',
    borderRadius: '8px',
    padding: '1rem',
    marginBottom: '1rem',
  },
  stepsTitle: {
    fontSize: '0.875rem',
    fontWeight: 600,
    color: '#ccc',
    margin: '0 0 0.5rem 0',
  },
  stepsList: {
    margin: 0,
    paddingLeft: '1.25rem',
  },
  step: {
    fontSize: '0.875rem',
    color: '#999',
    marginBottom: '0.25rem',
    lineHeight: 1.4,
  },
  buttonRow: {
    display: 'flex',
    gap: '0.75rem',
    flexWrap: 'wrap',
  },
  primaryButton: {
    backgroundColor: '#007aff',
    color: '#fff',
    border: 'none',
    borderRadius: '8px',
    padding: '0.5rem 1rem',
    fontSize: '0.875rem',
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'background-color 0.2s',
  },
  secondaryButton: {
    backgroundColor: 'transparent',
    color: '#007aff',
    border: '1px solid #007aff',
    borderRadius: '8px',
    padding: '0.5rem 1rem',
    fontSize: '0.875rem',
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'all 0.2s',
  },
  grantedMessage: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    color: '#34c759',
    fontSize: '0.875rem',
    fontWeight: 500,
  },
  checkmark: {
    fontSize: '1rem',
  },
  restartWarning: {
    fontSize: '0.75rem',
    color: '#ff9500',
    marginTop: '0.75rem',
    marginBottom: 0,
  },
  footer: {
    marginTop: '2rem',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '1rem',
  },
  continueButton: {
    backgroundColor: '#34c759',
    color: '#fff',
    border: 'none',
    borderRadius: '12px',
    padding: '1rem 2rem',
    fontSize: '1rem',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all 0.2s',
    width: '100%',
    maxWidth: '300px',
  },
  pollingInfo: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '0.5rem',
  },
  pollingIndicator: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    fontSize: '0.75rem',
    color: '#00d4ff',
  },
  pollingDot: {
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    backgroundColor: '#00d4ff',
    animation: 'pulse 1s ease-in-out infinite',
  },
  refreshButton: {
    backgroundColor: 'transparent',
    color: '#007aff',
    border: '1px solid #007aff',
    borderRadius: '8px',
    padding: '0.5rem 1rem',
    fontSize: '0.875rem',
    fontWeight: 500,
    cursor: 'pointer',
  },
  restartNote: {
    fontSize: '0.75rem',
    color: '#ff9500',
    textAlign: 'center',
    marginTop: '1rem',
  },
  errorCard: {
    background: '#3a2020',
    borderRadius: '12px',
    padding: '1rem',
    border: '1px solid #5a3030',
    marginBottom: '1rem',
  },
  errorText: {
    color: '#ff6b6b',
    fontSize: '0.875rem',
    margin: 0,
  },
  devNote: {
    backgroundColor: '#2a2a3a',
    borderRadius: '8px',
    padding: '1rem',
    marginBottom: '1.5rem',
    fontSize: '0.875rem',
    color: '#a0a0c0',
    lineHeight: 1.5,
    border: '1px solid #3a3a4a',
  },
};

export default Permissions;
