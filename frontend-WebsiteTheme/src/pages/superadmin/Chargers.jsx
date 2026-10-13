import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import Modal from '../../components/common/Modal';
import SocietySelector from '../../components/common/SocietySelector';
import CsvUploadPanel from '../../components/common/CsvUploadPanel';

const SAMPLE_CSV = 'flat_number,charger_id,meter_number\nA101,EZC001,MH04-12345\nA102,EZC002,MH04-12345\nB201,EZC003,MH04-67890\n';

export default function Chargers() {
  const { showToast } = useToast();

  const [societyId, setSocietyId] = useState(null);
  const [chargers, setChargers] = useState([]);
  const [meters, setMeters] = useState([]);      // for label lookup + filter
  const [meterFilter, setMeterFilter] = useState('');    // '' = all
  const [loading, setLoading] = useState(false);
  const [bulkAction, setBulkAction] = useState(null);   // 'deactivate' | 'activate' | null

  // ── Load both chargers and meters when society changes ────────────────

  const [flats, setFlats] = useState([]);

  async function loadData(sid = societyId) {
    if (!sid) return;
    setLoading(true);
    try {
      const [chargerData, meterData, flatData] = await Promise.all([
        api('GET', `/api/chargers/${sid}`),
        api('GET', `/api/meters/${sid}`),
        api('GET', `/api/societies/${sid}/flats`),
      ]);
      setChargers(chargerData);
      setMeters(meterData);
      setFlats(flatData);
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setLoading(false);
    }
  }

  function onSocietyChange(id) {
    setSocietyId(id);
    setChargers([]);
    setMeters([]);
    setFlats([]);
    setMeterFilter('');
    if (id) loadData(id);
  }

  // Build meter_id → meter object map for fast label lookup
  const meterMap = Object.fromEntries(meters.map(m => [m.id, m]));
  // Build flat_id → flat_number map so we show flat number not raw ID
  const flatMap = Object.fromEntries(flats.map(f => [f.id, f.flat_number]));

  // ── Derive real charger status from is_active + last_seen_at ─────
  // Four states:
  //   not_commissioned — never connected (last_seen_at is null)
  //   online           — is_active and last seen < 5 minutes ago
  //   offline          — is_active but last seen > 5 minutes ago
  //   deactivated      — is_active=false (manually disabled)
  function chargerStatus(c) {
    // A society-wide command is queued but this charger hasn't confirmed it yet
    if (c.pending_cmd === 'DEACTIVATE_ALL') return 'deactivating';
    if (c.pending_cmd === 'ACTIVATE_ALL') return 'activating';
    if (!c.is_active) return c.still_locked ? 'still_locked' : 'deactivated';
    if (!c.last_seen_at) return 'not_commissioned';
    const diffMin = (Date.now() - new Date(c.last_seen_at).getTime()) / 60000;
    return diffMin < 5 ? 'online' : 'offline';
  }

  const STATUS_CONFIG = {
    not_commissioned: { label: 'Not Commissioned', badge: 'badge-amber', dot: '#d97706' },
    online: { label: 'Online', badge: 'badge-green', dot: '#15803d' },
    offline: { label: 'Offline', badge: 'badge-red', dot: '#c53030' },
    deactivated: { label: 'Deactivated', badge: 'badge-gray', dot: '#718096' },
    deactivating: { label: 'Deactivation pending', badge: 'badge-amber', dot: '#d97706' },
    activating: { label: 'Activation pending', badge: 'badge-amber', dot: '#d97706' },
    still_locked: { label: 'Still locked (other reason)', badge: 'badge-red', dot: '#c53030' },
  };

  // Apply meter filter
  const visibleChargers = meterFilter
    ? chargers.filter(c => String(c.meter_id) === meterFilter)
    : chargers;

  // ── Actions ───────────────────────────────────────────────────────────

  async function handleBulk() {
    const path = bulkAction === 'deactivate' ? 'deactivate-all' : 'activate-all';
    try {
      const res = await api('POST', `/api/chargers/${societyId}/${path}`);
      setBulkAction(null);
      showToast(
        res.broadcast_sent
          ? `${bulkAction === 'deactivate' ? 'Deactivate' : 'Activate'} command sent to ${res.chargers} chargers. Offline chargers will be updated when they reconnect.`
          : 'Broadcast failed — command queued and will be sent as chargers reconnect',
        res.broadcast_sent ? 'success' : 'error'
      );
      setTimeout(() => loadData(), 3000);
    } catch (e) {
      setBulkAction(null);
      showToast(e.message, 'error');
    }
  }

  // Keep refreshing while any charger is still waiting to confirm a society-wide command
  const anyPending = chargers.some(c => c.pending_cmd);
  useEffect(() => {
    if (!anyPending) return;
    const t = setInterval(() => loadData(), 10000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anyPending, societyId]);

  // ── Render ────────────────────────────────────────────────────────────

  return (
    <div>
      <div className="page-header" style={{ marginBottom: 20 }}>
        <div>
          <div className="page-title">Chargers</div>
          <div style={{ fontSize: 13, color: '#4a5568', marginTop: 2 }}>
            Manage charger devices — each charger is assigned to a meter and a flat
          </div>
        </div>
      </div>

      <SocietySelector value={societyId} onChange={onSocietyChange} />

      {societyId && (
        <>
          {/* CSV upload */}
          <CsvUploadPanel
            title="📤 Bulk Upload Chargers (CSV)"
            hint={
              <span>
                Required columns:{' '}
                <code>flat_number</code>,{' '}
                <code>charger_id</code>,{' '}
                <code>meter_number</code>
                <span style={{ color: '#718096' }}>
                  {' '}— meter_number must match an existing meter in this society
                </span>
              </span>
            }
            uploadPath={`/api/chargers/${societyId}/csv`}
            sampleCsv={SAMPLE_CSV}
            sampleFilename="chargers_sample.csv"
            skippedKey="charger_id"
            onUploaded={() => loadData()}
          />

          {/* Society-wide lock / unlock */}
          <div style={{ display: 'flex', gap: 10, marginBottom: 16, alignItems: 'center', flexWrap: 'wrap' }}>
            <button
              className="btn"
              style={{ background: '#dc2626', border: '1.5px solid #dc2626', color: '#fff' }}
              onClick={() => setBulkAction('deactivate')}
              disabled={chargers.length === 0}
            >
              Deactivate All
            </button>
            <button
              className="btn"
              style={{ background: '#16a34a', border: '1.5px solid #16a34a', color: '#fff' }}
              onClick={() => setBulkAction('activate')}
              disabled={chargers.length === 0}
            >
              Reactivate All
            </button>
            {anyPending && (
              <span style={{ fontSize: 13, color: '#d97706' }}>
                {chargers.filter(c => c.pending_cmd).length} charger(s) waiting to confirm — offline chargers are updated when they reconnect
              </span>
            )}
          </div>

          {/* Meter filter bar — only show if there are multiple meters */}
          {meters.length > 1 && (
            <div className="selector-bar" style={{ marginBottom: 16 }}>
              <label style={{ margin: 0, whiteSpace: 'nowrap' }}>⚡ Filter by Meter:</label>
              <select
                value={meterFilter}
                onChange={e => setMeterFilter(e.target.value)}
                style={{ maxWidth: 300 }}
              >
                <option value="">All Meters ({chargers.length} chargers)</option>
                {meters.map(m => {
                  const count = chargers.filter(c => c.meter_id === m.id).length;
                  return (
                    <option key={m.id} value={String(m.id)}>
                      {m.label} ({m.meter_number}) — {count} charger{count !== 1 ? 's' : ''}
                    </option>
                  );
                })}
              </select>
              {meterFilter && (
                <button
                  className="btn btn-sm btn-secondary"
                  onClick={() => setMeterFilter('')}
                >
                  Clear filter
                </button>
              )}
            </div>
          )}

          {/* Chargers table */}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Charger ID</th>
                  <th>Meter</th>
                  <th>Flat No.</th>
                  <th>FW Version</th>
                  <th>Status</th>
                  <th>Last Seen</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr className="empty-row">
                    <td colSpan={6}>Loading…</td>
                  </tr>
                ) : visibleChargers.length === 0 ? (
                  <tr className="empty-row">
                    <td colSpan={6}>
                      {chargers.length === 0
                        ? 'No chargers yet — upload a CSV to get started'
                        : 'No chargers match the selected filter'}
                    </td>
                  </tr>
                ) : (
                  visibleChargers.map(c => {
                    const meter = meterMap[c.meter_id];
                    return (
                      <tr key={c.charger_id}>
                        <td>
                          <span style={{
                            fontFamily: 'monospace',
                            fontWeight: 700,
                            fontSize: 13,
                            background: '#f4f4f4',
                            padding: '2px 8px',
                            borderRadius: 6,
                          }}>
                            {c.charger_id}
                          </span>
                        </td>
                        <td>
                          {meter ? (
                            <div>
                              <div style={{ fontWeight: 600, fontSize: 13 }}>{meter.label}</div>
                              <div style={{ fontSize: 11, color: '#718096', marginTop: 1 }}>
                                {meter.meter_number}
                              </div>
                            </div>
                          ) : (
                            <span style={{ color: '#a0aec0' }}>—</span>
                          )}
                        </td>
                        <td style={{ color: '#4a5568' }}>
                          <strong>{flatMap[c.flat_id] || <span style={{ color: '#a0aec0' }}>—</span>}</strong>
                        </td>
                        <td style={{ color: '#4a5568' }}>{c.fw_version || '—'}</td>
                        <td>
                          {(() => {
                            const s = chargerStatus(c);
                            const cfg = STATUS_CONFIG[s];
                            return (
                              <span className={`badge ${cfg.badge}`}>
                                {cfg.label}
                              </span>
                            );
                          })()}
                        </td>
                        <td style={{ fontSize: 13, color: '#4a5568' }}>
                          {c.last_seen_at
                            ? new Date(c.last_seen_at).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' })
                            : <span style={{ color: '#a0aec0' }}>Never</span>}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>

            {/* Row count footer */}
            {!loading && chargers.length > 0 && (
              <div style={{
                padding: '10px 16px',
                borderTop: '1px solid rgba(0,0,0,0.06)',
                fontSize: 12,
                color: '#718096',
                display: 'flex',
                gap: 16,
                flexWrap: 'wrap',
              }}>
                <span>Total: <strong>{chargers.length}</strong></span>
                {meterFilter && (
                  <span>Showing: <strong>{visibleChargers.length}</strong> in selected meter</span>
                )}
                <span style={{ color: '#15803d' }}>
                  Online: <strong>{chargers.filter(c => chargerStatus(c) === 'online').length}</strong>
                </span>
                <span style={{ color: '#d97706' }}>
                  Not Commissioned: <strong>{chargers.filter(c => chargerStatus(c) === 'not_commissioned').length}</strong>
                </span>
                <span style={{ color: '#c53030' }}>
                  Offline: <strong>{chargers.filter(c => chargerStatus(c) === 'offline').length}</strong>
                </span>
                <span style={{ color: '#718096' }}>
                  Deactivated: <strong>{chargers.filter(c => chargerStatus(c) === 'deactivated').length}</strong>
                </span>
              </div>
            )}
          </div>
        </>
      )}

      {/* Bulk confirmation */}
      <Modal
        open={!!bulkAction}
        title={bulkAction === 'deactivate' ? 'Deactivate all chargers' : 'Reactivate all chargers'}
        onClose={() => setBulkAction(null)}
        onConfirm={handleBulk}
        confirmLabel={bulkAction === 'deactivate' ? 'Deactivate All' : 'Reactivate All'}
      >
        <p>
          {bulkAction === 'deactivate'
            ? 'Every charger in this society will stop any running session (billed up to now) and be locked. Chargers that are offline will be locked as soon as they reconnect.'
            : 'The society-wide lock will be removed from every charger. Chargers that are offline will be updated as soon as they reconnect.'}
        </p>
      </Modal>
    </div>
  );
}