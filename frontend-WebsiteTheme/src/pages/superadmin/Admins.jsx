import { useState } from 'react';
import { api } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import Modal from '../../components/common/Modal';
import SocietySelector from '../../components/common/SocietySelector';

export default function Admins() {
  const { showToast } = useToast();
  const [societyId, setSocietyId] = useState(null);
  const [admins, setAdmins] = useState([]);
  const [loading, setLoading] = useState(false);

  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState({ email: '', password: '', fullName: '' });

  const [editTarget, setEditTarget] = useState(null);
  const [editForm, setEditForm] = useState({ fullName: '', email: '', password: '', isActive: true });

  const [removeTarget, setRemoveTarget] = useState(null);

  async function loadAdmins(sid = societyId) {
    if (!sid) return;
    setLoading(true);
    try {
      const data = await api('GET', `/api/society-admins/${sid}`);
      setAdmins(data);
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setLoading(false);
    }
  }

  function onSocietyChange(id) {
    setSocietyId(id);
    setAdmins([]);
    if (id) loadAdmins(id);
  }

  function openCreate() {
    setCreateForm({ email: '', password: '', fullName: '' });
    setCreateOpen(true);
  }

  async function handleCreate() {
    const email = createForm.email.trim();
    const password = createForm.password;
    const fullName = createForm.fullName.trim();
    if (!email || !password) {
      showToast('Email and password are required', 'error');
      return;
    }
    try {
      await api('POST', `/api/society-admins/${societyId}`, { email, password, full_name: fullName || null });
      setCreateOpen(false);
      showToast('Admin created');
      loadAdmins();
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  function openEdit(a) {
    setEditForm({ fullName: a.full_name || '', email: a.email || '', password: '', isActive: a.is_active });
    setEditTarget(a);
  }

  async function handleEdit() {
    const email = editForm.email.trim();
    if (!email) { showToast('Email is required', 'error'); return; }
    const body = {
      full_name: editForm.fullName.trim() || null,
      is_active: editForm.isActive,
    };
    if (email.toLowerCase() !== (editTarget.email || '').toLowerCase()) body.email = email;
    if (editForm.password) body.password = editForm.password;
    try {
      await api('PUT', `/api/society-admins/${societyId}/${editTarget.id}`, body);
      setEditTarget(null);
      showToast('Admin updated');
      loadAdmins();
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  async function handleRemove() {
    try {
      await api('DELETE', `/api/society-admins/${societyId}/${removeTarget.id}`);
      setRemoveTarget(null);
      showToast('Admin removed');
      loadAdmins();
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  return (
    <div>
      <div className="page-title" style={{ marginBottom: 20 }}>
        Society Admins
      </div>

      <SocietySelector value={societyId} onChange={onSocietyChange} />

      {societyId && (
        <>
          <div className="page-header">
            <div />
            <button className="btn btn-primary" onClick={openCreate}>
              + Add Admin
            </button>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr className="empty-row">
                    <td colSpan={6}>Loading…</td>
                  </tr>
                ) : admins.length === 0 ? (
                  <tr className="empty-row">
                    <td colSpan={6}>No admins for this society yet</td>
                  </tr>
                ) : (
                  admins.map(a => (
                    <tr key={a.id}>
                      <td>{a.id}</td>
                      <td>{a.full_name || '—'}</td>
                      <td>{a.email}</td>
                      <td>
                        <span className={`badge ${a.is_active ? 'badge-green' : 'badge-red'}`}>
                          {a.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td>{new Date(a.created_at).toLocaleDateString()}</td>
                      <td style={{ display: 'flex', gap: 8 }}>
                        <button className="btn btn-sm btn-secondary" onClick={() => openEdit(a)}>
                          Edit
                        </button>
                        <button className="btn btn-sm btn-danger" onClick={() => setRemoveTarget(a)}>
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      <Modal open={createOpen} title="Add Society Admin" onClose={() => setCreateOpen(false)} onConfirm={handleCreate}>
        <div className="form-group">
          <label>Email *</label>
          <input
            type="email"
            placeholder="admin@example.com"
            value={createForm.email}
            onChange={e => setCreateForm({ ...createForm, email: e.target.value })}
          />
        </div>
        <div className="form-group">
          <label>Password *</label>
          <input
            type="password"
            placeholder="Min 8 characters"
            value={createForm.password}
            onChange={e => setCreateForm({ ...createForm, password: e.target.value })}
          />
        </div>
        <div className="form-group">
          <label>Full Name</label>
          <input
            placeholder="Full name"
            value={createForm.fullName}
            onChange={e => setCreateForm({ ...createForm, fullName: e.target.value })}
          />
        </div>
      </Modal>

      <Modal open={!!editTarget} title="Edit Admin" onClose={() => setEditTarget(null)} onConfirm={handleEdit}>
        <div className="form-group">
          <label>Full Name</label>
          <input value={editForm.fullName} onChange={e => setEditForm({ ...editForm, fullName: e.target.value })} />
        </div>
        <div className="form-group">
          <label>Email</label>
          <input
            type="email"
            value={editForm.email}
            onChange={e => setEditForm({ ...editForm, email: e.target.value })}
          />
          <small style={{ fontSize: 12, color: '#718096', marginTop: 4, display: 'block' }}>
            Also their login. Bill and invoice emails go to this address.
          </small>
        </div>
        <div className="form-group">
          <label>
            New Password <span style={{ color: '#718096', fontWeight: 400 }}>(leave blank to keep)</span>
          </label>
          <input
            type="password"
            placeholder="New password"
            value={editForm.password}
            onChange={e => setEditForm({ ...editForm, password: e.target.value })}
          />
        </div>
        <div className="form-group">
          <label>Status</label>
          <select
            value={editForm.isActive ? 'true' : 'false'}
            onChange={e => setEditForm({ ...editForm, isActive: e.target.value === 'true' })}
          >
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </select>
        </div>
      </Modal>

      <Modal
        open={!!removeTarget}
        title="Remove Admin"
        onClose={() => setRemoveTarget(null)}
        onConfirm={handleRemove}
        confirmLabel="Remove"
      >
        <p style={{ color: '#4a5568', fontSize: 14 }}>
          Remove <strong>{removeTarget?.email}</strong> from this society?
          <br />
          Their account will not be deleted.
        </p>
      </Modal>
    </div>
  );
}
