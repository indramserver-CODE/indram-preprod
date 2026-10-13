import { useState } from 'react';
import { api } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import Modal from '../../components/common/Modal';
import SocietySelector from '../../components/common/SocietySelector';

const EMPTY_FORM = {
  meter_number: '',
  label: '',
  sanctioned_load: '',
  location: '',
};

export default function Meters() {
  const { showToast } = useToast();

  // Society selection
  const [societyId, setSocietyId]   = useState(null);
  const [societyName, setSocietyName] = useState('');
  const [meters, setMeters]         = useState([]);
  const [loading, setLoading]       = useState(false);

  // Create / Edit modal
  const [modalOpen, setModalOpen]   = useState(false);
  const [editTarget, setEditTarget] = useState(null);   // null = create, object = edit
  const [form, setForm]             = useState(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);

  // Delete confirmation
  const [deleteTarget, setDeleteTarget] = useState(null);

  // ── Data loading ──────────────────────────────────────────────────────

  async function loadMeters(sid = societyId) {
    if (!sid) return;
    setLoading(true);
    try {
      const data = await api('GET', `/api/meters/${sid}`);
      setMeters(data);
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setLoading(false);
    }
  }

  function onSocietyChange(id, name) {
    setSocietyId(id);
    setSocietyName(name || '');
    setMeters([]);
    if (id) loadMeters(id);
  }

  // ── Create / Edit ─────────────────────────────────────────────────────

  function openCreate() {
    setEditTarget(null);
    setForm(EMPTY_FORM);
    setModalOpen(true);
  }

  function openEdit(meter) {
    setEditTarget(meter);
    setForm({
      meter_number:    meter.meter_number,
      label:           meter.label,
      sanctioned_load: meter.sanctioned_load ?? '',
      location:        meter.location ?? '',
    });
    setModalOpen(true);
  }

  function closeModal() {
    setModalOpen(false);
    setEditTarget(null);
    setForm(EMPTY_FORM);
  }

  async function handleSubmit() {
    const { meter_number, label, sanctioned_load, location } = form;

    if (!meter_number.trim()) {
      showToast('Meter number is required', 'error'); return;
    }
    if (!label.trim()) {
      showToast('Label is required', 'error'); return;
    }

    const payload = {
      meter_number: meter_number.trim(),
      label:        label.trim(),
      sanctioned_load: sanctioned_load ? parseFloat(sanctioned_load) : null,
      location:     location.trim() || null,
    };

    setSubmitting(true);
    try {
      if (editTarget) {
        await api('PUT', `/api/meters/${editTarget.id}`, payload);
        showToast('Meter updated successfully');
      } else {
        await api('POST', `/api/meters/${societyId}`, payload);
        showToast('Meter created successfully');
      }
      closeModal();
      loadMeters();
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setSubmitting(false);
    }
  }

  // ── Delete ────────────────────────────────────────────────────────────

  async function handleDelete() {
    try {
      await api('DELETE', `/api/meters/${deleteTarget.id}`);
      setDeleteTarget(null);
      showToast('Meter deleted');
      loadMeters();
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  // ── Render ────────────────────────────────────────────────────────────

  return (
    <div>
      {/* Page header */}
      <div className="page-header" style={{ marginBottom: 20 }}>
        <div>
          <div className="page-title">Meters</div>
          <div style={{ fontSize: 13, color: '#4a5568', marginTop: 2 }}>
            Manage MSEB electricity meters per society
          </div>
        </div>
        {societyId && (
          <button className="btn btn-primary" onClick={openCreate}>
            + Add Meter
          </button>
        )}
      </div>

      {/* Society selector */}
      <SocietySelector
        value={societyId}
        onChange={(id, name) => onSocietyChange(id, name)}
      />

      {/* Info banner when a society is selected but has no meters */}
      {societyId && !loading && meters.length === 0 && (
        <div style={{
          background: 'rgba(0, 255, 65, 0.06)',
          border: '1px solid rgba(0, 255, 65, 0.2)',
          borderRadius: 12,
          padding: '24px 28px',
          marginBottom: 20,
          display: 'flex',
          alignItems: 'center',
          gap: 16,
        }}>
          <span style={{ fontSize: 32 }}>⚡</span>
          <div>
            <div style={{ fontWeight: 700, fontSize: 15, color: '#1a202c' }}>
              No meters yet for {societyName}
            </div>
            <div style={{ fontSize: 13, color: '#4a5568', marginTop: 4 }}>
              Add the MSEB electricity meters for this society. Chargers and billing are scoped per meter.
            </div>
          </div>
        </div>
      )}

      {/* Meters table */}
      {societyId && (meters.length > 0 || loading) && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Meter Number</th>
                <th>Label / Name</th>
                <th>Location</th>
                <th>Sanctioned Load</th>
                <th>Chargers</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr className="empty-row">
                  <td colSpan={6}>Loading meters…</td>
                </tr>
              ) : (
                meters.map(m => (
                  <tr key={m.id}>
                    <td>
                      <span style={{
                        fontFamily: 'monospace',
                        fontWeight: 700,
                        fontSize: 13,
                        background: '#f4f4f4',
                        padding: '2px 8px',
                        borderRadius: 6,
                      }}>
                        {m.meter_number}
                      </span>
                    </td>
                    <td>
                      <strong>{m.label}</strong>
                    </td>
                    <td style={{ color: '#4a5568' }}>
                      {m.location || <span style={{ color: '#a0aec0' }}>—</span>}
                    </td>
                    <td>
                      {m.sanctioned_load
                        ? <span>{parseFloat(m.sanctioned_load).toFixed(1)} <span style={{ color: '#718096', fontSize: 12 }}>kW</span></span>
                        : <span style={{ color: '#a0aec0' }}>—</span>
                      }
                    </td>
                    <td>
                      <span className={`badge ${m.charger_count > 0 ? 'badge-green' : 'badge-gray'}`}>
                        {m.charger_count ?? 0} charger{(m.charger_count ?? 0) !== 1 ? 's' : ''}
                      </span>
                    </td>
                    <td style={{ display: 'flex', gap: 8 }}>
                      <button
                        className="btn btn-sm btn-secondary"
                        onClick={() => openEdit(m)}
                      >
                        Edit
                      </button>
                      <button
                        className="btn btn-sm btn-danger"
                        onClick={() => setDeleteTarget(m)}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Create / Edit modal */}
      {modalOpen && (
        <div
          style={{
            display: 'flex', position: 'fixed', inset: 0,
            background: 'rgba(0,0,0,0.45)', zIndex: 1000,
            alignItems: 'center', justifyContent: 'center',
          }}
          onClick={closeModal}
        >
          <div
            style={{
              background: '#ffffff', borderRadius: 14,
              padding: 32, width: '100%', maxWidth: 500,
              boxShadow: '0 24px 64px rgba(0,0,0,0.25)',
              maxHeight: '90vh', overflowY: 'auto',
            }}
            onClick={e => e.stopPropagation()}
          >
            <h2 style={{ fontSize: 18, fontWeight: 700, color: '#1a202c', marginBottom: 4 }}>
              {editTarget ? '✏️ Edit Meter' : '⚡ Add New Meter'}
            </h2>
            <p style={{ fontSize: 13, color: '#4a5568', marginBottom: 24 }}>
              {editTarget
                ? `Editing meter for ${societyName}`
                : `Adding a new MSEB meter to ${societyName}`}
            </p>

            <div className="form-group">
              <label>Meter Number * <span style={{ fontWeight: 400, color: '#718096' }}>(MSEB physical meter ID)</span></label>
              <input
                type="text"
                placeholder="e.g. MH04-12345"
                value={form.meter_number}
                onChange={e => setForm({ ...form, meter_number: e.target.value })}
              />
            </div>

            <div className="form-group">
              <label>Label / Name * <span style={{ fontWeight: 400, color: '#718096' }}>(friendly display name)</span></label>
              <input
                type="text"
                placeholder="e.g. Block A, Tower 1, Wing East"
                value={form.label}
                onChange={e => setForm({ ...form, label: e.target.value })}
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div className="form-group">
                <label>Sanctioned Load (kW)</label>
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  placeholder="e.g. 50"
                  value={form.sanctioned_load}
                  onChange={e => setForm({ ...form, sanctioned_load: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label>Location</label>
                <input
                  type="text"
                  placeholder="e.g. Ground floor, Basement"
                  value={form.location}
                  onChange={e => setForm({ ...form, location: e.target.value })}
                />
              </div>
            </div>

            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 8 }}>
              <button
                onClick={closeModal}
                style={{
                  padding: '9px 20px', border: '1.5px solid rgba(0,0,0,0.12)',
                  borderRadius: 8, background: '#ffffff', color: '#4a5568',
                  fontSize: 14, cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleSubmit}
                disabled={submitting}
                style={{
                  padding: '9px 24px', border: 'none', borderRadius: 8,
                  background: submitting ? '#a0aec0' : '#00ff41',
                  color: '#051005', fontSize: 14, fontWeight: 700,
                  cursor: submitting ? 'not-allowed' : 'pointer',
                }}
              >
                {submitting
                  ? (editTarget ? 'Saving…' : 'Creating…')
                  : (editTarget ? 'Save Changes' : 'Create Meter')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete confirmation modal */}
      <Modal
        open={!!deleteTarget}
        title="Delete Meter"
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        confirmLabel="Delete"
      >
        <p style={{ color: '#4a5568', fontSize: 14, lineHeight: 1.6 }}>
          Delete meter <strong>{deleteTarget?.label}</strong>{' '}
          ({deleteTarget?.meter_number})?
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
          ⚠️ This will also delete all chargers and billing records associated with this meter. This action cannot be undone.
        </div>
      </Modal>
    </div>
  );
}
