import { useState } from 'react';

export type TimePreset = 'today' | 'yesterday' | 'this_week' | 'last_week' | 'this_month' | 'custom' | 'all';

interface TimeFilterProps {
  value: TimePreset;
  customStart?: string;
  customEnd?: string;
  onChange: (preset: TimePreset, customStart?: string, customEnd?: string) => void;
}

const PRESETS: { value: TimePreset; label: string }[] = [
  { value: 'all', label: 'All Time' },
  { value: 'today', label: 'Today' },
  { value: 'yesterday', label: 'Yesterday' },
  { value: 'this_week', label: 'This Week' },
  { value: 'last_week', label: 'Last Week' },
  { value: 'this_month', label: 'This Month' },
  { value: 'custom', label: 'Custom' },
];

export function TimeFilter({ value, customStart, customEnd, onChange }: TimeFilterProps) {
  const [showCustom, setShowCustom] = useState(value === 'custom');
  const [localStart, setLocalStart] = useState(customStart || '');
  const [localEnd, setLocalEnd] = useState(customEnd || '');

  const handlePresetClick = (preset: TimePreset) => {
    if (preset === 'custom') {
      setShowCustom(true);
    } else {
      setShowCustom(false);
      onChange(preset);
    }
  };

  const handleCustomApply = () => {
    if (localStart && localEnd) {
      onChange('custom', localStart, localEnd);
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.presets}>
        {PRESETS.map((preset) => (
          <button
            key={preset.value}
            onClick={() => handlePresetClick(preset.value)}
            style={{
              ...styles.presetButton,
              ...(value === preset.value ? styles.presetButtonActive : {}),
            }}
          >
            {preset.label}
          </button>
        ))}
      </div>
      {showCustom && (
        <div style={styles.customRange}>
          <div style={styles.dateInputGroup}>
            <label style={styles.dateLabel}>From</label>
            <input
              type="date"
              value={localStart}
              onChange={(e) => setLocalStart(e.target.value)}
              style={styles.dateInput}
            />
          </div>
          <div style={styles.dateInputGroup}>
            <label style={styles.dateLabel}>To</label>
            <input
              type="date"
              value={localEnd}
              onChange={(e) => setLocalEnd(e.target.value)}
              style={styles.dateInput}
            />
          </div>
          <button
            onClick={handleCustomApply}
            disabled={!localStart || !localEnd}
            style={{
              ...styles.applyButton,
              ...(!localStart || !localEnd ? styles.applyButtonDisabled : {}),
            }}
          >
            Apply
          </button>
        </div>
      )}
    </div>
  );
}

export function getTimeFilterHint(preset: TimePreset, customStart?: string, customEnd?: string): string | undefined {
  switch (preset) {
    case 'today':
      return 'today';
    case 'yesterday':
      return 'yesterday';
    case 'this_week':
      return 'this week';
    case 'last_week':
      return 'last week';
    case 'this_month':
      return 'this month';
    case 'custom':
      if (customStart && customEnd) {
        return `from ${customStart} to ${customEnd}`;
      }
      return undefined;
    case 'all':
    default:
      return undefined;
  }
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.75rem',
    padding: '0.75rem',
    backgroundColor: 'var(--bg-secondary)',
    borderRadius: '8px',
    border: '1px solid var(--border)',
  },
  presets: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '0.5rem',
  },
  presetButton: {
    backgroundColor: 'transparent',
    border: '1px solid var(--border)',
    borderRadius: '6px',
    padding: '0.375rem 0.75rem',
    color: 'var(--text-secondary)',
    fontSize: '0.8rem',
    cursor: 'pointer',
    transition: 'all 0.2s',
  },
  presetButtonActive: {
    backgroundColor: 'var(--accent)',
    borderColor: 'var(--accent)',
    color: 'white',
  },
  customRange: {
    display: 'flex',
    alignItems: 'flex-end',
    gap: '0.75rem',
    flexWrap: 'wrap',
  },
  dateInputGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.25rem',
  },
  dateLabel: {
    fontSize: '0.75rem',
    color: 'var(--text-secondary)',
  },
  dateInput: {
    backgroundColor: 'var(--bg-primary)',
    border: '1px solid var(--border)',
    borderRadius: '6px',
    padding: '0.375rem 0.5rem',
    color: 'var(--text-primary)',
    fontSize: '0.85rem',
    colorScheme: 'dark',
  },
  applyButton: {
    backgroundColor: 'var(--accent)',
    border: 'none',
    borderRadius: '6px',
    padding: '0.5rem 1rem',
    color: 'white',
    fontSize: '0.85rem',
    cursor: 'pointer',
    fontWeight: 500,
  },
  applyButtonDisabled: {
    backgroundColor: '#404040',
    cursor: 'not-allowed',
    opacity: 0.5,
  },
};

export default TimeFilter;
