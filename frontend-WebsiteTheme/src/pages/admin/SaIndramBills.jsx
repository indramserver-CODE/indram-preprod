import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import { toNum } from '../../utils/format';

function fmtMonth(d) {
    return new Date(d + '-02').toLocaleDateString('en-IN', { month: 'long', year: 'numeric' });
}
function fmtCurrency(v) {
    return `\u20B9${toNum(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function SaIndramBills() {
    const { showToast } = useToast();
    const [societyName, setSocietyName] = useState('');
    const [bills, setBills] = useState([]);
    const [loading, setLoading] = useState(true);
    const [detailView, setDetailView] = useState(null);

    useEffect(() => {
        api('GET', '/api/usage/society').then(s => setSocietyName(s.name)).catch(() => { });
        api('GET', '/api/sa/indram-bills')
            .then(setBills)
            .catch(e => showToast(e.message, 'error'))
            .finally(() => setLoading(false));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    async function loadDetail(bill) {
        try { setDetailView(await api('GET', `/api/sa/indram-bills/${bill.id}`)); }
        catch (e) { showToast(e.message, 'error'); }
    }

    const totalUnpaid = bills
        .filter(b => b.payment_status === 'unpaid')
        .reduce((s, b) => s + toNum(b.total_indram_amount), 0);

    return (
        <div>
            <div className="page-header">
                <div>
                    <div className="page-title">Indram Bill</div>
                    <div style={{ fontSize: 13, color: '#4a5568', marginTop: 2 }}>{societyName}</div>
                </div>
            </div>

            {/* Info banner */}
            <div style={{
                background: 'rgba(0, 255, 65, 0.06)', border: '1px solid rgba(0, 255, 65, 0.2)',
                borderRadius: 12, padding: '14px 18px', marginBottom: 20,
                display: 'flex', alignItems: 'flex-start', gap: 12,
            }}>
                <span style={{ fontSize: 20 }}>ℹ️</span>
                <div style={{ fontSize: 13, color: '#4a5568', lineHeight: 1.7 }}>
                    The Indram platform invoice is automatically generated each time you generate flat bills.
                    It represents the platform service charge collected from your flats on behalf of Indram.
                    Payment status is updated by the Indram team once payment is received.
                </div>
            </div>

            {/* Outstanding banner */}
            {!loading && totalUnpaid > 0 && (
                <div style={{
                    background: '#fff5f5', border: '1px solid #fed7d7', borderRadius: 12,
                    padding: '14px 18px', marginBottom: 20,
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                }}>
                    <div>
                        <div style={{ fontWeight: 700, color: '#c53030', fontSize: 14 }}>Outstanding Amount</div>
                        <div style={{ fontSize: 13, color: '#718096', marginTop: 2 }}>
                            Transfer {fmtCurrency(totalUnpaid)} to Indram to clear pending invoices.
                        </div>
                    </div>
                    <div style={{ fontSize: 24, fontWeight: 700, color: '#c53030' }}>{fmtCurrency(totalUnpaid)}</div>
                </div>
            )}

            {/* Bills table */}
            <div className="table-wrap" style={{ marginBottom: detailView ? 24 : 0 }}>
                <table>
                    <thead>
                        <tr><th>Month</th><th>Total Units (kWh)</th><th>Amount</th><th>Due Date</th><th>Invoice Email</th><th>Payment Status</th><th>Actions</th></tr>
                    </thead>
                    <tbody>
                        {loading ? (
                            <tr className="empty-row"><td colSpan={7}>Loading...</td></tr>
                        ) : bills.length === 0 ? (
                            <tr className="empty-row"><td colSpan={7}>No Indram bills yet — generated automatically when you create flat bills</td></tr>
                        ) : bills.map(b => (
                            <tr key={b.id}>
                                <td><strong>{fmtMonth(b.billing_month)}</strong></td>
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
                                    {b.paid_at && (
                                        <div style={{ fontSize: 11, color: '#718096', marginTop: 2 }}>
                                            {new Date(b.paid_at).toLocaleDateString('en-IN')}
                                        </div>
                                    )}
                                </td>
                                <td>
                                    <button className="btn btn-sm btn-secondary" onClick={() => loadDetail(b)}>Details</button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {/* Detail panel */}
            {detailView && (
                <div style={{ marginTop: 4 }}>
                    <div className="page-header" style={{ marginBottom: 16 }}>
                        <div>
                            <div className="page-title" style={{ fontSize: 18 }}>
                                {fmtMonth(detailView.billing_month)} — Invoice Detail
                            </div>
                            <div style={{ fontSize: 13, color: '#4a5568', marginTop: 3 }}>Breakdown per meter</div>
                        </div>
                        <button className="btn btn-secondary" onClick={() => setDetailView(null)}>Close</button>
                    </div>

                    {/* Summary strip */}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12, marginBottom: 16 }}>
                        {[
                            { label: 'Total Units', value: `${parseFloat(detailView.total_units).toFixed(2)} kWh` },
                            { label: 'Total Amount', value: fmtCurrency(detailView.total_indram_amount) },
                            { label: 'Due Date', value: new Date(detailView.due_date).toLocaleDateString('en-IN') },
                            { label: 'Status', value: detailView.payment_status === 'paid' ? 'Paid' : 'Unpaid' },
                        ].map(item => (
                            <div key={item.label} style={{ background: '#f9fafb', border: '1px solid rgba(0,0,0,0.07)', borderRadius: 10, padding: '12px 16px' }}>
                                <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: '#718096', marginBottom: 4 }}>{item.label}</div>
                                <div style={{ fontSize: 16, fontWeight: 700, color: '#1a202c' }}>{item.value}</div>
                            </div>
                        ))}
                    </div>

                    {/* Meter breakdown */}
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

                    {/* Payment note */}
                    <div style={{
                        marginTop: 16, background: '#f0f9ff', border: '1px solid #bae6fd',
                        borderRadius: 10, padding: '14px 18px', fontSize: 13, color: '#0c4a6e',
                    }}>
                        <strong>How to pay:</strong> Transfer {fmtCurrency(detailView.total_indram_amount)} to Indram using the bank details
                        provided in the invoice PDF sent to your email. Use the invoice number as the payment reference.
                        The Indram team will mark this bill as paid once the transfer is confirmed.
                    </div>
                </div>
            )}
        </div>
    );
}