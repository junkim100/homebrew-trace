import { useState, useRef, useEffect, KeyboardEvent } from 'react';

interface ChatInputProps {
  onSubmit: (query: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatInput({ onSubmit, disabled = false, placeholder = 'Ask about your activity...' }: ChatInputProps) {
  const [query, setQuery] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea based on content
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  }, [query]);

  const handleSubmit = () => {
    const trimmed = query.trim();
    if (trimmed && !disabled) {
      onSubmit(trimmed);
      setQuery('');
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.inputWrapper}>
        <textarea
          ref={textareaRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          style={{
            ...styles.input,
            ...(disabled ? styles.inputDisabled : {}),
          }}
          rows={1}
        />
        <button
          onClick={handleSubmit}
          disabled={disabled || !query.trim()}
          style={{
            ...styles.submitButton,
            ...(disabled || !query.trim() ? styles.submitButtonDisabled : {}),
          }}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M22 2L11 13" />
            <path d="M22 2L15 22L11 13L2 9L22 2Z" />
          </svg>
        </button>
      </div>
      <p style={styles.hint}>
        Press Enter to send, Shift+Enter for new line
      </p>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    width: '100%',
    padding: '1rem',
    borderTop: '1px solid var(--border)',
    backgroundColor: 'var(--bg-primary)',
  },
  inputWrapper: {
    display: 'flex',
    gap: '0.5rem',
    alignItems: 'flex-end',
    backgroundColor: 'var(--bg-secondary)',
    borderRadius: '12px',
    padding: '0.5rem',
    border: '1px solid var(--border)',
  },
  input: {
    flex: 1,
    backgroundColor: 'transparent',
    border: 'none',
    color: 'var(--text-primary)',
    fontSize: '0.95rem',
    lineHeight: '1.5',
    resize: 'none',
    outline: 'none',
    fontFamily: 'inherit',
    padding: '0.5rem',
    maxHeight: '200px',
  },
  inputDisabled: {
    opacity: 0.5,
    cursor: 'not-allowed',
  },
  submitButton: {
    backgroundColor: 'var(--accent)',
    border: 'none',
    borderRadius: '8px',
    padding: '0.5rem',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: 'white',
    transition: 'background-color 0.2s',
  },
  submitButtonDisabled: {
    backgroundColor: '#404040',
    cursor: 'not-allowed',
    opacity: 0.5,
  },
  hint: {
    fontSize: '0.75rem',
    color: 'var(--text-secondary)',
    marginTop: '0.5rem',
    textAlign: 'center',
  },
};

export default ChatInput;
