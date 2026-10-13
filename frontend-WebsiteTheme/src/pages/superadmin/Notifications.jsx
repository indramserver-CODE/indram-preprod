import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import SocietySelector from '../../components/common/SocietySelector';

// Billing notifications: a flat marked Unpaid → switch its charger off; it paid → switch back on.
// The switch uses the RFID endpoints (online check + charger ack), same as the RFID page.

function timeAgo(iso) {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1)  return 'just now';
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} h ago`;
  return new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

export default function Notifications() {
  const { showToast } = useToast();
  const [items, setItems]           = useState([]);
  const [unread, setUnread]         = useState(0);
  const [loading, setLoading]       = useState(true);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [societyId, setSocietyId]   = useState(null);
  const [busyId, setBusyId]         = useState(null);

  async function load(only = unreadOnly, sid = societyId) {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: '100' });
      if (only) params.set('unread_only', 'true');
      if (sid)  params.set('society_id', sid);
      const data = await api('GET', `/api/notifications?${params}`);
      setItems(data.items);
      setUnread(data.unread_count);
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []); // eslint-disable-line

  async function markRead(n) {
    try {
      await api('PUT', `/api/notifications/${n.id}/read`);
      load();
    } catch (e) { showToast(e.message, 'error'); }
  }

  async function markAllRead() {
    try {
      await api('PUT', '/api/notifications/read-all');
      load();
    } catch (e) { showToast(e.message, 'error'); }
  }

  async function switchCharger(n) {
    const off = n.action === 'deactivate';
    if (!window.confirm(`${off ? 'Switch off' : 'Switch on'} charger ${n.charger_id || ''}?\n\n${n.message}`)) return;
    setBusyId(n.id);
    try {
      await api('POST', n.action_url);
      await api('PUT', `/api/notifications/${n.id}/actioned`);
      showToast(`✅ Charger ${n.charger_id || ''} switched ${off ? 'off' : 'on'}`);
      load();
    } catch (e) {
      const detail = typeof e.detail === 'object' && e.detail ? e.detail : {};
      if (e.status === 504) {
        // Charger dropped mid-command — it's queued and applies on reconnect
        await api('PUT', `/api/notifications/${n.id}/actioned`).catch(() => {});
        showToast(`⚠️ ${e.message} ${detail.hint || ''}`, 'error');
        load();
      } else if (e.status === 425) {
        showToast(`🔴 ${e.message} Try again when the charger is back online.`, 'error');
      } else if (e.status === 502) {
        showToast(`❌ ${e.message} Reason: ${detail.reason || 'unknown'}`, 'error');
      } else {
        showToast(e.message, 'error');
      }
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Notifications {unread > 0 && <span className="badge badge-red" style={{ fontSize: 13, verticalAlign: 'middle' }}>{unread} unread</span>}</div>
          <div style={{ fontSize: 13, color: '#4a5568', marginTop: 2 }}>Flats marked Unpaid or paid late — switch their chargers off or back on</div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {unread > 0 && <button className="btn btn-secondary" onClick={markAllRead}>Mark all read</button>}
          <button className="btn btn-secondary" onClick={() => load()}>Refresh</button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
        <SocietySelector value={societyId} onChange={id => { setSocietyId(id); load(unreadOnly, id); }} />
        <label style={{ fontSize: 13, color: '#4a5568', display: 'flex', alignItems: 'center', gap: 6, margin: 0 }}>
          <input type="checkbox" checked={unreadOnly} style={{ width: 'auto' }}
                 onChange={e => { setUnreadOnly(e.target.checked); load(e.target.checked, societyId); }} />
          Unread only
        </label>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr><th></th><th>Notification</th><th>Society</th><th>When</th><th>Charger</th><th>Actions</th></tr>
          </thead>
          <tbody>
            {loading ? (
              <tr className="empty-row"><td colSpan={6}>Loading…</td></tr>
            ) : items.length === 0 ? (
              <tr className="empty-row"><td colSpan={6}>{unreadOnly ? 'No unread notifications' : 'No notifications yet'}</td></tr>
            ) : items.map(n => (
              <tr key={n.id} style={{ background: n.is_read ? undefined : 'rgba(79,134,247,0.05)' }}>
                <td style={{ width: 28, textAlign: 'center' }}>{n.type === 'flat_unpaid' ? '🔴' : '🟢'}</td>
                <td style={{ fontWeight: n.is_read ? 400 : 600, fontSize: 14 }}>{n.message}</td>
                <td style={{ fontSize: 13, color: '#4a5568' }}>{n.society_name}</td>
                <td style={{ fontSize: 13, color: '#4a5568', whiteSpace: 'nowrap' }}>{timeAgo(n.created_at)}</td>
                <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{n.charger_id || '—'}</td>
                <td>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                    {n.actioned_at ? (
                      <span className="badge badge-green">✓ Switched {n.action === 'deactivate' ? 'off' : 'on'}</span>
                    ) : n.action_url && (
                      <button className={`btn btn-sm ${n.action === 'deactivate' ? 'btn-danger' : 'btn-primary'}`}
                              disabled={busyId === n.id} onClick={() => switchCharger(n)}>
                        {busyId === n.id ? 'Checking charger…' : n.action === 'deactivate' ? 'Switch off' : 'Switch on'}
                      </button>
                    )}
                    {!n.is_read && <button className="btn btn-sm btn-secondary" onClick={() => markRead(n)}>Mark read</button>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
