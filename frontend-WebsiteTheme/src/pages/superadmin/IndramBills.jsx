import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import SocietySelector from '../../components/common/SocietySelector';

function fmtMonth(d) {
  return new Date(d + '-02').toLocaleDateString('en-IN', { month: 'long', year: 'numeric' });
}
function fmtCurrency(v) {
  return `\u20B9${parseFloat(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function IndramBills() {
  const { showToast } = useToast();
  const [revenue, setRevenue]             = useState(null);
  const [bills, setBills]                 = useState([]);
  const [loading, setLoading]             = useState(true);
  const [societyFilter, setSocietyFilter] = useState(null);
  const [monthFilter, setMonthFilter]     = useState('');
  const [detailView, setDetailView]       = useState(null);
  const [updatingId, setUpdatingId]       = useState(null);

  async function loadRevenue() {
    try { setRevenue(await api('GET', '/api/indram-bills/revenue-summary')); } catch {}
  }

  async function loadBills(sid = societyFilter, month = monthFilter) {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (sid)   params.set('society_id', sid);
      if (month) params.set('month', month);
      setBills(await api('GET', '/api/indram-bills' + (params.toString() ? '?' + params : '')));
    } catch (e) { showToast(e.message, 'error'); }
    finally { setLoading(false); }
  }

  useEffect(() => { loadRevenue(); loadBills(); }, []); // eslint-disable-line

  function handleSocietyChange(id) { setSocietyFilter(id); loadBills(id, monthFilter); }
  function handleMonthChange(m)    { setMonthFilter(m);    loadBills(societyFilter, m); }

  async function loadDetail(bill) {
    try { setDetailView(await api('GET', `/api/indram-bills/${bill.id}`)); }
    catch (e) { showToast(e.message, 'error'); }
  }

  async function togglePayment(bill) {
    const newStatus = bill.payment_status === 'paid' ? 'unpaid' : 'paid';
    setUpdatingId(bill.id);
    try {
      await api('PUT', `/api/indram-bills/${bill.id}/payment`, { payment_status: newStatus });
      showToast(`Bill marked as ${newStatus}`);
      loadBills(); loadRevenue();
      if (detailView?.id === bill.id) setDetailView(p => ({ ...p, payment_status: newStatus }));
    } catch (e) { showToast(e.message, 'error'); }
    finally { setUpdatingId(null); }
  }

  return (
    <div>
      <div className="page-header" style={{ marginBottom: 20 }}>
        <div>
          <div className="page-title">Indram Bills</div>
          <div style={{ fontSize: 13, color: '#4a5568', marginTop: 2 }}>Platform service invoices — all societies</div>
        </div>
        <button className="btn btn-secondary" onClick={() => { loadRevenue(); loadBills(); }}>Refresh</button>
      </div>

      {revenue && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 12, marginBottom: 24 }}>
          {[
            { label: 'Total Revenue',   value: fmtCurrency(revenue.total_all_time), color: '#1a202c' },
            { label: 'Collected',       value: fmtCurrency(revenue.total_paid),     color: '#15803d' },
            { label: 'Outstanding',     value: fmtCurrency(revenue.total_unpaid),   color: revenue.total_unpaid > 0 ? '#c53030' : '#a0aec0' },
            { label: 'This Month',      value: fmtCurrency(revenue.this_month),     color: '#4338ca' },
            { label: 'Unpaid Invoices', value: revenue.unpaid_count,                color: revenue.unpaid_count > 0 ? '#c53030' : '#a0aec0' },
          ].map(item => (
            <div key={item.label} style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.08)', borderRadius: 12, padding: '14px 16px', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
              <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: '#718096', marginBottom: 6 }}>{item.label}</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: item.color }}>{item.value}</div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
        <SocietySelector value={societyFilter} onChange={handleSocietyChange} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <label style={{ fontSize: 13, color: '#4a5568' }}>Month:</label>
          <input type="month" value={monthFilter} onChange={e => handleMonthChange(e.target.value)} style={{ width: 160 }} />
        </div>
        {(societyFilter || monthFilter) && (
          <button className="btn btn-sm btn-secondary" onClick={() => { setSocietyFilter(null); setMonthFilter(''); loadBills(null, ''); }}>
            Clear filters
          </button>
        )}
      </div>

      <div className="table-wrap" style={{ marginBottom: detailView ? 24 : 0 }}>
        <table>
          <thead>
            <tr><th>Society</th><th>Month</th><th>Units (kWh)</th><th>Amount</th><th>Due Date</th><th>Email</th><th>Payment</th><th>Actions</th></tr>
          </thead>
          <tbody>
            {loading ? (
              <tr className="empty-row"><td colSpan={8}>Loading...</td></tr>
            ) : bills.length === 0 ? (
              <tr className="empty-row"><td colSpan={8}>No Indram bills found</td></tr>
            ) : bills.map(b => (
              <tr key={b.id}>
                <td><strong>{b.society_name || '-'}</strong></td>
                <td>{fmtMonth(b.billing_month)}</td>
                <td>{parseFloat(b.total_units).toFixed(2)}</td>
                <td><strong>{fmtCurrency(b.total_indram_amount)}</strong></td>
                <td style={{ fontSize: 13, color: '#4a5568' }}>{new Date(b.due_date).toLocaleDateString('en-IN')}</td>
                <td>
                  <span className={`badge ${b.email_status === 'sent' ? 'badge-green' : b.email_status === 'failed' ? 'badge-red' : 'badge-gray'}`}>
                    {b.email_status === 'sent' ? 'Sent' : b.email_status === 'failed' ? 'Failed' : 'Pending'}
                  </span>
                </td>
                <td>
                  <span className={`badge ${b.payment_status === 'paid' ? 'badge-green' : 'badge-red'}`}>
                    {b.payment_status === 'paid' ? 'Paid' : 'Unpaid'}
                  </span>
                  {b.paid_at && <div style={{ fontSize: 11, color: '#718096', marginTop: 2 }}>{new Date(b.paid_at).toLocaleDateString('en-IN')}</div>}
                </td>
                <td style={{ display: 'flex', gap: 6 }}>
                  <button className="btn btn-sm btn-secondary" onClick={() => loadDetail(b)}>Details</button>
                  <button className={`btn btn-sm ${b.payment_status === 'paid' ? 'btn-danger' : 'btn-secondary'}`}
                    disabled={updatingId === b.id} onClick={() => togglePayment(b)}>
                    {updatingId === b.id ? '...' : b.payment_status === 'paid' ? 'Mark Unpaid' : 'Mark Paid'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {detailView && (
        <div style={{ marginTop: 4 }}>
          <div className="page-header" style={{ marginBottom: 16 }}>
            <div>
              <div className="page-title" style={{ fontSize: 18 }}>{detailView.society_name} — {fmtMonth(detailView.billing_month)}</div>
              <div style={{ fontSize: 13, color: '#4a5568', marginTop: 3 }}>Invoice breakdown per meter</div>
            </div>
            <button className="btn btn-secondary" onClick={() => setDetailView(null)}>Close</button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12, marginBottom: 16 }}>
            {[
              { label: 'Total Units',  value: `${parseFloat(detailView.total_units).toFixed(2)} kWh` },
              { label: 'Total Amount', value: fmtCurrency(detailView.total_indram_amount) },
              { label: 'Due Date',     value: new Date(detailView.due_date).toLocaleDateString('en-IN') },
              { label: 'Status',       value: detailView.payment_status === 'paid' ? 'Paid' : 'Unpaid' },
            ].map(item => (
              <div key={item.label} style={{ background: '#f9fafb', border: '1px solid rgba(0,0,0,0.07)', borderRadius: 10, padding: '12px 16px' }}>
                <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: '#718096', marginBottom: 4 }}>{item.label}</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: '#1a202c' }}>{item.value}</div>
              </div>
            ))}
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Meter Number</th><th>Meter Label</th><th>Units Billed (kWh)</th><th>Indram Charges</th></tr>
              </thead>
              <tbody>
                {!detailView.meter_breakdown?.length ? (
                  <tr className="empty-row"><td colSpan={4}>No meter data</td></tr>
                ) : detailView.meter_breakdown.map(m => (
                  <tr key={m.meter_id}>
                    <td><code style={{ fontSize: 12 }}>{m.meter_number}</code></td>
                    <td><strong>{m.meter_label}</strong></td>
                    <td>{parseFloat(m.units_billed).toFixed(4)}</td>
                    <td><strong>{fmtCurrency(m.indram_amount)}</strong></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}