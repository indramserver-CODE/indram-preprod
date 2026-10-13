import { useEffect, useState } from 'react';
import { api, apiDownload } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import SocietySelector from '../../components/common/SocietySelector';
import { toNum, fmtDate, fmtPeriod, todayIso } from '../../utils/format';

// Indram's GST tax invoices — one per sent meter bill.
// Late flag (after due date + society's grace days) adds the late fee + GST; Paid clears it.

function fmtCurrency(v) {
  return `₹${toNum(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function PaymentCell({ bill }) {
  if (bill.status === 'cancelled') return <span className="badge badge-gray">Cancelled</span>;
  return (
    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', alignItems: 'center' }}>
      <span className={`badge ${bill.payment_status === 'paid' ? 'badge-green' : 'badge-red'}`}>
        {bill.payment_status === 'paid' ? 'Paid' : 'Unpaid'}
      </span>
      {bill.late_flag && <span className="badge badge-amber">Late</span>}
      {bill.paid_at && <div style={{ fontSize: 11, color: '#718096', width: '100%' }}>{fmtDate(bill.paid_at)}</div>}
    </div>
  );
}

export default function IndramBills() {
  const { showToast } = useToast();
  const [revenue, setRevenue]             = useState(null);
  const [bills, setBills]                 = useState([]);
  const [loading, setLoading]             = useState(true);
  const [societyFilter, setSocietyFilter] = useState(null);
  const [monthFilter, setMonthFilter]     = useState('');
  const [paymentFilter, setPaymentFilter] = useState('');
  const [showCancelled, setShowCancelled] = useState(false);
  const [detail, setDetail]               = useState(null);
  const [busyId, setBusyId]               = useState(null);

  async function loadRevenue() {
    try { setRevenue(await api('GET', '/api/indram-bills/revenue-summary')); } catch { /* tiles are optional */ }
  }

  async function loadBills(f = {}) {
    const sid     = f.sid     !== undefined ? f.sid     : societyFilter;
    const month   = f.month   !== undefined ? f.month   : monthFilter;
    const payment = f.payment !== undefined ? f.payment : paymentFilter;
    const cancelled = f.cancelled !== undefined ? f.cancelled : showCancelled;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (sid)       params.set('society_id', sid);
      if (month)     params.set('month', month);
      if (payment)   params.set('payment_status', payment);
      if (cancelled) params.set('include_cancelled', 'true');
      setBills(await api('GET', '/api/indram-bills' + (params.toString() ? '?' + params : '')));
    } catch (e) { showToast(e.message, 'error'); }
    finally { setLoading(false); }
  }

  useEffect(() => { loadRevenue(); loadBills(); }, []); // eslint-disable-line

  async function openDetail(bill) {
    try { setDetail(await api('GET', `/api/indram-bills/${bill.id}`)); }
    catch (e) { showToast(e.message, 'error'); }
  }

  async function act(bill, action) {
    const prompt = action === 'late'
      ? `Raise the late flag on ${bill.invoice_number}?\n\nThe society's late fee (plus GST) is added and the updated invoice is emailed to the society admin.`
      : `Mark ${bill.invoice_number} as paid${bill.late_flag ? ' (including the late fee)' : ''}?\n\nA receipt becomes available to the society admin.`;
    if (!window.confirm(prompt)) return;
    setBusyId(bill.id);
    try {
      const updated = await api('PUT', `/api/indram-bills/${bill.id}/${action}`);
      showToast(action === 'late' ? `Late fee added to ${updated.invoice_number} — society admin emailed` : `${updated.invoice_number} marked paid`);
      loadBills(); loadRevenue();
      if (detail?.id === bill.id) setDetail(updated);
    } catch (e) { showToast(e.message, 'error'); }
    finally { setBusyId(null); }
  }

  function download(bill, kind) {
    apiDownload(`/api/indram-bills/${bill.id}/${kind}`).catch(e => showToast(e.message, 'error'));
  }

  function Actions({ bill }) {
    const open = bill.status === 'issued' && bill.payment_status === 'unpaid';
    return (
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {open && !bill.late_flag && (
          <button className="btn btn-sm btn-danger" disabled={busyId === bill.id}
                  title={bill.late_flag_allowed_from ? `Allowed from ${fmtDate(bill.late_flag_allowed_from)}` : ''}
                  onClick={() => act(bill, 'late')}>Flag late</button>
        )}
        {open && <button className="btn btn-sm btn-primary" disabled={busyId === bill.id} onClick={() => act(bill, 'paid')}>Mark paid</button>}
        <button className="btn btn-sm btn-secondary" onClick={() => download(bill, 'pdf')}>Invoice</button>
        {bill.has_receipt && <button className="btn btn-sm btn-secondary" onClick={() => download(bill, 'receipt')}>Receipt</button>}
      </div>
    );
  }

  const clearFilters = () => {
    setSocietyFilter(null); setMonthFilter(''); setPaymentFilter('');
    loadBills({ sid: null, month: '', payment: '' });
  };

  return (
    <div>
      <div className="page-header" style={{ marginBottom: 20 }}>
        <div>
          <div className="page-title">Indram Bills</div>
          <div style={{ fontSize: 13, color: '#4a5568', marginTop: 2 }}>GST tax invoices to societies — issued automatically when a society sends its bills</div>
        </div>
        <button className="btn btn-secondary" onClick={() => { loadRevenue(); loadBills(); }}>Refresh</button>
      </div>

      {revenue && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 12, marginBottom: 24 }}>
          {[
            { label: 'Total (before GST)', value: fmtCurrency(revenue.total_all_time), color: '#1a202c' },
            { label: 'Collected',          value: fmtCurrency(revenue.total_paid),     color: '#15803d' },
            { label: 'Outstanding',        value: fmtCurrency(revenue.total_unpaid),   color: revenue.total_unpaid > 0 ? '#c53030' : '#a0aec0' },
            { label: 'This Month',         value: fmtCurrency(revenue.this_month),     color: '#4338ca' },
            { label: 'Unpaid Invoices',    value: revenue.unpaid_count,                color: revenue.unpaid_count > 0 ? '#c53030' : '#a0aec0' },
            { label: 'Flagged Late',       value: revenue.late_count,                  color: revenue.late_count > 0 ? '#b7791f' : '#a0aec0' },
          ].map(item => (
            <div key={item.label} style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.08)', borderRadius: 12, padding: '14px 16px', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
              <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: '#718096', marginBottom: 6 }}>{item.label}</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: item.color }}>{item.value}</div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
        <SocietySelector value={societyFilter} onChange={id => { setSocietyFilter(id); loadBills({ sid: id }); }} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <label style={{ fontSize: 13, color: '#4a5568' }}>Month:</label>
          <input type="month" value={monthFilter} onChange={e => { setMonthFilter(e.target.value); loadBills({ month: e.target.value }); }} style={{ width: 160 }} />
        </div>
        <select value={paymentFilter} onChange={e => { setPaymentFilter(e.target.value); loadBills({ payment: e.target.value }); }} style={{ width: 150 }}>
          <option value="">All payments</option>
          <option value="unpaid">Unpaid</option>
          <option value="paid">Paid</option>
        </select>
        <label style={{ fontSize: 13, color: '#4a5568', display: 'flex', alignItems: 'center', gap: 6, margin: 0 }}>
          <input type="checkbox" checked={showCancelled} style={{ width: 'auto' }}
                 onChange={e => { setShowCancelled(e.target.checked); loadBills({ cancelled: e.target.checked }); }} />
          Show cancelled
        </label>
        {(societyFilter || monthFilter || paymentFilter) && (
          <button className="btn btn-sm btn-secondary" onClick={clearFilters}>Clear filters</button>
        )}
      </div>

      <div className="table-wrap" style={{ marginBottom: detail ? 24 : 0 }}>
        <table>
          <thead>
            <tr><th>Invoice No.</th><th>Society</th><th>Meter · Period</th><th>Units</th><th>Charges</th><th>Total (incl. GST)</th><th>Due</th><th>Payment</th><th>Actions</th></tr>
          </thead>
          <tbody>
            {loading ? (
              <tr className="empty-row"><td colSpan={9}>Loading...</td></tr>
            ) : bills.length === 0 ? (
              <tr className="empty-row"><td colSpan={9}>No Indram invoices found</td></tr>
            ) : bills.map(b => (
              <tr key={b.id} style={b.status === 'cancelled' ? { opacity: 0.6 } : undefined}>
                <td>
                  <button className="btn btn-sm btn-secondary" style={{ fontFamily: 'monospace' }} onClick={() => openDetail(b)}>{b.invoice_number}</button>
                </td>
                <td><strong>{b.society_name || '-'}</strong></td>
                <td style={{ fontSize: 13 }}>{b.meter_label}<div style={{ color: '#718096', fontSize: 12 }}>{fmtPeriod(b.period_from, b.period_till)}</div></td>
                <td>{toNum(b.total_units).toFixed(2)}</td>
                <td>
                  {fmtCurrency(b.total_indram_amount)}
                  {toNum(b.late_fee) > 0 && <div style={{ fontSize: 11, color: '#c53030' }}>+ {fmtCurrency(b.late_fee)} late fee</div>}
                </td>
                <td><strong>{fmtCurrency(b.total_payable)}</strong></td>
                <td style={{ fontSize: 13, color: b.payment_status === 'unpaid' && b.due_date < todayIso() ? '#c53030' : '#4a5568' }}>{fmtDate(b.due_date)}</td>
                <td><PaymentCell bill={b} /></td>
                <td><Actions bill={b} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {detail && (
        <div style={{ marginTop: 4 }}>
          <div className="page-header" style={{ marginBottom: 16 }}>
            <div>
              <div className="page-title" style={{ fontSize: 18 }}>{detail.invoice_number} — {detail.society_name}</div>
              <div style={{ fontSize: 13, color: '#4a5568', marginTop: 3 }}>
                {detail.meter_label} ({detail.meter_number}) · {fmtPeriod(detail.period_from, detail.period_till)}
                {detail.replaces_number && <> · replaces {detail.replaces_number}</>}
                {detail.replaced_by_number && <> · replaced by {detail.replaced_by_number}</>}
              </div>
            </div>
            <button className="btn btn-secondary" onClick={() => setDetail(null)}>Close</button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12, marginBottom: 16 }}>
            {[
              { label: 'Units',            value: `${toNum(detail.total_units).toFixed(3)} kWh @ ${fmtCurrency(detail.indram_rate)}` },
              { label: 'Charges',          value: fmtCurrency(detail.total_indram_amount) },
              { label: `Late fee${detail.late_fee_pct ? ` (${toNum(detail.late_fee_pct)}%)` : ''}`, value: fmtCurrency(detail.late_fee) },
              { label: 'CGST + SGST',      value: fmtCurrency(toNum(detail.cgst) + toNum(detail.sgst)) },
              { label: 'Total payable',    value: fmtCurrency(detail.total_payable) },
              { label: 'Due date',         value: fmtDate(detail.due_date) },
              { label: 'Late flag allowed', value: fmtDate(detail.late_flag_allowed_from) },
              { label: 'Society GSTIN',    value: detail.society_gstin || '—' },
            ].map(item => (
              <div key={item.label} style={{ background: '#f9fafb', border: '1px solid rgba(0,0,0,0.07)', borderRadius: 10, padding: '12px 16px' }}>
                <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: '#718096', marginBottom: 4 }}>{item.label}</div>
                <div style={{ fontSize: 15, fontWeight: 700, color: '#1a202c' }}>{item.value}</div>
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <PaymentCell bill={detail} />
            <Actions bill={detail} />
          </div>
        </div>
      )}
    </div>
  );
}
