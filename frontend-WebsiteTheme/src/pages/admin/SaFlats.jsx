import { useEffect, useMemo, useState } from 'react';
import { api } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import Modal from '../../components/common/Modal';
import { LiveStatusBadge } from '../../components/common/FaultBadges';

export default function SaFlats() {
  const { showToast } = useToast();
  const [societyName, setSocietyName] = useState('');
  const [flats, setFlats]             = useState([]);
  const [meters, setMeters]           = useState([]);
  const [loading, setLoading]         = useState(true);
  const [search, setSearch]           = useState('');
  const [meterFilter, setMeterFilter] = useState('');
  const [chargerFilter, setChargerFilter] = useState('');
  const [emailFilter, setEmailFilter]     = useState('');
  const [ownerFilter, setOwnerFilter]     = useState('');

  const [editTarget, setEditTarget] = useState(null);
  const [editForm, setEditForm]     = useState({ ownerName: '', email: '' });

  async function load() {
    setLoading(true);
    try {
      const [flatData, meterData] = await Promise.all([
        api('GET', '/api/sa/flats'),
        api('GET', '/api/sa/meters'),
      ]);
      setFlats(flatData);
      setMeters(meterData);
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    api('GET', '/api/usage/society').then(s => setSocietyName(s.name)).catch(() => {});
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Filter + search
  const filtered = useMemo(() => {
    let list = flats;
    const q = search.toLowerCase().trim();
    if (q) {
      list = list.filter(f =>
        (f.flat_number || '').toLowerCase().includes(q) ||
        (f.owner_name || '').toLowerCase().includes(q) ||
        (f.email || '').toLowerCase().includes(q)
      );
    }
    if (meterFilter) {
      list = list.filter(f => String(f.meter_id) === meterFilter);
    }
    if (chargerFilter) {
      list = list.filter(f => (chargerFilter === 'with') === !!f.charger_id);
    }
    if (emailFilter) {
      list = list.filter(f => (emailFilter === 'with') === !!f.email);
    }
    if (ownerFilter) {
      list = list.filter(f => (ownerFilter === 'with') === !!f.owner_name);
    }
    return list;
  }, [flats, search, meterFilter, chargerFilter, emailFilter, ownerFilter]);

  const filtersActive = !!(search || meterFilter || chargerFilter || emailFilter || ownerFilter);
  function clearFilters() {
    setSearch(''); setMeterFilter(''); setChargerFilter(''); setEmailFilter(''); setOwnerFilter('');
  }

  // Stats
  const withCharger    = flats.filter(f => f.charger_id).length;
  const withoutCharger = flats.length - withCharger;
  const withEmail      = flats.filter(f => f.email).length;

  // Edit handlers
  function openEdit(f) {
    setEditForm({ ownerName: f.owner_name || '', email: f.email || '' });
    setEditTarget(f);
  }

  async function handleEdit() {
    try {
      await api('PATCH', `/api/sa/flats/${editTarget.id}`, {
        owner_name: editForm.ownerName.trim() || null,
        email:      editForm.email.trim() || null,
      });
      setEditTarget(null);
      showToast('Flat updated successfully');
      load();
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  const multipleMeters = meters.length > 1;

  return (
    <div>
      {/* Header */}
      <div className="page-header">
        <div>
          <div className="page-title">Chargers</div>
          <div style={{ fontSize: 13, color: '#4a5568', marginTop: 2 }}>{societyName}</div>
        </div>
        <button className="btn btn-secondary" onClick={load}>
          🔄 Refresh
        </button>
      </div>

      {/* Summary strip */}
      {!loading && flats.length > 0 && (
        <div style={{
          display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap',
        }}>
          {[
            { label: 'Total Flats',       value: flats.length,    color: '#1a202c' },
            { label: 'With Charger',      value: withCharger,     color: '#15803d' },
            { label: 'No Charger Yet',    value: withoutCharger,  color: withoutCharger > 0 ? '#c53030' : '#a0aec0' },
            { label: 'Email Configured',  value: withEmail,       color: '#4338ca' },
          ].map(item => (
            <div key={item.label} style={{
              background: '#ffffff',
              border: '1px solid rgba(0,0,0,0.08)',
              borderRadius: 10, padding: '12px 18px',
              minWidth: 130,
            }}>
              <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: '#718096', marginBottom: 4 }}>
                {item.label}
              </div>
              <div style={{ fontSize: 22, fontWeight: 700, color: item.color }}>
                {item.value}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Search + meter filter bar */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
        <input
          type="text"
          placeholder="Search by flat number, owner or email…"
          style={{ maxWidth: 300, flex: '1 1 200px' }}
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        {multipleMeters && (
          <select
            value={meterFilter}
            onChange={e => setMeterFilter(e.target.value)}
            style={{ maxWidth: 260, flex: '0 1 260px' }}
          >
            <option value="">All Meters</option>
            {meters.map(m => (
              <option key={m.id} value={String(m.id)}>
                {m.label} ({m.meter_number})
              </option>
            ))}
          </select>
        )}
        <select value={chargerFilter} onChange={e => setChargerFilter(e.target.value)} style={{ maxWidth: 180, flex: '0 1 180px' }}>
          <option value="">All Chargers</option>
          <option value="with">With charger</option>
          <option value="without">No charger</option>
        </select>
        <select value={emailFilter} onChange={e => setEmailFilter(e.target.value)} style={{ maxWidth: 190, flex: '0 1 190px' }}>
          <option value="">All Billing Emails</option>
          <option value="with">Email configured</option>
          <option value="without">Email missing</option>
        </select>
        <select value={ownerFilter} onChange={e => setOwnerFilter(e.target.value)} style={{ maxWidth: 180, flex: '0 1 180px' }}>
          <option value="">All Owners</option>
          <option value="with">Owner name set</option>
          <option value="without">Owner name missing</option>
        </select>
        {filtersActive && (
          <button className="btn btn-sm btn-secondary" onClick={clearFilters}>
            Clear filters
          </button>
        )}
        {filtersActive && (
          <span style={{ fontSize: 13, color: '#718096' }}>
            {filtered.length} of {flats.length} flats
          </span>
        )}
      </div>

      {/* Flats table */}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Flat No.</th>
              {multipleMeters && <th>Meter</th>}
              <th>Charger ID</th>
              <th>Charger Status</th>
              <th>Owner Name</th>
              <th>Billing Email</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr className="empty-row">
                <td colSpan={multipleMeters ? 7 : 6}>Loading…</td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr className="empty-row">
                <td colSpan={multipleMeters ? 7 : 6}>
                  {flats.length === 0 ? 'No flats found' : 'No flats match your filters'}
                </td>
              </tr>
            ) : (
              filtered.map(f => (
                <tr key={f.id}>
                  <td>
                    <strong>{f.flat_number}</strong>
                  </td>
                  {multipleMeters && (
                    <td>
                      {f.meter_label
                        ? <span className="badge badge-blue">{f.meter_label}</span>
                        : <span style={{ color: '#a0aec0', fontSize: 13 }}>—</span>
                      }
                    </td>
                  )}
                  <td>
                    {f.charger_id
                      ? <code style={{ fontSize: 12, background: '#f4f4f4', padding: '2px 6px', borderRadius: 4 }}>{f.charger_id}</code>
                      : <span style={{ color: '#c53030', fontSize: 13 }}>No charger</span>
                    }
                  </td>
                  <td>
                    {f.charger_id
                      ? <LiveStatusBadge status={f.charger_status} faultCode={f.fault_code} />
                      : <span style={{ color: '#a0aec0' }}>—</span>
                    }
                  </td>
                  <td>{f.owner_name || <span style={{ color: '#a0aec0' }}>—</span>}</td>
                  <td style={{ fontSize: 13 }}>
                    {f.email
                      ? <span style={{ color: '#4a5568' }}>{f.email}</span>
                      : <span style={{ color: '#c53030', fontSize: 12 }}>⚠️ No email</span>
                    }
                  </td>
                  <td>
                    <button className="btn btn-sm btn-secondary" onClick={() => openEdit(f)}>
                      Edit
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>

        {/* Footer note about missing emails */}
        {!loading && withoutCharger === 0 && withEmail < flats.length && (
          <div style={{
            padding: '10px 16px',
            borderTop: '1px solid rgba(0,0,0,0.06)',
            fontSize: 12,
            color: '#c53030',
            background: '#fff5f5',
          }}>
            ⚠️ {flats.length - withEmail} flat{flats.length - withEmail !== 1 ? 's' : ''} missing a billing email — they won't receive monthly bills.
          </div>
        )}
      </div>

      {/* Edit modal */}
      <Modal
        open={!!editTarget}
        title={`Edit Flat ${editTarget?.flat_number || ''}`}
        onClose={() => setEditTarget(null)}
        onConfirm={handleEdit}
        confirmLabel="Save Changes"
      >
        {editTarget?.meter_label && (
          <div style={{
            background: '#f0f9ff',
            border: '1px solid #bae6fd',
            borderRadius: 8,
            padding: '8px 12px',
            fontSize: 13,
            color: '#0369a1',
            marginBottom: 16,
          }}>
            ⚡ Meter: {editTarget.meter_label}
            {editTarget.charger_id && (
              <span style={{ marginLeft: 10, color: '#4a5568' }}>
                · Charger: <code>{editTarget.charger_id}</code>
              </span>
            )}
          </div>
        )}
        <div className="form-group">
          <label>Owner Name</label>
          <input
            placeholder="Full name of owner / resident"
            value={editForm.ownerName}
            onChange={e => setEditForm({ ...editForm, ownerName: e.target.value })}
          />
        </div>
        <div className="form-group">
          <label>Billing Email</label>
          <input
            type="email"
            placeholder="billing@example.com"
            value={editForm.email}
            onChange={e => setEditForm({ ...editForm, email: e.target.value })}
          />
          <small style={{ fontSize: 12, color: '#718096', marginTop: 4, display: 'block' }}>
            Monthly bills will be sent to this email address.
          </small>
        </div>
      </Modal>
    </div>
  );
}