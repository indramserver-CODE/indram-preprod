import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import Modal from '../../components/common/Modal';

const DEFAULT_INDRAM_RATE = '1.50';

const EMPTY_CREATE = { name: '', address: '', indram_rate: DEFAULT_INDRAM_RATE };
const EMPTY_EDIT   = { name: '', address: '', indram_rate: '' };

export default function Societies() {
  const { showToast } = useToast();
  const [societies, setSocieties]     = useState([]);
  const [loading, setLoading]         = useState(true);
  const [createOpen, setCreateOpen]   = useState(false);
  const [createForm, setCreateForm]   = useState(EMPTY_CREATE);
  const [editTarget, setEditTarget]   = useState(null);
  const [editForm, setEditForm]       = useState(EMPTY_EDIT);
  const [deleteTarget, setDeleteTarget] = useState(null);

  async function load() {
    setLoading(true);
    try {
      const data = await api('GET', '/api/societies');
      setSocieties(data);
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Create ────────────────────────────────────────────────────────────

  function openCreate() {
    setCreateForm(EMPTY_CREATE);
    setCreateOpen(true);
  }

  async function handleCreate() {
    const name = createForm.name.trim();
    if (!name) { showToast('Name is required', 'error'); return; }

    const rate = createForm.indram_rate.trim();
    if (rate && (isNaN(parseFloat(rate)) || parseFloat(rate) < 0)) {
      showToast('INDRAM rate must be a positive number', 'error'); return;
    }

    try {
      await api('POST', '/api/societies', {
        name,
        address:     createForm.address.trim() || null,
        indram_rate: rate ? parseFloat(rate) : null,
      });
      setCreateOpen(false);
      showToast('Society created');
      load();
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  // ── Edit ──────────────────────────────────────────────────────────────

  function openEdit(s) {
    setEditForm({
      name:        s.name,
      address:     s.address || '',
      indram_rate: s.indram_rate !== null && s.indram_rate !== undefined
                     ? String(parseFloat(s.indram_rate))
                     : '',
    });
    setEditTarget(s);
  }

  async function handleEdit() {
    const name = editForm.name.trim();
    if (!name) { showToast('Name is required', 'error'); return; }

    const rate = editForm.indram_rate.trim();
    if (rate && (isNaN(parseFloat(rate)) || parseFloat(rate) < 0)) {
      showToast('INDRAM rate must be a positive number', 'error'); return;
    }

    try {
      await api('PUT', `/api/societies/${editTarget.id}`, {
        name,
        address:     editForm.address.trim() || null,
        indram_rate: rate ? parseFloat(rate) : null,
      });
      setEditTarget(null);
      showToast('Society updated');
      load();
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  // ── Delete ────────────────────────────────────────────────────────────

  async function handleDelete() {
    try {
      await api('DELETE', `/api/societies/${deleteTarget.id}`);
      setDeleteTarget(null);
      showToast('Society deleted');
      load();
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  // ── Helpers ───────────────────────────────────────────────────────────

  function IndramRateField({ value, onChange }) {
    return (
      <div className="form-group">
        <label>
          INDRAM Rate (₹ / kWh)
          <span style={{ fontWeight: 400, color: '#718096', marginLeft: 6 }}>
            (default ₹{DEFAULT_INDRAM_RATE} if left blank)
          </span>
        </label>
        <div style={{ position: 'relative' }}>
          <span style={{
            position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)',
            color: '#4a5568', fontWeight: 600, fontSize: 14, pointerEvents: 'none',
          }}>
            ₹
          </span>
          <input
            type="number"
            step="0.01"
            min="0"
            placeholder={DEFAULT_INDRAM_RATE}
            value={value}
            onChange={e => onChange(e.target.value)}
            style={{ paddingLeft: 28 }}
          />
        </div>
        <small style={{ fontSize: 12, color: '#718096', marginTop: 4, display: 'block' }}>
          This is the platform service charge added to every flat's electricity bill per kWh consumed.
          Applied uniformly across all meters in this society.
        </small>
      </div>
    );
  }

  // ── Render ────────────────────────────────────────────────────────────

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Societies</div>
          <div style={{ fontSize: 13, color: '#4a5568', marginTop: 2 }}>
            Manage societies and their INDRAM billing rates
          </div>
        </div>
        <button className="btn btn-primary" onClick={openCreate}>
          + Add Society
        </button>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Name</th>
              <th>Address</th>
              <th>INDRAM Rate</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr className="empty-row">
                <td colSpan={6}>Loading…</td>
              </tr>
            ) : societies.length === 0 ? (
              <tr className="empty-row">
                <td colSpan={6}>No societies yet</td>
              </tr>
            ) : (
              societies.map(s => (
                <tr key={s.id}>
                  <td>{s.id}</td>
                  <td><strong>{s.name}</strong></td>
                  <td style={{ color: '#4a5568' }}>{s.address || '—'}</td>
                  <td>
                    {s.indram_rate !== null && s.indram_rate !== undefined ? (
                      <span style={{
                        fontWeight: 700,
                        color: '#15803d',
                        background: 'rgba(0,255,65,0.08)',
                        border: '1px solid rgba(0,255,65,0.2)',
                        borderRadius: 6,
                        padding: '2px 8px',
                        fontSize: 13,
                      }}>
                        ₹{parseFloat(s.indram_rate).toFixed(4)}/kWh
                      </span>
                    ) : (
                      <span style={{
                        color: '#718096', fontSize: 13,
                        fontStyle: 'italic',
                      }}>
                        default ₹{DEFAULT_INDRAM_RATE}
                      </span>
                    )}
                  </td>
                  <td style={{ fontSize: 13, color: '#4a5568' }}>
                    {new Date(s.created_at).toLocaleDateString()}
                  </td>
                  <td style={{ display: 'flex', gap: 8 }}>
                    <button className="btn btn-sm btn-secondary" onClick={() => openEdit(s)}>
                      Edit
                    </button>
                    <button className="btn btn-sm btn-danger" onClick={() => setDeleteTarget(s)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Create modal */}
      <Modal
        open={createOpen}
        title="Add Society"
        onClose={() => setCreateOpen(false)}
        onConfirm={handleCreate}
      >
        <div className="form-group">
          <label>Name *</label>
          <input
            placeholder="Society name"
            value={createForm.name}
            onChange={e => setCreateForm({ ...createForm, name: e.target.value })}
          />
        </div>
        <div className="form-group">
          <label>Address</label>
          <input
            placeholder="Full address"
            value={createForm.address}
            onChange={e => setCreateForm({ ...createForm, address: e.target.value })}
          />
        </div>
        <IndramRateField
          value={createForm.indram_rate}
          onChange={v => setCreateForm({ ...createForm, indram_rate: v })}
        />
      </Modal>

      {/* Edit modal */}
      <Modal
        open={!!editTarget}
        title={`Edit Society — ${editTarget?.name || ''}`}
        onClose={() => setEditTarget(null)}
        onConfirm={handleEdit}
      >
        <div className="form-group">
          <label>Name *</label>
          <input
            value={editForm.name}
            onChange={e => setEditForm({ ...editForm, name: e.target.value })}
          />
        </div>
        <div className="form-group">
          <label>Address</label>
          <input
            value={editForm.address}
            onChange={e => setEditForm({ ...editForm, address: e.target.value })}
          />
        </div>
        <IndramRateField
          value={editForm.indram_rate}
          onChange={v => setEditForm({ ...editForm, indram_rate: v })}
        />
      </Modal>

      {/* Delete modal */}
      <Modal
        open={!!deleteTarget}
        title="Delete Society"
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        confirmLabel="Delete"
      >
        <p style={{ color: '#4a5568', fontSize: 14 }}>
          Are you sure you want to delete <strong>{deleteTarget?.name}</strong>?
        </p>
        <div style={{
          marginTop: 12,
          background: '#fff5f5',
          border: '1px solid #fed7d7',
          borderRadius: 8,
          padding: '10px 14px',
          fontSize: 13,
          color: '#c53030',
        }}>
          ⚠️ This will also delete all meters, flats, chargers, RFID cards and billing records.
        </div>
      </Modal>
    </div>
  );
}