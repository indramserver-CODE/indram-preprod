import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import { CompletedStatusBadge } from '../../components/common/FaultBadges';

function todayMonth() {
  const t = new Date();
  return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}`;
}

export default function SaCompleted() {
  const { showToast } = useToast();
  const [societyName, setSocietyName] = useState('');
  const [month, setMonth] = useState(todayMonth());
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);

  async function load(m = month) {
    setLoading(true);
    try {
      const data = await api('GET', `/api/sessions/completed?month=${m}`);
      setSessions(data);
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

  function onMonthChange(m) {
    setMonth(m);
    load(m);
  }

  const totalUnits = sessions.reduce((s, x) => s + parseFloat(x.units_consumed || 0), 0);
  const errors = sessions.filter(x => x.status === 'charging_ended_error').length;

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Completed Sessions</div>
          <div style={{ fontSize: 13, color: '#4a5568', marginTop: 2 }}>{societyName}</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <input type="month" style={{ width: 'auto', padding: '8px 12px' }} value={month} onChange={e => onMonthChange(e.target.value)} />
          <button className="btn btn-secondary" onClick={() => load()}>
            🔄 Refresh
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 16, marginBottom: 20 }}>
        <div className="table-wrap" style={{ padding: '16px 20px', flex: 1 }}>
          <div style={{ fontSize: 11, color: '#718096', fontWeight: 700, textTransform: 'uppercase' }}>Total Sessions</div>
          <div style={{ fontSize: 24, fontWeight: 700, color: '#1a202c' }}>{sessions.length}</div>
        </div>
        <div className="table-wrap" style={{ padding: '16px 20px', flex: 1 }}>
          <div style={{ fontSize: 11, color: '#718096', fontWeight: 700, textTransform: 'uppercase' }}>Total Units</div>
          <div style={{ fontSize: 24, fontWeight: 700, color: '#1a202c' }}>{totalUnits.toFixed(3)} kWh</div>
        </div>
        <div className="table-wrap" style={{ padding: '16px 20px', flex: 1 }}>
          <div style={{ fontSize: 11, color: '#718096', fontWeight: 700, textTransform: 'uppercase' }}>Errors</div>
          <div style={{ fontSize: 24, fontWeight: 700, color: errors > 0 ? '#c53030' : '#1a202c' }}>{errors}</div>
        </div>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Charger ID</th>
              <th>RFID UID</th>
              <th>Started</th>
              <th>Ended</th>
              <th>Units (kWh)</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr className="empty-row">
                <td colSpan={7}>Loading…</td>
              </tr>
            ) : sessions.length === 0 ? (
              <tr className="empty-row">
                <td colSpan={7}>No completed sessions for this month</td>
              </tr>
            ) : (
              sessions.map(s => (
                <tr key={s.id}>
                  <td>{s.charger_id}</td>
                  <td>
                    <code>{s.rfid_uid || '—'}</code>
                  </td>
                  <td>{new Date(s.started_at).toLocaleString()}</td>
                  <td>{s.ended_at ? new Date(s.ended_at).toLocaleString() : '—'}</td>
                  <td>{s.units_consumed != null ? parseFloat(s.units_consumed).toFixed(4) : '—'}</td>
                  <td>
                    <CompletedStatusBadge status={s.status} faultCode={s.fault_code} />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <p style={{ fontSize: 12, color: '#718096', marginTop: 16, textAlign: 'center' }}>
        ℹ️ Tip: Hover over a status badge to view its description
      </p>
    </div>
  );
}
