import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import { fmtMoney } from '../../utils/format';

function todayMonth() {
  const t = new Date();
  return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}`;
}

export default function SaUsage() {
  const { showToast } = useToast();
  const [societyName, setSocietyName] = useState('');
  const [month, setMonth] = useState(todayMonth());
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  async function load(m = month) {
    setLoading(true);
    try {
      const data = await api('GET', `/api/usage?month=${m}`);
      setRows(data);
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

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Usage per Flat</div>
          <div style={{ fontSize: 13, color: '#4a5568', marginTop: 2 }}>{societyName}</div>
        </div>
        <input type="month" style={{ width: 'auto', padding: '8px 12px' }} value={month} onChange={e => onMonthChange(e.target.value)} />
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Flat No.</th>
              <th>Owner</th>
              <th>Sessions</th>
              <th>Total Units (kWh)</th>
              <th>Amount</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr className="empty-row">
                <td colSpan={5}>Loading…</td>
              </tr>
            ) : rows.length === 0 ? (
              <tr className="empty-row">
                <td colSpan={5}>No data for this month</td>
              </tr>
            ) : (
              rows.map(r => (
                <tr key={r.flat_number}>
                  <td>
                    <strong>{r.flat_number}</strong>
                  </td>
                  <td>{r.owner_name || '—'}</td>
                  <td>{r.session_count}</td>
                  <td>{parseFloat(r.total_units).toFixed(4)}</td>
                  <td>{fmtMoney(r.total_amount)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
