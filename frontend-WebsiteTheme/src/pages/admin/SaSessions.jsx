import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import { LiveStatusBadge } from '../../components/common/FaultBadges';

const fmt = (val, decimals = 2) => (val != null ? parseFloat(val).toFixed(decimals) : '—');

export default function SaSessions() {
  const { showToast } = useToast();
  const [societyName, setSocietyName] = useState('');
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const data = await api('GET', '/api/sessions/active');
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

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Active Sessions</div>
          <div style={{ fontSize: 13, color: '#4a5568', marginTop: 2 }}>{societyName}</div>
        </div>
        <button className="btn btn-secondary" onClick={load}>
          🔄 Refresh
        </button>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Flat No.</th>
              <th>Charger ID</th>
              <th>RFID UID</th>
              <th>Started At</th>
              <th>Duration</th>
              <th>Voltage (V)</th>
              <th>Current (A)</th>
              <th>Energy (kWh)</th>
              <th>Temp (°C)</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr className="empty-row">
                <td colSpan={10}>Loading…</td>
              </tr>
            ) : sessions.length === 0 ? (
              <tr className="empty-row">
                <td colSpan={10}>No active sessions right now</td>
              </tr>
            ) : (
              sessions.map(s => (
                <tr key={s.charger_id + (s.started_at || '')}>
                  <td>
                    <strong>{s.flat_number || '—'}</strong>
                  </td>
                  <td>
                    <code>{s.charger_id}</code>
                  </td>
                  <td>
                    <code>{s.rfid_uid || '—'}</code>
                  </td>
                  <td>{s.started_at ? new Date(s.started_at).toLocaleString() : '—'}</td>
                  <td>{s.duration_min != null ? `${s.duration_min} min` : '—'}</td>
                  <td>{fmt(s.voltage)}</td>
                  <td>{fmt(s.current)}</td>
                  <td>{fmt(s.energy_kwh, 4)}</td>
                  <td>{fmt(s.temperature_c, 1)}</td>
                  <td>
                    <LiveStatusBadge status={s.charger_status} faultCode={s.fault_code} />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
