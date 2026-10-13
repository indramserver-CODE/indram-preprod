export default function Modal({ open, title, onClose, onConfirm, confirmLabel = 'Confirm', children }) {
  if (!open) return null;

  return (
    <div
      style={{
        display: 'flex',
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.5)',
        zIndex: 1000,
        alignItems: 'center',
        justifyContent: 'center',
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: '#ffffff',
          border: '1px solid rgba(0,0,0,0.08)',
          borderRadius: 12,
          padding: 32,
          width: '100%',
          maxWidth: 480,
          boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
        }}
        onClick={e => e.stopPropagation()}
      >
        <h2 style={{ fontFamily: "'Outfit', sans-serif", fontSize: 18, fontWeight: 700, color: '#1a202c', marginBottom: 20 }}>{title}</h2>
        <div>{children}</div>
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 24 }}>
          <button
            onClick={onClose}
            style={{
              padding: '9px 20px',
              border: '1.5px solid rgba(0,0,0,0.14)',
              borderRadius: 8,
              background: '#ffffff',
              color: '#4a5568',
              fontSize: 14,
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            style={{
              padding: '9px 20px',
              border: 'none',
              borderRadius: 8,
              background: '#00ff41',
              color: '#051005',
              fontSize: 14,
              fontWeight: 700,
              cursor: 'pointer',
            }}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
