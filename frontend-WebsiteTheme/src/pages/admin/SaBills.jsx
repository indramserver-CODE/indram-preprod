import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, apiUpload, apiDownload } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import { fmtMoney, toNum, fmtDate, fmtPeriod, todayIso, addDaysIso } from '../../utils/format';

// Billing flow: Generate (draft + preview, nothing emailed) → Send → mark Paid / Unpaid.

const EMPTY_FORM = {
  meter_id:    '',
  periodFrom:  '',
  periodTill:  '',
  dueDate:     '',
  tariff:      '',
  totalAmount: '',
  totalUnits:  '',
};

const card   = { background: '#f9fafb', border: '1px solid rgba(0,0,0,0.07)', borderRadius: 10, padding: '16px 18px', marginBottom: 20 };
const step   = { fontSize: 12, fontWeight: 700, textTransform: 'uppercase', color: '#718096', marginBottom: 12 };
const hint   = { fontSize: 12, color: '#718096', marginTop: 4, display: 'block' };
const grid2  = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 };
const overlay = {
  display: 'flex', position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)',
  zIndex: 1000, alignItems: 'center', justifyContent: 'center',
};
const dialog = {
  background: '#ffffff', borderRadius: 14, padding: 32, width: '100%', maxWidth: 560,
  boxShadow: '0 24px 64px rgba(0,0,0,0.25)', maxHeight: '92vh', overflowY: 'auto',
};

const STATUS = {
  draft:     ['badge-amber', 'Draft — not sent'],
  sent:      ['badge-green', 'Sent'],
  cancelled: ['badge-gray',  'Cancelled (reissued)'],
};
const PAYMENT = {
  pending: ['badge-gray',  'Pending'],
  paid:    ['badge-green', 'Paid'],
  unpaid:  ['badge-red',   'Unpaid'],
};

function Badge({ map, value }) {
  const [cls, label] = map[value] || ['badge-gray', value];
  return <span className={`badge ${cls}`}>{label}</span>;
}

function Stats({ items }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12, marginBottom: 16 }}>
      {items.map(item => (
        <div key={item.label} style={{ background: '#f9fafb', border: '1px solid rgba(0,0,0,0.07)', borderRadius: 10, padding: '12px 16px' }}>
          <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: '#718096', marginBottom: 4 }}>{item.label}</div>
          <div style={{ fontSize: 16, fontWeight: 700, color: item.color || '#1a202c' }}>{item.value}</div>
        </div>
      ))}
    </div>
  );
}

function Field({ label, children, help, style }) {
  return (
    <div className="form-group" style={{ marginBottom: 0, ...style }}>
      <label>{label}</label>
      {children}
      {help && <small style={hint}>{help}</small>}
    </div>
  );
}

function DialogButtons({ onCancel, cancelLabel = 'Cancel', children }) {
  return (
    <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 8, flexWrap: 'wrap' }}>
      <button className="btn btn-secondary" onClick={onCancel}>{cancelLabel}</button>
      {children}
    </div>
  );
}

// ── Generate / reissue form ───────────────────────────────────────────

function GenerateModal({ meters, initial, reissueOf, indramRate, onClose, onPreview }) {
  const { showToast } = useToast();
  const [form, setForm]         = useState(initial);
  const [period, setPeriod]     = useState(null);   // /next-period response for the selected meter
  const [submitting, setSubmitting] = useState(false);
  const photoRef = useRef(null);

  const isReissue = !!reissueOf;
  const set = patch => setForm(f => ({ ...f, ...patch }));

  // Suggested From/Till for the selected meter (From = day after the last bill's Till)
  useEffect(() => {
    if (isReissue || !form.meter_id) { setPeriod(null); return; }
    let cancelled = false;
    api('GET', `/api/billing/next-period?meter_id=${form.meter_id}`)
      .then(p => {
        if (cancelled) return;
        setPeriod(p);
        // Editing a draft keeps its dates; otherwise suggest the next period for this meter
        const keep = f => f.meter_id === initial.meter_id && initial.periodTill;
        setForm(f => ({
          ...f,
          periodFrom: p.suggested_from || (keep(f) ? initial.periodFrom : ''),
          periodTill: keep(f) ? initial.periodTill : (p.suggested_till || ''),
        }));
      })
      .catch(e => showToast(e.message, 'error'));
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.meter_id]);

  const effectiveRate =
    toNum(form.totalAmount) > 0 && toNum(form.totalUnits) > 0
      ? (toNum(form.totalAmount) / toNum(form.totalUnits)).toFixed(4)
      : null;
  const earliest = form.periodTill ? addDaysIso(form.periodTill, 3) : null;
  const tooEarly = earliest && todayIso() < earliest;
  const fromLocked = !isReissue && !!period?.last_till;

  async function submit() {
    const { meter_id, periodFrom, periodTill, dueDate, tariff, totalAmount, totalUnits } = form;
    if (!isReissue) {
      if (!meter_id)   { showToast('Select a meter', 'error'); return; }
      if (!periodFrom) { showToast('Enter the From date of the MSEB bill', 'error'); return; }
      if (!periodTill) { showToast('Enter the Till date of the MSEB bill', 'error'); return; }
      if (periodTill < periodFrom) { showToast('Till date must be on or after the From date', 'error'); return; }
    }
    if (!dueDate)     { showToast('Set a due date', 'error'); return; }
    if (!totalAmount) { showToast('Enter the total amount on the MSEB bill', 'error'); return; }
    if (!totalUnits)  { showToast('Enter the units on the MSEB bill', 'error'); return; }
    if (!tariff)      { showToast('Enter the per-unit rate on the MSEB bill', 'error'); return; }
    const photo = photoRef.current?.files?.[0];
    if (!isReissue && !photo) { showToast('Upload a photo or PDF of the MSEB bill', 'error'); return; }

    const fd = new FormData();
    if (!isReissue) {
      fd.append('meter_id',    meter_id);
      fd.append('period_from', periodFrom);
      fd.append('period_till', periodTill);
    }
    fd.append('due_date',             dueDate);
    fd.append('tariff',               tariff);
    fd.append('total_bill_amount',    totalAmount);
    fd.append('total_units_consumed', totalUnits);
    if (photo) fd.append('bill_photo', photo);

    setSubmitting(true);
    try {
      const preview = await apiUpload(isReissue ? `/api/billing/${reissueOf.id}/reissue` : '/api/billing/generate', fd);
      onPreview(preview, form);
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={overlay} onClick={onClose}>
      <div style={dialog} onClick={e => e.stopPropagation()}>
        <h2 style={{ fontSize: 18, fontWeight: 700, color: '#1a202c', marginBottom: 4 }}>
          {isReissue ? '↺ Reissue Bill' : '⚡ Generate Bills'}
        </h2>
        <p style={{ fontSize: 13, color: '#4a5568', marginBottom: 20 }}>
          {isReissue
            ? <>Enter the corrected MSEB figures for <strong>{reissueOf.meter_label}</strong>, {fmtPeriod(reissueOf.period_from, reissueOf.period_till)}. The old bills are cancelled and new bill numbers issued when you send.</>
            : 'Enter the MSEB bill for one meter. You will see a preview first — nothing is emailed until you click Send.'}
        </p>

        {!isReissue && (
          <div style={card}>
            <div style={step}>Step 1 — Meter &amp; billing period</div>
            <Field label="Meter *">
              <select value={form.meter_id} onChange={e => set({ meter_id: e.target.value })}>
                <option value="">— Select the meter to bill —</option>
                {meters.map(m => (
                  <option key={m.id} value={String(m.id)}>{m.label} ({m.meter_number})</option>
                ))}
              </select>
            </Field>

            {period?.draft_id && (
              <div style={{ fontSize: 12, color: '#b7791f', marginTop: 8 }}>
                This meter already has an unsent draft — generating again replaces it.
              </div>
            )}

            <div style={{ ...grid2, marginTop: 14 }}>
              <Field label="From date *" help={fromLocked ? `Day after the last bill (ended ${fmtDate(period.last_till)})` : 'Start date on the MSEB bill'}>
                <input type="date" value={form.periodFrom} disabled={fromLocked}
                       onChange={e => set({ periodFrom: e.target.value })} />
              </Field>
              <Field label="Till date *" help="End date on the MSEB bill">
                <input type="date" value={form.periodTill} min={form.periodFrom || undefined}
                       onChange={e => set({ periodTill: e.target.value })} />
              </Field>
            </div>
            {form.meter_id && !period?.last_till && period && (
              <small style={hint}>First bill for this meter — enter the dates exactly as on the MSEB bill.</small>
            )}
            {tooEarly && (
              <div style={{ fontSize: 12, color: '#c53030', marginTop: 8 }}>
                A period ending {fmtDate(form.periodTill)} can be generated from {fmtDate(earliest)}, so late charging records are included.
              </div>
            )}
          </div>
        )}

        <div style={card}>
          <div style={step}>{isReissue ? 'Corrected MSEB bill' : 'Step 2 — MSEB bill details'}</div>
          <div style={grid2}>
            <Field label="Total amount on bill (₹) *" help="Including all MSEB taxes">
              <input type="number" step="0.01" min="0" placeholder="e.g. 45000"
                     value={form.totalAmount} onChange={e => set({ totalAmount: e.target.value })} />
            </Field>
            <Field label="Units on bill (kWh) *">
              <input type="number" step="0.001" min="0" placeholder="e.g. 3000"
                     value={form.totalUnits} onChange={e => set({ totalUnits: e.target.value })} />
            </Field>
            <Field label="Per-unit rate on bill (₹) *" help="Base rate, before taxes">
              <input type="number" step="0.01" min="0" placeholder="e.g. 9.50"
                     value={form.tariff} onChange={e => set({ tariff: e.target.value })} />
            </Field>
            <Field label="Due date for residents *">
              <input type="date" value={form.dueDate} min={form.periodTill || undefined}
                     onChange={e => set({ dueDate: e.target.value })} />
            </Field>
          </div>
          <div className="form-group" style={{ marginTop: 14, marginBottom: 0 }}>
            <label>
              Photo or PDF of the MSEB bill {isReissue
                ? <span style={{ fontWeight: 400, color: '#718096' }}>(optional — keeps the earlier photo if left empty)</span>
                : '*'}
            </label>
            <input ref={photoRef} type="file" accept="image/*,.pdf" style={{ width: 'auto' }} />
            {!isReissue && initial.totalAmount && (
              <small style={hint}>Choose the bill photo again — generating replaces the earlier draft.</small>
            )}
          </div>
        </div>

        {effectiveRate && (
          <div style={{ ...card, background: 'rgba(0,255,65,0.08)', border: '1px solid rgba(0,255,65,0.25)' }}>
            <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: '#4a5568' }}>Effective rate (amount ÷ units)</div>
            <div style={{ fontSize: 24, fontWeight: 700, color: '#1a3c5e', marginTop: 2 }}>
              ₹ {effectiveRate} <span style={{ fontSize: 14, color: '#4a5568', fontWeight: 400 }}>/ kWh</span>
            </div>
            <div style={{ fontSize: 12, color: '#718096', marginTop: 4 }}>
              Indram service: ₹{toNum(indramRate ?? 1.5).toFixed(2)}/kWh + 18% GST (₹{(toNum(indramRate ?? 1.5) * 1.18).toFixed(2)}/kWh)
            </div>
          </div>
        )}

        <DialogButtons onCancel={onClose}>
          <button className="btn btn-primary" onClick={submit} disabled={submitting || tooEarly}>
            {submitting ? 'Preparing preview…' : 'Preview bills →'}
          </button>
        </DialogButtons>
      </div>
    </div>
  );
}

// ── Preview before Send ───────────────────────────────────────────────

function PreviewModal({ preview, meterLabel, onEdit, onDiscard, onSend, onClose }) {
  const [busy, setBusy] = useState(false);
  const isReissue = !!preview.replaces_id;

  async function run(fn) {
    setBusy(true);
    try { await fn(); } finally { setBusy(false); }
  }

  return (
    <div style={overlay} onClick={onClose}>
      <div style={dialog} onClick={e => e.stopPropagation()}>
        <h2 style={{ fontSize: 18, fontWeight: 700, color: '#1a202c', marginBottom: 4 }}>
          Check before sending
        </h2>
        <p style={{ fontSize: 13, color: '#4a5568', marginBottom: 20 }}>
          {meterLabel} · {fmtPeriod(preview.period_from, preview.period_till)} · due {fmtDate(preview.due_date)}
        </p>

        <Stats items={[
          { label: 'Flats billed',      value: preview.total_flats },
          { label: 'Total units',       value: `${toNum(preview.total_units).toFixed(3)} kWh` },
          { label: 'MSEB electricity',  value: fmtMoney(preview.total_electricity) },
          { label: 'Indram (incl. GST)', value: fmtMoney(preview.total_indram) },
          { label: 'Total amount',      value: fmtMoney(preview.total_amount), color: '#1a3c5e' },
          { label: 'Effective rate',    value: `${fmtMoney(preview.effective_rate, 4)}/kWh` },
        ]} />

        {preview.total_flats === 0 && (
          <div style={{ ...card, background: '#fffbeb', border: '1px solid #fcd34d', fontSize: 13 }}>
            No flat charged in this period, so no bills will be emailed. Sending still records the period, so the next bill starts the day after.
          </div>
        )}
        {preview.flats_with_adjustments > 0 && (
          <div style={{ fontSize: 13, color: '#4a5568', marginBottom: 8 }}>
            ℹ️ {preview.flats_with_adjustments} flat(s) include “adjustment” charging from an earlier period that arrived late.
          </div>
        )}
        {preview.flats_without_email > 0 && (
          <div style={{ fontSize: 13, color: '#c53030', marginBottom: 8 }}>
            ⚠️ {preview.flats_without_email} flat(s) have no email address — their bills will be created but not emailed.
          </div>
        )}
        {isReissue && (
          <div style={{ fontSize: 13, color: '#b7791f', marginBottom: 8 }}>
            Sending cancels the earlier bills and Indram invoice for this period. Residents are told to use the new bill number.
          </div>
        )}
        <div style={{ fontSize: 12, color: '#718096', marginBottom: 16 }}>
          Flats with no charging this period get no bill. Open the bill below to download any flat's PDF before sending.
        </div>

        <DialogButtons onCancel={onClose} cancelLabel="Close">
          <button className="btn btn-danger" disabled={busy} onClick={() => run(onDiscard)}>Discard</button>
          <button className="btn btn-secondary" disabled={busy} onClick={onEdit}>Edit figures</button>
          <button className="btn btn-primary" disabled={busy} onClick={() => run(onSend)}>
            {busy ? 'Working…' : `Send ${preview.total_flats} bill${preview.total_flats === 1 ? '' : 's'}`}
          </button>
        </DialogButtons>
      </div>
    </div>
  );
}

// ── Bill detail: flats, payments, downloads ───────────────────────────

function BillDetail({ billId, graceDays, onClose, onChanged }) {
  const { showToast } = useToast();
  const [bill, setBill]         = useState(null);
  const [flatBills, setFlatBills] = useState([]);
  const [query, setQuery]       = useState('');
  const [payFilter, setPayFilter] = useState('');
  const [busyId, setBusyId]     = useState(null);

  async function loadBill() {
    try {
      setBill(await api('GET', `/api/billing/${billId}`));
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  async function loadFlats() {
    const params = new URLSearchParams();
    if (query.trim()) params.set('q', query.trim());
    if (payFilter)    params.set('payment_status', payFilter);
    try {
      setFlatBills(await api('GET', `/api/billing/${billId}/flat-bills?${params}`));
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  useEffect(() => { loadBill(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [billId]);
  useEffect(() => {
    const t = setTimeout(loadFlats, 250);   // debounce search typing
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [billId, query, payFilter]);

  if (!bill) return null;

  const sent = bill.status === 'sent';
  const unpaidFrom = addDaysIso(bill.due_date, graceDays + 1);
  const canMarkUnpaid = todayIso() >= unpaidFrom;
  const totals = bill.flat_bills.reduce((t, fb) => ({
    amount: t.amount + toNum(fb.total_payable),
    paid:   t.paid + (fb.payment_status === 'paid' ? 1 : 0),
    unpaid: t.unpaid + (fb.payment_status === 'unpaid' ? 1 : 0),
  }), { amount: 0, paid: 0, unpaid: 0 });

  async function setPayment(fb, status) {
    if (status === 'unpaid' && !window.confirm(
      `Mark flat ${fb.flat_number} Unpaid?\n\nA late fee is added, the bill is emailed again, and the super admin is asked to switch the charger off.`)) return;
    setBusyId(fb.id);
    try {
      await api('PUT', `/api/billing/flat-bills/${fb.id}/payment`, { payment_status: status });
      showToast(status === 'paid' ? `Flat ${fb.flat_number} marked Paid — receipt emailed` : `Flat ${fb.flat_number} marked Unpaid — late fee added`);
      await Promise.all([loadBill(), loadFlats()]);
      onChanged();
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setBusyId(null);
    }
  }

  async function markAllPaid() {
    const pending = bill.flat_bills.filter(fb => fb.payment_status === 'pending').length;
    if (!pending) { showToast('No pending flats left', 'error'); return; }
    if (!window.confirm(`Mark all ${pending} pending flats as Paid?\n\nMark the unpaid flats first — every flat still pending will be marked Paid and emailed a receipt.`)) return;
    try {
      const res = await api('POST', `/api/billing/${billId}/mark-all-paid`);
      showToast(res.detail);
      await Promise.all([loadBill(), loadFlats()]);
      onChanged();
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  function download(path) {
    apiDownload(path).catch(e => showToast(e.message, 'error'));
  }

  return (
    <div style={{ marginTop: 4 }}>
      <div className="page-header" style={{ marginBottom: 16 }}>
        <div>
          <div className="page-title" style={{ fontSize: 18 }}>
            {bill.meter_label} · {fmtPeriod(bill.period_from, bill.period_till)}
          </div>
          <div style={{ fontSize: 13, color: '#4a5568', marginTop: 3, display: 'flex', gap: 8, alignItems: 'center' }}>
            <Badge map={STATUS} value={bill.status} />
            Meter {bill.meter_number} · due {fmtDate(bill.due_date)}
          </div>
        </div>
        <button className="btn btn-secondary" onClick={onClose}>✕ Close</button>
      </div>

      <Stats items={[
        { label: 'Flats billed',   value: bill.flat_bills.length },
        { label: 'Total amount',   value: fmtMoney(totals.amount) },
        { label: 'Paid',           value: totals.paid, color: '#15803d' },
        { label: 'Unpaid',         value: totals.unpaid, color: totals.unpaid ? '#c53030' : undefined },
        { label: 'MSEB bill',      value: `${fmtMoney(bill.total_bill_amount)} · ${toNum(bill.total_units_consumed).toFixed(0)} kWh` },
        { label: 'Effective rate', value: `${fmtMoney(bill.effective_unit_rate, 4)}/kWh` },
      ]} />

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
        <span style={{ fontSize: 13, color: '#4a5568', alignSelf: 'center' }}>Your bills:</span>
        <button className="btn btn-sm btn-secondary" onClick={() => download(`/api/billing/${billId}/summary/society`)}>Society total</button>
        <button className="btn btn-sm btn-secondary" onClick={() => download(`/api/billing/${billId}/summary/mseb`)}>MSEB total</button>
        <button className="btn btn-sm btn-secondary" onClick={() => download(`/api/billing/${billId}/summary/indram`)}>Indram total + GST</button>
        <button className="btn btn-sm btn-secondary" onClick={() => download(`/api/billing/${billId}/mseb-photo`)}>MSEB bill photo</button>
      </div>

      <div className="selector-bar" style={{ marginBottom: 12, gap: 10, flexWrap: 'wrap' }}>
        <input placeholder="Search flat no. or owner…" value={query} onChange={e => setQuery(e.target.value)} style={{ maxWidth: 240 }} />
        <select value={payFilter} onChange={e => setPayFilter(e.target.value)} style={{ maxWidth: 180 }}>
          <option value="">All payments</option>
          <option value="pending">Pending</option>
          <option value="unpaid">Unpaid</option>
          <option value="paid">Paid</option>
        </select>
        {sent && (
          <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
            <button className="btn btn-sm btn-primary" onClick={markAllPaid}>✓ Mark all as paid</button>
            <div style={{ fontSize: 11, color: '#718096', marginTop: 3 }}>Mark the unpaid flats first</div>
          </div>
        )}
      </div>
      {sent && !canMarkUnpaid && (
        <div style={{ fontSize: 12, color: '#718096', marginBottom: 10 }}>
          Flats can be marked Unpaid from {fmtDate(unpaidFrom)} (due date + {graceDays} grace day{graceDays === 1 ? '' : 's'}).
        </div>
      )}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Bill No.</th>
              <th>Flat</th>
              <th>Owner</th>
              <th>kWh</th>
              <th>MSEB</th>
              <th>Indram + GST</th>
              <th>Total</th>
              <th>Payment</th>
              <th>Email</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {flatBills.length === 0 ? (
              <tr className="empty-row"><td colSpan={10}>{query || payFilter ? 'No flats match' : 'No flat bills — no flat charged in this period'}</td></tr>
            ) : flatBills.map(fb => (
              <tr key={fb.id}>
                <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{fb.bill_number || 'DRAFT'}</td>
                <td><strong>{fb.flat_number}</strong></td>
                <td style={{ color: '#4a5568' }}>{fb.owner_name || '—'}</td>
                <td>
                  {toNum(fb.units_consumed).toFixed(3)}
                  {toNum(fb.adjustment_units) > 0 && (
                    <div style={{ fontSize: 11, color: '#b7791f' }}>incl. {toNum(fb.adjustment_units).toFixed(3)} adj.</div>
                  )}
                </td>
                <td>{fmtMoney(fb.electricity_charges_incl_tax)}</td>
                <td>{fmtMoney(fb.indram_total)}</td>
                <td>
                  <strong>{fmtMoney(fb.total_payable)}</strong>
                  {toNum(fb.late_fee) > 0 && (
                    <div style={{ fontSize: 11, color: '#c53030' }}>+ {fmtMoney(fb.late_fee)} late fee</div>
                  )}
                </td>
                <td>{sent || bill.status === 'cancelled' ? <Badge map={PAYMENT} value={fb.payment_status} /> : '—'}</td>
                <td style={{ fontSize: 12 }}>
                  {!fb.email ? <span style={{ color: '#c53030' }}>No email</span>
                    : fb.email_status === 'sent' ? '✅ Sent'
                    : fb.email_status === 'failed' ? '❌ Failed' : '⏳ Pending'}
                </td>
                <td>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {sent && fb.payment_status !== 'paid' && (
                      <button className="btn btn-sm btn-primary" disabled={busyId === fb.id} onClick={() => setPayment(fb, 'paid')}>Paid</button>
                    )}
                    {sent && fb.payment_status === 'pending' && (
                      <button className="btn btn-sm btn-danger" disabled={busyId === fb.id || !canMarkUnpaid}
                              title={canMarkUnpaid ? '' : `Available from ${fmtDate(unpaidFrom)}`}
                              onClick={() => setPayment(fb, 'unpaid')}>Unpaid</button>
                    )}
                    <button className="btn btn-sm btn-secondary" onClick={() => download(`/api/billing/flat-bills/${fb.id}/pdf`)}>Bill</button>
                    {fb.marked_unpaid_at && (
                      <button className="btn btn-sm btn-secondary" onClick={() => download(`/api/billing/flat-bills/${fb.id}/late-pdf`)}>Bill + late fee</button>
                    )}
                    {fb.payment_status === 'paid' && (
                      <button className="btn btn-sm btn-secondary" onClick={() => download(`/api/billing/flat-bills/${fb.id}/receipt`)}>Receipt</button>
                    )}
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

// ── Page ──────────────────────────────────────────────────────────────

export default function SaBills() {
  const { showToast } = useToast();

  const [society, setSociety]   = useState(null);
  const [meters, setMeters]     = useState([]);
  const [bills, setBills]       = useState([]);
  const [loading, setLoading]   = useState(true);
  const [meterFilter, setMeterFilter] = useState('');

  const [generate, setGenerate] = useState(null);   // { initial, reissueOf }
  const [preview, setPreview]   = useState(null);   // { data, form, reissueOf }
  const [detailId, setDetailId] = useState(null);

  async function loadBills(meterId = meterFilter) {
    setLoading(true);
    try {
      setBills(await api('GET', meterId ? `/api/billing?meter_id=${meterId}` : '/api/billing'));
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    api('GET', '/api/sa/society').then(setSociety).catch(() => {});
    api('GET', '/api/sa/meters').then(setMeters).catch(() => {});
    loadBills('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function meterLabel(id) {
    const m = meters.find(x => x.id === Number(id));
    return m ? `${m.label} (${m.meter_number})` : '';
  }

  function openGenerate(initial = null) {
    setGenerate({
      initial: initial || { ...EMPTY_FORM, meter_id: meters.length === 1 ? String(meters[0].id) : meterFilter },
      reissueOf: null,
    });
  }

  function openReissue(b) {
    setGenerate({ initial: { ...EMPTY_FORM, dueDate: b.due_date }, reissueOf: b });
  }

  async function openDraftPreview(b) {
    try {
      const [data, detail] = await Promise.all([
        api('GET', `/api/billing/${b.id}/preview`),
        api('GET', `/api/billing/${b.id}`),
      ]);
      // Figures for "Edit figures" — the draft's own values
      const form = {
        meter_id:    String(detail.meter_id),
        periodFrom:  detail.period_from,
        periodTill:  detail.period_till,
        dueDate:     detail.due_date,
        tariff:      String(toNum(detail.tariff)),
        totalAmount: String(toNum(detail.total_bill_amount)),
        totalUnits:  String(toNum(detail.total_units_consumed)),
      };
      const reissueOf = b.replaces_id ? bills.find(x => x.id === b.replaces_id) || null : null;
      setPreview({ data, form, reissueOf, meterLabel: `${b.meter_label} (${b.meter_number})` });
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  async function sendDraft() {
    const id = preview.data.monthly_bill_id;
    try {
      const res = await api('POST', `/api/billing/${id}/send`);
      showToast(`Bills sent for ${res.meter_label}${res.invoice_number ? ` · Indram invoice ${res.invoice_number}` : ''}. Emails are going out…`);
      setPreview(null);
      setDetailId(id);
      loadBills();
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  async function discardDraft(id = preview?.data.monthly_bill_id) {
    try {
      await api('DELETE', `/api/billing/${id}`);
      showToast('Draft discarded');
      setPreview(null);
      if (detailId === id) setDetailId(null);
      loadBills();
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  const drafts = bills.filter(b => b.status === 'draft');
  const missingPaymentDetails = society && !society.payee_name && !society.upi_id && !society.bank_account_no;

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Billing</div>
          <div style={{ fontSize: 13, color: '#4a5568', marginTop: 2 }}>{society?.name}</div>
        </div>
        <button className="btn btn-primary" onClick={() => openGenerate()}>⚡ Generate Bills</button>
      </div>

      {missingPaymentDetails && (
        <div style={{ ...card, background: '#fffbeb', border: '1px solid #fcd34d', fontSize: 13 }}>
          Your payment details and letterhead aren't set yet, so bills won't tell residents how to pay.{' '}
          <Link to="/admin/billing-settings">Set them up in Billing Settings →</Link>
        </div>
      )}

      {drafts.map(d => (
        <div key={d.id} style={{ ...card, background: '#fffbeb', border: '1px solid #fcd34d', display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <div style={{ flex: 1, fontSize: 13 }}>
            <strong>Draft not sent:</strong> {d.meter_label}, {fmtPeriod(d.period_from, d.period_till)} — {d.total_flats} flats, {fmtMoney(d.total_amount)}
            {d.replaces_id && ' (reissue)'}
          </div>
          <button className="btn btn-sm btn-primary" onClick={() => openDraftPreview(d)}>Review &amp; send</button>
          <button className="btn btn-sm btn-danger" onClick={() => discardDraft(d.id)}>Discard</button>
        </div>
      ))}

      {meters.length > 1 && (
        <div className="selector-bar" style={{ marginBottom: 16 }}>
          <label style={{ margin: 0, whiteSpace: 'nowrap' }}>⚡ Filter by Meter:</label>
          <select value={meterFilter} onChange={e => { setMeterFilter(e.target.value); loadBills(e.target.value); }} style={{ maxWidth: 320 }}>
            <option value="">All Meters</option>
            {meters.map(m => <option key={m.id} value={String(m.id)}>{m.label} ({m.meter_number})</option>)}
          </select>
        </div>
      )}

      <div className="table-wrap" style={{ marginBottom: detailId ? 24 : 0 }}>
        <table>
          <thead>
            <tr>
              <th>Billing period</th>
              {meters.length > 1 && <th>Meter</th>}
              <th>Status</th>
              <th>Flats</th>
              <th>Total</th>
              <th>Due date</th>
              <th>Payments</th>
              <th>Emails</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr className="empty-row"><td colSpan={9}>Loading…</td></tr>
            ) : bills.length === 0 ? (
              <tr className="empty-row"><td colSpan={9}>No bills yet — click ⚡ Generate Bills to start</td></tr>
            ) : bills.map(b => (
              <tr key={b.id} style={b.status === 'cancelled' ? { opacity: 0.6 } : undefined}>
                <td><strong>{fmtPeriod(b.period_from, b.period_till)}</strong></td>
                {meters.length > 1 && <td>{b.meter_label}</td>}
                <td><Badge map={STATUS} value={b.status} /></td>
                <td><span className="badge badge-blue">{b.total_flats}</span></td>
                <td>{fmtMoney(b.total_amount)}</td>
                <td style={{ fontSize: 13, color: '#4a5568' }}>{fmtDate(b.due_date)}</td>
                <td style={{ fontSize: 12 }}>
                  {b.status === 'sent' ? (
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                      <span className="badge badge-green">{b.flats_paid} paid</span>
                      {b.flats_unpaid > 0 && <span className="badge badge-red">{b.flats_unpaid} unpaid</span>}
                      {b.total_flats - b.flats_paid - b.flats_unpaid > 0 && (
                        <span className="badge badge-gray">{b.total_flats - b.flats_paid - b.flats_unpaid} pending</span>
                      )}
                    </div>
                  ) : '—'}
                </td>
                <td style={{ fontSize: 12 }}>
                  {b.status === 'draft' ? '—' : (
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                      {b.emails_sent > 0 && <span className="badge badge-green">✅ {b.emails_sent}</span>}
                      {b.emails_failed > 0 && <span className="badge badge-red">❌ {b.emails_failed}</span>}
                      {b.emails_pending > 0 && <span className="badge badge-gray">⏳ {b.emails_pending}</span>}
                    </div>
                  )}
                </td>
                <td>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button className="btn btn-sm btn-secondary" onClick={() => setDetailId(b.id)}>Details</button>
                    {b.status === 'draft' && <button className="btn btn-sm btn-primary" onClick={() => openDraftPreview(b)}>Send</button>}
                    {b.status === 'sent' && <button className="btn btn-sm btn-secondary" onClick={() => openReissue(b)} title="Wrong MSEB figures? Cancel and reissue">Reissue</button>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {detailId && (
        <BillDetail
          key={detailId}
          billId={detailId}
          graceDays={society?.resident_late_fee_grace_days ?? 0}
          onClose={() => setDetailId(null)}
          onChanged={() => loadBills()}
        />
      )}

      {generate && (
        <GenerateModal
          meters={meters}
          initial={generate.initial}
          reissueOf={generate.reissueOf}
          indramRate={society?.indram_rate}
          onClose={() => setGenerate(null)}
          onPreview={(data, form) => {
            const reissueOf = generate.reissueOf;
            setGenerate(null);
            setPreview({ data, form, reissueOf, meterLabel: reissueOf ? reissueOf.meter_label : meterLabel(form.meter_id) });
            loadBills();
          }}
        />
      )}

      {preview && (
        <PreviewModal
          preview={preview.data}
          meterLabel={preview.meterLabel}
          onClose={() => setPreview(null)}
          onDiscard={() => discardDraft()}
          onSend={sendDraft}
          onEdit={() => {
            const { form, reissueOf } = preview;
            setPreview(null);
            setGenerate({ initial: form, reissueOf });
          }}
        />
      )}
    </div>
  );
}
