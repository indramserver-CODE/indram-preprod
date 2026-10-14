import { useState } from 'react';
import { api } from '../../api/client';
import { useToast } from '../../context/ToastContext';

// Super admin "Delete all" for one society. Shows what will be deleted (or why it can't be),
// and the delete button only enables once the society's name is typed.

const LABELS = { flats: 'flats', chargers: 'chargers', rfid_cards: 'RFID cards' };
const TITLES = { flats: 'Delete all flats', chargers: 'Delete all chargers', rfid: 'Delete all RFID cards' };

export default function DeleteAllButton({ societyId, scope, onDone }) {
  const { showToast } = useToast();
  const [preview, setPreview] = useState(null);
  const [typed, setTyped]     = useState('');
  const [busy, setBusy]       = useState(false);

  async function open() {
    try {
      setTyped('');
      setPreview(await api('GET', `/api/societies/${societyId}/delete-all/${scope}`));
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  async function confirm() {
    setBusy(true);
    try {
      await api('DELETE', `/api/societies/${societyId}/delete-all/${scope}`, { confirm_name: typed });
      showToast(`Deleted: ${summary(preview.counts)} from ${preview.society_name}`);
      setPreview(null);
      onDone?.();
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  const matches = preview && typed.trim().toLowerCase() === preview.society_name.trim().toLowerCase();

  return (
    <>
      <button className="btn btn-danger" onClick={open} disabled={!societyId}>Delete all</button>

      {preview && (
        <div
          style={{ display: 'flex', position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1000,
                   alignItems: 'center', justifyContent: 'center' }}
          onClick={() => !busy && setPreview(null)}
        >
          <div
            style={{ background: '#ffffff', borderRadius: 12, padding: 28, width: '100%', maxWidth: 480,
                     maxHeight: '90vh', overflowY: 'auto', boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }}
            onClick={e => e.stopPropagation()}
          >
            <h2 style={{ fontSize: 18, fontWeight: 700, color: '#1a202c', marginBottom: 6 }}>{TITLES[scope]}</h2>
            <div style={{ fontSize: 14, color: '#4a5568', marginBottom: 16 }}>{preview.society_name}</div>

            {preview.blocked ? (
              <div style={{ background: '#fffbeb', border: '1px solid #fcd34d', borderRadius: 8, padding: '12px 14px',
                            fontSize: 13, color: '#92400e', marginBottom: 8 }}>
                {preview.blocked}
              </div>
            ) : (
              <>
                <div style={{ background: '#fff5f5', border: '1px solid #fed7d7', borderRadius: 8, padding: '12px 14px',
                              fontSize: 13, color: '#c53030', marginBottom: 12 }}>
                  This permanently deletes <strong>{summary(preview.counts)}</strong>. It can't be undone.
                </div>
                {preview.warning && (
                  <div style={{ fontSize: 13, color: '#4a5568', marginBottom: 12 }}>{preview.warning}</div>
                )}
                <div className="form-group">
                  <label>Type <strong>{preview.society_name}</strong> to confirm</label>
                  <input value={typed} autoFocus onChange={e => setTyped(e.target.value)}
                         placeholder={preview.society_name} />
                </div>
              </>
            )}

            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 16 }}>
              <button className="btn btn-secondary" onClick={() => setPreview(null)} disabled={busy}>
                {preview.blocked ? 'Close' : 'Cancel'}
              </button>
              {!preview.blocked && (
                <button className="btn btn-danger" onClick={confirm} disabled={!matches || busy}>
                  {busy ? 'Deleting…' : TITLES[scope]}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function summary(counts) {
  return Object.entries(counts)
    .filter(([, n]) => n > 0)
    .map(([k, n]) => `${n} ${LABELS[k] || k}`)
    .join(', ');
}
