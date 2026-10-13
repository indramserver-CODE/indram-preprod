import { useEffect, useState } from 'react';
import { api, apiDownload } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import { toNum, fmtDate, fmtPeriod, todayIso } from '../../utils/format';

// Society admin: Indram's GST tax invoices — one each time a meter's bills are sent.

function fmtCurrency(v) {
    return `₹${toNum(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function SaIndramBills() {
    const { showToast } = useToast();
    const [societyName, setSocietyName] = useState('');
    const [bills, setBills] = useState([]);
    const [loading, setLoading] = useState(true);
    const [detail, setDetail] = useState(null);

    useEffect(() => {
        api('GET', '/api/sa/society').then(s => setSocietyName(s.name)).catch(() => { });
        api('GET', '/api/sa/indram-bills')
            .then(setBills)
            .catch(e => showToast(e.message, 'error'))
            .finally(() => setLoading(false));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    async function openDetail(bill) {
        try { setDetail(await api('GET', `/api/sa/indram-bills/${bill.id}`)); }
        catch (e) { showToast(e.message, 'error'); }
    }

    function download(bill, kind) {
        apiDownload(`/api/sa/indram-bills/${bill.id}/${kind}`).catch(e => showToast(e.message, 'error'));
    }

    const unpaid = bills.filter(b => b.payment_status === 'unpaid');
    const totalUnpaid = unpaid.reduce((s, b) => s + toNum(b.total_payable), 0);
    const lateCount = unpaid.filter(b => b.late_flag).length;

    return (
        <div>
            <div className="page-header">
                <div>
                    <div className="page-title">Indram Bills</div>
                    <div style={{ fontSize: 13, color: '#4a5568', marginTop: 2 }}>{societyName}</div>
                </div>
            </div>

            <div style={{
                background: 'rgba(0, 255, 65, 0.06)', border: '1px solid rgba(0, 255, 65, 0.2)',
                borderRadius: 12, padding: '14px 18px', marginBottom: 20,
                display: 'flex', alignItems: 'flex-start', gap: 12,
            }}>
                <span style={{ fontSize: 20 }}>ℹ️</span>
                <div style={{ fontSize: 13, color: '#4a5568', lineHeight: 1.7 }}>
                    Indram sends a GST tax invoice each time you send a meter's bills to residents: the Indram service
                    charge for the units billed, plus 18% GST. Pay it by the due date — a late fee is added after that.
                    Once Indram records your payment, it shows as Paid and you can download the receipt.
                </div>
            </div>

            {!loading && totalUnpaid > 0 && (
                <div style={{
                    background: '#fff5f5', border: '1px solid #fed7d7', borderRadius: 12,
                    padding: '14px 18px', marginBottom: 20,
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                }}>
                    <div>
                        <div style={{ fontWeight: 700, color: '#c53030', fontSize: 14 }}>Outstanding Amount</div>
                        <div style={{ fontSize: 13, color: '#718096', marginTop: 2 }}>
                            {unpaid.length} unpaid invoice{unpaid.length === 1 ? '' : 's'}
                            {lateCount > 0 && <> · <strong style={{ color: '#c53030' }}>{lateCount} with a late fee</strong></>}
                            . Use the invoice number as the payment reference.
                        </div>
                    </div>
                    <div style={{ fontSize: 24, fontWeight: 700, color: '#c53030' }}>{fmtCurrency(totalUnpaid)}</div>
                </div>
            )}

            <div className="table-wrap" style={{ marginBottom: detail ? 24 : 0 }}>
                <table>
                    <thead>
                        <tr><th>Invoice No.</th><th>Meter · Period</th><th>Units (kWh)</th><th>Charges</th><th>Total (incl. GST)</th><th>Due Date</th><th>Status</th><th>Actions</th></tr>
                    </thead>
                    <tbody>
                        {loading ? (
                            <tr className="empty-row"><td colSpan={8}>Loading...</td></tr>
                        ) : bills.length === 0 ? (
                            <tr className="empty-row"><td colSpan={8}>No Indram invoices yet — one is issued each time you send bills to residents</td></tr>
                        ) : bills.map(b => (
                            <tr key={b.id}>
                                <td style={{ fontFamily: 'monospace', fontSize: 13 }}><strong>{b.invoice_number}</strong></td>
                                <td style={{ fontSize: 13 }}>{b.meter_label}<div style={{ color: '#718096', fontSize: 12 }}>{fmtPeriod(b.period_from, b.period_till)}</div></td>
                                <td>{toNum(b.total_units).toFixed(2)}</td>
                                <td>
                                    {fmtCurrency(b.total_indram_amount)}
                                    {toNum(b.late_fee) > 0 && <div style={{ fontSize: 11, color: '#c53030' }}>+ {fmtCurrency(b.late_fee)} late fee</div>}
                                </td>
                                <td><strong>{fmtCurrency(b.total_payable)}</strong></td>
                                <td style={{ fontSize: 13, color: b.payment_status === 'unpaid' && b.due_date < todayIso() ? '#c53030' : '#4a5568' }}>{fmtDate(b.due_date)}</td>
                                <td>
                                    <span className={`badge ${b.payment_status === 'paid' ? 'badge-green' : 'badge-red'}`}>
                                        {b.payment_status === 'paid' ? 'Paid' : 'Unpaid'}
                                    </span>
                                    {b.late_flag && <span className="badge badge-amber" style={{ marginLeft: 4 }}>Late</span>}
                                    {b.paid_at && <div style={{ fontSize: 11, color: '#718096', marginTop: 2 }}>{fmtDate(b.paid_at)}</div>}
                                </td>
                                <td>
                                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                                        <button className="btn btn-sm btn-secondary" onClick={() => openDetail(b)}>Details</button>
                                        <button className="btn btn-sm btn-secondary" onClick={() => download(b, 'pdf')}>Invoice</button>
                                        {b.has_receipt && <button className="btn btn-sm btn-primary" onClick={() => download(b, 'receipt')}>Download receipt</button>}
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {detail && (
                <div style={{ marginTop: 4 }}>
                    <div className="page-header" style={{ marginBottom: 16 }}>
                        <div>
                            <div className="page-title" style={{ fontSize: 18 }}>Invoice {detail.invoice_number}</div>
                            <div style={{ fontSize: 13, color: '#4a5568', marginTop: 3 }}>
                                {detail.meter_label} ({detail.meter_number}) · {fmtPeriod(detail.period_from, detail.period_till)}
                                {detail.replaces_number && <> · replaces cancelled invoice {detail.replaces_number}</>}
                            </div>
                        </div>
                        <button className="btn btn-secondary" onClick={() => setDetail(null)}>Close</button>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12, marginBottom: 16 }}>
                        {[
                            { label: 'Units', value: `${toNum(detail.total_units).toFixed(3)} kWh @ ${fmtCurrency(detail.indram_rate)}` },
                            { label: 'Charges', value: fmtCurrency(detail.total_indram_amount) },
                            { label: `Late fee${detail.late_fee_pct ? ` (${toNum(detail.late_fee_pct)}%)` : ''}`, value: fmtCurrency(detail.late_fee) },
                            { label: 'CGST 9% + SGST 9%', value: fmtCurrency(toNum(detail.cgst) + toNum(detail.sgst)) },
                            { label: 'Total payable', value: fmtCurrency(detail.total_payable) },
                            { label: 'Due date', value: fmtDate(detail.due_date) },
                        ].map(item => (
                            <div key={item.label} style={{ background: '#f9fafb', border: '1px solid rgba(0,0,0,0.07)', borderRadius: 10, padding: '12px 16px' }}>
                                <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: '#718096', marginBottom: 4 }}>{item.label}</div>
                                <div style={{ fontSize: 16, fontWeight: 700, color: '#1a202c' }}>{item.value}</div>
                            </div>
                        ))}
                    </div>

                    {detail.payment_status === 'unpaid' && (
                        <div style={{
                            background: '#f0f9ff', border: '1px solid #bae6fd',
                            borderRadius: 10, padding: '14px 18px', fontSize: 13, color: '#0c4a6e',
                        }}>
                            <strong>How to pay:</strong> transfer {fmtCurrency(detail.total_payable)} to Indram with
                            {' '}<strong>{detail.invoice_number}</strong> as the reference. Indram marks the invoice Paid once the transfer
                            is confirmed, and the receipt appears here.
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
