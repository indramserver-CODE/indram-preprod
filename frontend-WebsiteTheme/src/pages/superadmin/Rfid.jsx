import { useState } from 'react';
import { api } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import Modal from '../../components/common/Modal';
import SocietySelector from '../../components/common/SocietySelector';
import CsvUploadPanel from '../../components/common/CsvUploadPanel';

// Two UIDs per row — uid2 and label2 are optional
const SAMPLE_CSV =
  'flat_number,uid,label,uid2,label2\n' +
  'A101,14AF7D05,Owner Card,2B3C4D5E,Spouse Card\n' +
  'A102,9F8E7D6C,Car Key,,\n' +
  'B201,AA1122BB,Primary,,\n';

// ── Operation states (per-flat) ───────────────────────────────────────
const OP = {
  IDLE: 'idle',
  CHECKING: 'checking',
  OFFLINE_BLOCK: 'offline_block',
  OFFLINE_QUEUE: 'offline_queue',
  SENDING: 'sending',
  QUEUED: 'queued',
  REJECTED: 'rejected',
  SUCCESS: 'success',
};

function parseApiError(e) {
  const detail = e.detail || {};
  return {
    status: e.status,
    code: detail.code,
    message: detail.message || e.message,
    hint: detail.hint,
    reason: detail.reason,
    queued: detail.queued,
    canQueue: detail.can_queue,
  };
}

export default function Rfid() {
  const { showToast } = useToast();

  const [societyId, setSocietyId] = useState(null);
  const [cards, setCards] = useState([]);
  const [flats, setFlats] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [deleteTarget, setDeleteTarget] = useState(null);

  // Per-flat op state
  const [flatOps, setFlatOps] = useState({});

  // Modals
  const [deactivateTarget, setDeactivateTarget] = useState(null);
  const [activateTarget, setActivateTarget] = useState(null);
  const [addCardTarget, setAddCardTarget] = useState(null);
  const [addForm, setAddForm] = useState({ uid: '', label: '' });
  const [queueConfirm, setQueueConfirm] = useState(null);

  // ── Data loading ──────────────────────────────────────────────────

  async function loadData(sid = societyId) {
    if (!sid) return;
    setLoading(true);
    try {
      const [cardData, flatData] = await Promise.all([
        api('GET', `/api/rfid/${sid}`),
        api('GET', `/api/societies/${sid}/flats`),
      ]);
      setCards(cardData);
      setFlats(flatData);
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setLoading(false);
    }
  }

  function onSocietyChange(id) {
    setSocietyId(id);
    setCards([]);
    setFlats([]);
    setSearch('');
    setFlatOps({});
    if (id) loadData(id);
  }

  // ── Grouped structure ─────────────────────────────────────────────

  const groups = (() => {
    const map = {};
    flats.forEach(f => {
      map[f.id] = {
        flat_id: f.id,
        flat_number: f.flat_number,
        charger_id: f.charger_id || null,
        cards: [],
      };
    });
    cards.forEach(c => {
      if (map[c.flat_id]) map[c.flat_id].cards.push(c);
    });
    let list = Object.values(map);
    const q = search.toLowerCase().trim();
    if (q) {
      list = list.filter(g =>
        (g.flat_number || '').toLowerCase().includes(q) ||
        g.cards.some(c => (c.uid || '').toLowerCase().includes(q))
      );
    }
    return list.sort((a, b) => a.flat_number.localeCompare(b.flat_number));
  })();

  // ── Op state helpers ───────────────────────────────────────────────

  function setOp(flat_id, op, extra = {}) {
    setFlatOps(prev => ({ ...prev, [flat_id]: { op, ...extra } }));
  }

  function clearOp(flat_id) {
    setFlatOps(prev => { const n = { ...prev }; delete n[flat_id]; return n; });
  }

  function getOp(flat_id) {
    return flatOps[flat_id]?.op || OP.IDLE;
  }

  // ── Delete ────────────────────────────────────────────────────────

  async function handleDelete() {
    const { id, uid, flat_id } = deleteTarget;
    setDeleteTarget(null);
    setOp(flat_id, OP.CHECKING);
    try {
      await api('DELETE', `/api/rfid/${id}`);
      setOp(flat_id, OP.SUCCESS);
      showToast(`✅ Card ${uid} removed from charger and system`);
      loadData();
      setTimeout(() => clearOp(flat_id), 3000);
    } catch (e) {
      const err = parseApiError(e);
      if (err.status === 425) {
        setOp(flat_id, OP.OFFLINE_BLOCK, { error: err });
        setTimeout(() => clearOp(flat_id), 8000);
      } else if (err.status === 504) {
        setOp(flat_id, OP.IDLE);
        showToast(`❌ ${err.message} ${err.hint || ''}`, 'error');
      } else if (err.status === 502) {
        setOp(flat_id, OP.REJECTED, { error: err });
        setTimeout(() => clearOp(flat_id), 5000);
        showToast(`❌ ${err.message}`, 'error');
      } else {
        clearOp(flat_id);
        showToast(err.message, 'error');
      }
    }
  }

  // ── Deactivate ────────────────────────────────────────────────────

  async function handleDeactivate(flat_id, flat_number) {
    setDeactivateTarget(null);
    setOp(flat_id, OP.CHECKING);
    try {
      const res = await api('POST', `/api/rfid/flat/${flat_id}/deactivate`);
      setOp(flat_id, OP.SUCCESS);
      showToast(`✅ Charger deactivated — ${res.cards_deactivated} card(s) disabled`);
      loadData();
      setTimeout(() => clearOp(flat_id), 3000);
    } catch (e) {
      const err = parseApiError(e);
      if (err.status === 425) {
        setOp(flat_id, OP.OFFLINE_QUEUE, { error: err });
        setQueueConfirm({ flat_id, flat_number, cmd: 'DEACTIVATE', error: err });
      } else if (err.status === 504) {
        setOp(flat_id, OP.QUEUED, { error: err });
        showToast(`⚠️ ${err.message} ${err.hint}`, 'error');
        setTimeout(() => clearOp(flat_id), 5000);
        loadData();
      } else if (err.status === 502) {
        setOp(flat_id, OP.REJECTED, { error: err });
        showToast(`❌ ${err.message} Reason: ${err.reason}`, 'error');
        setTimeout(() => clearOp(flat_id), 5000);
      } else {
        clearOp(flat_id);
        showToast(err.message, 'error');
      }
    }
  }

  function handleQueueDismiss() {
    const fid = queueConfirm?.flat_id;
    setQueueConfirm(null);
    if (fid) clearOp(fid);
  }

  // ── Activate ──────────────────────────────────────────────────────

  async function handleActivate(flat_id, flat_number) {
    setActivateTarget(null);
    setOp(flat_id, OP.CHECKING);
    try {
      const res = await api('POST', `/api/rfid/flat/${flat_id}/activate`);
      setOp(flat_id, OP.SUCCESS);
      showToast(`✅ Charger activated — ${res.cards_activated} card(s) enabled`);
      loadData();
      setTimeout(() => clearOp(flat_id), 3000);
    } catch (e) {
      const err = parseApiError(e);
      if (err.status === 425) {
        setOp(flat_id, OP.OFFLINE_QUEUE, { error: err });
        setQueueConfirm({ flat_id, flat_number, cmd: 'ACTIVATE', error: err });
      } else if (err.status === 504) {
        setOp(flat_id, OP.QUEUED, { error: err });
        showToast(`⚠️ ${err.message} ${err.hint}`, 'error');
        setTimeout(() => clearOp(flat_id), 5000);
        loadData();
      } else if (err.status === 502) {
        setOp(flat_id, OP.REJECTED, { error: err });
        showToast(`❌ ${err.message} Reason: ${err.reason}`, 'error');
        setTimeout(() => clearOp(flat_id), 5000);
      } else {
        clearOp(flat_id);
        showToast(err.message, 'error');
      }
    }
  }

  // ── Add card ──────────────────────────────────────────────────────

  async function handleAddCard() {
    const uid = addForm.uid.trim().toUpperCase();
    if (!uid) { showToast('UID is required', 'error'); return; }

    const { flat_id } = addCardTarget;
    setAddCardTarget(null);
    setOp(flat_id, OP.CHECKING);

    try {
      await api('POST', `/api/rfid/flat/${flat_id}/add-card`, {
        uid,
        label: addForm.label.trim() || null,
      });
      setOp(flat_id, OP.SUCCESS);
      showToast(`✅ Card ${uid} added and activated on charger`);
      loadData();
      setTimeout(() => clearOp(flat_id), 3000);
    } catch (e) {
      const err = parseApiError(e);
      if (err.status === 425) {
        setOp(flat_id, OP.OFFLINE_BLOCK, { error: err });
        setTimeout(() => clearOp(flat_id), 8000);
      } else if (err.status === 504) {
        setOp(flat_id, OP.IDLE);
        showToast(`❌ ${err.message} ${err.hint}`, 'error');
      } else if (err.status === 502) {
        setOp(flat_id, OP.REJECTED, { error: err });
        setTimeout(() => clearOp(flat_id), 5000);
        showToast(`❌ ${err.hint || err.message}`, 'error');
      } else {
        clearOp(flat_id);
        showToast(err.message, 'error');
      }
    }
  }

  // ── Op badge ──────────────────────────────────────────────────────

  function OpStatusBadge({ flat_id }) {
    const op = flatOps[flat_id]?.op || OP.IDLE;
    if (op === OP.IDLE) return null;
    const configs = {
      [OP.CHECKING]: { label: 'Checking charger…', bg: '#fffbeb', color: '#b45309', pulse: true },
      [OP.SENDING]: { label: 'Sending command…', bg: '#eff6ff', color: '#1d4ed8', pulse: true },
      [OP.SUCCESS]: { label: '✅ Done', bg: '#f0fdf4', color: '#15803d', pulse: false },
      [OP.QUEUED]: { label: '⏳ Queued', bg: '#fff7ed', color: '#c2410c', pulse: false },
      [OP.REJECTED]: { label: '❌ Rejected', bg: '#fff5f5', color: '#c53030', pulse: false },
      [OP.OFFLINE_BLOCK]: { label: '🔴 Charger offline', bg: '#fff5f5', color: '#c53030', pulse: false },
      [OP.OFFLINE_QUEUE]: { label: '🔴 Charger offline', bg: '#fff5f5', color: '#c53030', pulse: false },
    };
    const cfg = configs[op];
    if (!cfg) return null;
    return (
      <span style={{
        fontSize: 12, fontWeight: 600, padding: '3px 10px',
        borderRadius: 20, background: cfg.bg, color: cfg.color,
        animation: cfg.pulse ? 'pulse 1.5s ease-in-out infinite' : 'none',
      }}>
        {cfg.label}
      </span>
    );
  }

  // ── Stats ─────────────────────────────────────────────────────────

  const totalCards = cards.length;
  const activeCards = cards.filter(c => c.is_active).length;
  const flatsWithCards = new Set(cards.map(c => c.flat_id)).size;

  // ── Render ────────────────────────────────────────────────────────

  return (
    <div>
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.5; }
        }
      `}</style>

      {/* Header */}
      <div className="page-header" style={{ marginBottom: 20 }}>
        <div>
          <div className="page-title">RFID Cards</div>
          <div style={{ fontSize: 13, color: '#4a5568', marginTop: 2 }}>
            Manage RFID cards per society
          </div>
        </div>
        {societyId && (
          <button className="btn btn-secondary" onClick={() => loadData()}>
            🔄 Refresh
          </button>
        )}
      </div>

      {/* Society selector */}
      <SocietySelector value={societyId} onChange={onSocietyChange} />

      {societyId && (
        <>
          {/* CSV upload */}
          <CsvUploadPanel
            title="📤 Bulk Upload RFID Cards (CSV)"
            hint={
              <span>
                Required: <code>flat_number</code>, <code>uid</code>
                &nbsp;·&nbsp;
                Optional: <code>label</code>, <code>uid2</code>, <code>label2</code>
                &nbsp;·&nbsp;
                <span style={{ color: '#718096' }}>Max 3 cards per flat · uid2 registers a second card in the same row</span>
              </span>
            }
            uploadPath={`/api/rfid/${societyId}/csv`}
            sampleCsv={SAMPLE_CSV}
            sampleFilename="rfid_sample.csv"
            skippedKey="uid"
            onUploaded={() => loadData()}
          />

          {/* Summary strip */}
          {!loading && cards.length > 0 && (
            <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
              {[
                { label: 'Total Cards', value: totalCards, color: '#1a202c' },
                { label: 'Active', value: activeCards, color: '#15803d' },
                { label: 'Inactive', value: totalCards - activeCards, color: totalCards - activeCards > 0 ? '#c53030' : '#a0aec0' },
                { label: 'Flats with Cards', value: flatsWithCards, color: '#4338ca' },
              ].map(item => (
                <div key={item.label} style={{
                  background: '#ffffff',
                  border: '1px solid rgba(0,0,0,0.08)',
                  borderRadius: 10,
                  padding: '10px 16px',
                  minWidth: 120,
                }}>
                  <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: '#718096', marginBottom: 3 }}>
                    {item.label}
                  </div>
                  <div style={{ fontSize: 20, fontWeight: 700, color: item.color }}>{item.value}</div>
                </div>
              ))}
            </div>
          )}

          {/* Search */}
          <div style={{ marginBottom: 16 }}>
            <input
              type="text"
              placeholder="Search by flat number or UID…"
              style={{ maxWidth: 320 }}
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>

          {/* Flat groups */}
          {loading ? (
            <div style={{ color: '#718096', padding: 32, textAlign: 'center' }}>Loading…</div>
          ) : groups.length === 0 ? (
            <div style={{ color: '#718096', padding: 32, textAlign: 'center' }}>
              {flats.length === 0
                ? 'No flats found for this society'
                : 'No flats match your search'}
            </div>
          ) : (
            groups.map(g => {
              const op = getOp(g.flat_id);
              const isBusy = [OP.CHECKING, OP.SENDING].includes(op);
              const cardCount = g.cards.length;
              const canAddMore = cardCount < 3;
              const isDeactivated = cardCount > 0 && !g.cards[0].is_active;
              const isActivated = cardCount > 0 && g.cards[0].is_active;
              const opErr = flatOps[g.flat_id]?.error;

              return (
                <div className="table-wrap" style={{ marginBottom: 16 }} key={g.flat_id}>
                  {/* Flat header */}
                  <div style={{
                    padding: '12px 16px',
                    background: 'rgba(0,0,0,0.03)',
                    borderBottom: '1px solid rgba(0,0,0,0.08)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    flexWrap: 'wrap',
                    gap: 8,
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                      <strong style={{ fontSize: 14 }}>🏠 {g.flat_number}</strong>
                      {g.charger_id ? (
                        <code style={{ fontSize: 12, color: '#4a5568' }}>{g.charger_id}</code>
                      ) : (
                        <span style={{ fontSize: 12, color: '#c53030' }}>No charger</span>
                      )}
                      <span style={{ fontSize: 12, color: '#718096' }}>{cardCount}/3 cards</span>
                      <OpStatusBadge flat_id={g.flat_id} />
                    </div>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      {canAddMore && (
                        <button className="btn btn-sm btn-secondary"
                          disabled={isBusy}
                          onClick={() => { setAddForm({ uid: '', label: '' }); setAddCardTarget(g); }}>
                          ➕ Add RFID
                        </button>
                      )}
                      {isDeactivated && (
                        <button className="btn btn-sm btn-secondary"
                          disabled={isBusy}
                          onClick={() => setActivateTarget(g)}>
                          ✅ Activate Flat
                        </button>
                      )}
                      {isActivated && (
                        <button className="btn btn-sm btn-danger"
                          disabled={isBusy}
                          onClick={() => setDeactivateTarget(g)}>
                          🔴 Deactivate Flat
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Offline block banner */}
                  {op === OP.OFFLINE_BLOCK && opErr && (
                    <div style={{
                      padding: '10px 16px',
                      background: '#fff5f5',
                      borderBottom: '1px solid #fed7d7',
                      fontSize: 13, color: '#c53030',
                      display: 'flex', alignItems: 'center', gap: 8,
                    }}>
                      <span>⚠️</span>
                      <span>{opErr.message} {opErr.hint}</span>
                    </div>
                  )}

                  {/* Cards table */}
                  <table>
                    <thead>
                      <tr>
                        <th>UID</th>
                        <th>Label</th>
                        <th>Status</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {cardCount === 0 ? (
                        <tr className="empty-row">
                          <td colSpan={4}>No RFID cards yet — upload a CSV</td>
                        </tr>
                      ) : (
                        g.cards.map(c => (
                          <tr key={c.id}>
                            <td><code style={{ fontSize: 13 }}>{c.uid}</code></td>
                            <td style={{ color: '#4a5568' }}>
                              {c.label || <span style={{ color: '#a0aec0' }}>—</span>}
                            </td>
                            <td>
                              <span className={`badge ${c.is_active ? 'badge-green' : 'badge-red'}`}>
                                {c.is_active ? 'Active' : 'Inactive'}
                              </span>
                            </td>
                            <td>
                              <button
                                className="btn btn-sm btn-danger"
                                disabled={isBusy}
                                onClick={() => setDeleteTarget(c)}
                              >
                                Remove
                              </button>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              );
            })
          )}
        </>
      )}

      {/* ── Delete confirm ─────────────────────────────────────────── */}
      <Modal
        open={!!deleteTarget}
        title="Remove RFID Card"
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        confirmLabel="Remove"
      >
        <p style={{ color: '#4a5568', fontSize: 14 }}>
          Remove RFID card <strong><code>{deleteTarget?.uid}</code></strong>
          {deleteTarget?.label ? ` (${deleteTarget.label})` : ''}?
        </p>
        <p style={{ color: '#718096', fontSize: 13, marginTop: 8 }}>
          The card will first be removed from the charger (the charger must be online), and
          only then deleted from the system. If the charger does not confirm, the card is kept.
        </p>
      </Modal>

      {/* ── Deactivate confirm ─────────────────────────────────────── */}
      <Modal
        open={!!deactivateTarget}
        title={`Deactivate ${deactivateTarget?.flat_number || ''}`}
        onClose={() => setDeactivateTarget(null)}
        onConfirm={() => handleDeactivate(deactivateTarget.flat_id, deactivateTarget.flat_number)}
        confirmLabel="Deactivate"
      >
        <p style={{ color: '#4a5568', fontSize: 14 }}>
          This will send a <strong>DEACTIVATE</strong> command to charger{' '}
          <code>{deactivateTarget?.charger_id}</code>.<br /><br />
          The server will first check if the charger is online. If online, the command
          is sent immediately. If offline, you will be given the option to queue it.
          <br /><br />
          Any active charging session will be stopped.
        </p>
      </Modal>

      {/* ── Activate confirm ───────────────────────────────────────── */}
      <Modal
        open={!!activateTarget}
        title={`Activate ${activateTarget?.flat_number || ''}`}
        onClose={() => setActivateTarget(null)}
        onConfirm={() => handleActivate(activateTarget.flat_id, activateTarget.flat_number)}
        confirmLabel="Activate"
      >
        <p style={{ color: '#4a5568', fontSize: 14 }}>
          This will send an <strong>ACTIVE</strong> command to charger{' '}
          <code>{activateTarget?.charger_id}</code>.<br /><br />
          The server will first check if the charger is online. If online, the command
          is sent immediately. If offline, you will be given the option to queue it.
          <br /><br />
          All RFID cards for this flat will be re-enabled on the charger.
        </p>
      </Modal>

      {/* ── Offline queue modal ────────────────────────────────────── */}
      <Modal
        open={!!queueConfirm}
        title="Charger is Offline"
        onClose={handleQueueDismiss}
        onConfirm={handleQueueDismiss}
        confirmLabel="Understood"
      >
        {queueConfirm && (
          <div>
            <div style={{
              background: '#fff5f5', border: '1px solid #fed7d7',
              borderRadius: 8, padding: '12px 16px', marginBottom: 16,
            }}>
              <div style={{ fontWeight: 700, color: '#c53030', marginBottom: 4 }}>
                🔴 {queueConfirm.error.message}
              </div>
              <div style={{ fontSize: 13, color: '#4a5568' }}>
                {queueConfirm.error.hint}
              </div>
            </div>
            <p style={{ fontSize: 13, color: '#4a5568' }}>
              <strong>{queueConfirm.cmd}</strong> for flat{' '}
              <strong>{queueConfirm.flat_number}</strong> cannot be sent right now.
              Please wait for the charger to come back online and try again.
            </p>
          </div>
        )}
      </Modal>

      {/* ── Add card modal ─────────────────────────────────────────── */}
      <Modal
        open={!!addCardTarget}
        title={`Add RFID Card — ${addCardTarget?.flat_number || ''}`}
        onClose={() => setAddCardTarget(null)}
        onConfirm={handleAddCard}
        confirmLabel="Add Card"
      >
        <div style={{
          background: '#eff6ff', border: '1px solid #bae6fd',
          borderRadius: 8, padding: '10px 14px', marginBottom: 16,
          fontSize: 13, color: '#1d4ed8',
        }}>
          ℹ️ The server will first check if the charger is online before adding the card.
          RFID cards cannot be added while the charger is offline.
        </div>
        <div className="form-group">
          <label>RFID UID *</label>
          <input
            placeholder="e.g. 14AF7D05"
            style={{ textTransform: 'uppercase' }}
            value={addForm.uid}
            onChange={e => setAddForm({ ...addForm, uid: e.target.value })}
          />
          <small style={{ color: '#718096', fontSize: 12 }}>
            Uppercase hex, no spaces or separators
          </small>
        </div>
        <div className="form-group">
          <label>Label <span style={{ color: '#718096', fontWeight: 400 }}>(optional)</span></label>
          <input
            placeholder="e.g. Owner Card, Car Key"
            value={addForm.label}
            onChange={e => setAddForm({ ...addForm, label: e.target.value })}
          />
        </div>
      </Modal>
    </div>
  );
}