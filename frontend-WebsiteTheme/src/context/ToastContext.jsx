import { createContext, useCallback, useContext, useRef, useState } from 'react';

const ToastContext = createContext(null);

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const idRef = useRef(0);

  const showToast = useCallback((msg, type = 'success') => {
    const id = ++idRef.current;
    setToasts(prev => [...prev, { id, msg, type }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 3500);
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div
        style={{
          position: 'fixed',
          top: 20,
          right: 20,
          zIndex: 9999,
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
        }}
      >
        {toasts.map(t => (
          <div
            key={t.id}
            style={{
              padding: '12px 18px',
              borderRadius: 8,
              fontSize: 14,
              fontWeight: 500,
              fontFamily: "'Inter', sans-serif",
              boxShadow: '0 8px 24px rgba(0,0,0,0.15)',
              minWidth: 220,
              background: '#ffffff',
              border: t.type === 'success' ? '1px solid #bbf7d0' : '1px solid #fecaca',
              color: t.type === 'success' ? '#15803d' : '#c53030',
            }}
          >
            {t.msg}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within a ToastProvider');
  return ctx;
}
