import { useEffect, useRef, useState } from 'react';
import { api, apiUpload } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import { fmtMoney, toNum } from '../../utils/format';

function todayMonth() {
  const t = new Date();
  return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}`;
}

function fmtMonth(dateStr) {
  return new Date(dateStr + '-02').toLocaleDateString('en-IN', { month: 'long', year: 'numeric' });
}

const EMPTY_FORM = {
  meter_id:    '',
  month:       todayMonth(),
  tariff:      '',
  totalAmount: '',
  totalUnits:  '',
  dueDate:     '',
};

export default function SaBills() {
  const { showToast } = useToast();

  const [societyName, setSocietyName]   = useState('');
  const [indramRate, setIndramRate]     = useState(null);   // null = default ₹1.50
  const [meters, setMeters]             = useState([]);
  const [bills, setBills]             = useState([]);
  const [loading, setLoading]         = useState(true);

  // Filter
  const [meterFilter, setMeterFilter] = useState('');  // '' = all meters

  // Generate modal
  const [modalOpen, setModalOpen]     = useState(false);
  const [form, setForm]               = useState(EMPTY_FORM);
  const photoRef                      = useRef(null);
  const [submitting, setSubmitting]   = useState(false);

  // Detail drawer
  const [detailView, setDetailView]   = useState(null);  // { title, meter, flatBills, bill }

  // ── Initial load ──────────────────────────────────────────────────────

  async function loadBills(meterId = null) {
    setLoading(true);
    try {
      const path = meterId ? `/api/billing?meter_id=${meterId}` : '/api/billing';
      const data = await api('GET', path);
      setBills(data);
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    api('GET', '/api/usage/society')
      .then(s => {
        setSocietyName(s.name);
        setIndramRate(s.indram_rate ?? null);
      })
      .catch(() => {});

    api('GET', '/api/sa/meters')
      .then(data => {
        setMeters(data);
        // Auto-select if single meter
        if (data.length === 1) {
          setMeterFilter(String(data[0].id));
        }
      })
      .catch(() => {});

    loadBills();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Meter filter change ───────────────────────────────────────────────

  function handleMeterFilterChange(id) {
    const val = id || '';
    setMeterFilter(val);
    // Pass null when clearing so loadBills doesn't append ?meter_id= (which causes a 422)
    loadBills(val || null);
  }

  // ── Generate modal ────────────────────────────────────────────────────

  function openGenerateModal() {
    setForm({
      ...EMPTY_FORM,
      // Pre-select meter if only one, or if filter is active
      meter_id: meters.length === 1
        ? String(meters[0].id)
        : meterFilter || '',
    });
    if (photoRef.current) photoRef.current.value = '';
    setModalOpen(true);
  }

  const selectedMeter = form.meter_id
    ? meters.find(m => m.id === parseInt(form.meter_id, 10))
    : null;

  const effectiveRate =
    parseFloat(form.totalAmount) > 0 && parseFloat(form.totalUnits) > 0
      ? (parseFloat(form.totalAmount) / parseFloat(form.totalUnits)).toFixed(4)
      : null;

  async function generateBills() {
    const { meter_id, month, tariff, totalAmount, totalUnits, dueDate } = form;
    if (!meter_id) { showToast('Select a meter', 'error'); return; }
    if (!month)    { showToast('Select billing month', 'error'); return; }
    if (!tariff)   { showToast('Enter tariff rate', 'error'); return; }
    if (!totalAmount) { showToast('Enter total bill amount', 'error'); return; }
    if (!totalUnits)  { showToast('Enter total units consumed', 'error'); return; }
    if (!dueDate)     { showToast('Set a due date', 'error'); return; }

    const fd = new FormData();
    fd.append('meter_id',             meter_id);
    fd.append('billing_month',        month);
    fd.append('tariff',               tariff);
    fd.append('total_bill_amount',    totalAmount);
    fd.append('total_units_consumed', totalUnits);
    fd.append('due_date',             dueDate);
    const photoFile = photoRef.current?.files?.[0];
    if (photoFile) fd.append('bill_photo', photoFile);

    setSubmitting(true);
    try {
      const res = await apiUpload('/api/billing/generate', fd);
      setModalOpen(false);
      showToast(
        `✅ Bills generated for ${res.total_flats} flats under ${res.meter_label}. ` +
        `Effective rate: ${fmtMoney(res.effective_rate, 4)}/kWh. Emails being dispatched…`
      );
      loadBills(meterFilter);
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setSubmitting(false);
    }
  }

  // ── Detail view ───────────────────────────────────────────────────────

  async function loadDetail(bill) {
    try {
      const data = await api('GET', `/api/billing/${bill.id}`);
      const meter = meters.find(m => m.id === bill.meter_id);
      setDetailView({
        title:     `${fmtMonth(bill.billing_month)} — ${bill.meter_label || meter?.label || ''}`,
        flatBills: data.flat_bills,
        bill:      data,
        meter,
      });
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  async function deleteBill(bill) {
    if (!window.confirm(`Delete bill for ${fmtMonth(bill.billing_month)} (${bill.meter_label})? This cannot be undone.`)) return;
    try {
      await api('DELETE', `/api/billing/${bill.id}`);
      showToast('Bill deleted — you can regenerate it now');
      setDetailView(null);
      loadBills(meterFilter || null);
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  // ── Meter badge helper ────────────────────────────────────────────────

  function MeterBadge({ bill }) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <span style={{ fontWeight: 600, fontSize: 13 }}>
          {bill.meter_label || '—'}
        </span>
        <span style={{
          fontFamily: 'monospace', fontSize: 11,
          color: '#718096', background: '#f4f4f4',
          padding: '1px 6px', borderRadius: 4, display: 'inline-block',
        }}>
          {bill.meter_number || '—'}
        </span>
      </div>
    );
  }

  // ── Render ────────────────────────────────────────────────────────────

  return (
    <div>
      {/* Page header */}
      <div className="page-header">
        <div>
          <div className="page-title">Monthly Billing</div>
          <div style={{ fontSize: 13, color: '#4a5568', marginTop: 2 }}>{societyName}</div>
        </div>
        <button className="btn btn-primary" onClick={openGenerateModal}>
          ⚡ Generate Bills
        </button>
      </div>

      {/* Meter filter — only when multiple meters */}
      {meters.length > 1 && (
        <div className="selector-bar" style={{ marginBottom: 16 }}>
          <label style={{ margin: 0, whiteSpace: 'nowrap' }}>⚡ Filter by Meter:</label>
          <select
            value={meterFilter}
            onChange={e => handleMeterFilterChange(e.target.value)}
            style={{ maxWidth: 320 }}
          >
            <option value="">All Meters</option>
            {meters.map(m => (
              <option key={m.id} value={String(m.id)}>
                {m.label} ({m.meter_number})
              </option>
            ))}
          </select>
          {meterFilter && (
            <button
              className="btn btn-sm btn-secondary"
              onClick={() => handleMeterFilterChange(null)}
            >
              Show all
            </button>
          )}
        </div>
      )}

      {/* Bills list */}
      <div className="table-wrap" style={{ marginBottom: detailView ? 24 : 0 }}>
        <table>
          <thead>
            <tr>
              <th>Billing Month</th>
              {meters.length > 1 && <th>Meter</th>}
              <th>Total Units (kWh)</th>
              <th>Total Bill (₹)</th>
              <th>Eff. Rate (₹/kWh)</th>
              <th>Due Date</th>
              <th>Flats</th>
              <th>Email Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr className="empty-row">
                <td colSpan={meters.length > 1 ? 9 : 8}>Loading…</td>
              </tr>
            ) : bills.length === 0 ? (
              <tr className="empty-row">
                <td colSpan={meters.length > 1 ? 9 : 8}>
                  {meterFilter
                    ? 'No bills generated for this meter yet'
                    : 'No bills generated yet — click ⚡ Generate Bills to start'}
                </td>
              </tr>
            ) : (
              bills.map(b => (
                <tr key={b.id}>
                  <td>
                    <strong>{fmtMonth(b.billing_month)}</strong>
                  </td>
                  {meters.length > 1 && (
                    <td><MeterBadge bill={b} /></td>
                  )}
                  <td>{parseFloat(b.total_units_consumed).toFixed(4)}</td>
                  <td>{fmtMoney(b.total_bill_amount)}</td>
                  <td>{fmtMoney(b.effective_unit_rate, 4)}</td>
                  <td style={{ fontSize: 13, color: '#4a5568' }}>
                    {new Date(b.due_date).toLocaleDateString('en-IN')}
                  </td>
                  <td>
                    <span className="badge badge-blue">{b.total_flats}</span>
                  </td>
                  <td>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                      {b.emails_sent > 0 && (
                        <span className="badge badge-green">✅ {b.emails_sent} sent</span>
                      )}
                      {b.emails_failed > 0 && (
                        <span className="badge badge-red">❌ {b.emails_failed} failed</span>
                      )}
                      {b.emails_pending > 0 && (
                        <span className="badge badge-gray">⏳ {b.emails_pending} pending</span>
                      )}
                    </div>
                  </td>
                  <td style={{ display: 'flex', gap: 6 }}>
                    <button
                      className="btn btn-sm btn-secondary"
                      onClick={() => loadDetail(b)}
                    >
                      Details
                    </button>
                    <button
                      className="btn btn-sm btn-danger"
                      onClick={() => deleteBill(b)}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Flat bills detail panel */}
      {detailView && (
        <div style={{ marginTop: 4 }}>
          <div className="page-header" style={{ marginBottom: 16 }}>
            <div>
              <div className="page-title" style={{ fontSize: 18 }}>
                {detailView.title}
              </div>
              {detailView.meter && (
                <div style={{ fontSize: 13, color: '#4a5568', marginTop: 3 }}>
                  Meter: {detailView.meter.label} — {detailView.meter.meter_number}
                  {detailView.meter.location ? ` · ${detailView.meter.location}` : ''}
                </div>
              )}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                className="btn btn-secondary"
                onClick={() => setDetailView(null)}
              >
                ✕ Close
              </button>
            </div>
          </div>

          {/* Summary strip */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
            gap: 12,
            marginBottom: 16,
          }}>
            {[
              { label: 'Effective Rate', value: `${fmtMoney(detailView.bill.effective_unit_rate, 4)}/kWh` },
              { label: 'Total Units', value: `${parseFloat(detailView.bill.total_units_consumed).toFixed(2)} kWh` },
              { label: 'Total Bill', value: fmtMoney(detailView.bill.total_bill_amount) },
              { label: 'Due Date', value: new Date(detailView.bill.due_date).toLocaleDateString('en-IN') },
            ].map(item => (
              <div key={item.label} style={{
                background: '#f9fafb',
                border: '1px solid rgba(0,0,0,0.07)',
                borderRadius: 10,
                padding: '12px 16px',
              }}>
                <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: '#718096', marginBottom: 4 }}>
                  {item.label}
                </div>
                <div style={{ fontSize: 16, fontWeight: 700, color: '#1a202c' }}>
                  {item.value}
                </div>
              </div>
            ))}
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Flat No.</th>
                  <th>Owner</th>
                  <th>Units (kWh)</th>
                  <th>Electricity Incl. Tax (₹)</th>
                  <th>Indram (₹)</th>
                  <th>Total Payable (₹)</th>
                  <th>Email</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {detailView.flatBills.length === 0 ? (
                  <tr className="empty-row">
                    <td colSpan={8}>No flat bills found</td>
                  </tr>
                ) : (
                  detailView.flatBills.map(fb => (
                    <tr key={fb.id}>
                      <td><strong>{fb.flat_number || '—'}</strong></td>
                      <td style={{ color: '#4a5568' }}>{fb.owner_name || '—'}</td>
                      <td>{parseFloat(fb.units_consumed).toFixed(4)}</td>
                      <td>{fmtMoney(fb.electricity_charges_incl_tax)}</td>
                      <td>{fmtMoney(fb.indram_charges)}</td>
                      <td><strong>{fmtMoney(fb.total_payable)}</strong></td>
                      <td style={{ fontSize: 12, color: '#4a5568' }}>{fb.email || '—'}</td>
                      <td>
                        <span className={`badge ${
                          fb.email_status === 'sent'   ? 'badge-green' :
                          fb.email_status === 'failed' ? 'badge-red'   : 'badge-gray'
                        }`}>
                          {fb.email_status === 'sent'   ? '✅ Sent'    :
                           fb.email_status === 'failed' ? '❌ Failed'  : '⏳ Pending'}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Generate Bills modal */}
      {modalOpen && (
        <div
          style={{
            display: 'flex', position: 'fixed', inset: 0,
            background: 'rgba(0,0,0,0.45)', zIndex: 1000,
            alignItems: 'center', justifyContent: 'center',
          }}
          onClick={() => setModalOpen(false)}
        >
          <div
            style={{
              background: '#ffffff', borderRadius: 14, padding: 32,
              width: '100%', maxWidth: 540,
              boxShadow: '0 24px 64px rgba(0,0,0,0.25)',
              maxHeight: '92vh', overflowY: 'auto',
            }}
            onClick={e => e.stopPropagation()}
          >
            <h2 style={{ fontSize: 18, fontWeight: 700, color: '#1a202c', marginBottom: 4 }}>
              ⚡ Generate Monthly Bills
            </h2>
            <p style={{ fontSize: 13, color: '#4a5568', marginBottom: 24 }}>
              Enter the MSEB bill details for one meter. Bills are generated individually per meter.
            </p>

            {/* Step 1 — Meter selection */}
            <div style={{
              background: '#f9fafb', border: '1px solid rgba(0,0,0,0.07)',
              borderRadius: 10, padding: '16px 18px', marginBottom: 20,
            }}>
              <div style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', color: '#718096', marginBottom: 10 }}>
                Step 1 — Select Meter
              </div>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label>Meter *</label>
                <select
                  value={form.meter_id}
                  onChange={e => setForm({ ...form, meter_id: e.target.value })}
                >
                  <option value="">— Select the meter to bill —</option>
                  {meters.map(m => (
                    <option key={m.id} value={String(m.id)}>
                      {m.label} ({m.meter_number})
                      {m.charger_count ? ` — ${m.charger_count} charger${m.charger_count !== 1 ? 's' : ''}` : ''}
                    </option>
                  ))}
                </select>
              </div>
              {selectedMeter?.location && (
                <div style={{ fontSize: 12, color: '#4a5568', marginTop: 8 }}>
                  📍 {selectedMeter.location}
                  {selectedMeter.sanctioned_load
                    ? ` · ⚡ ${parseFloat(selectedMeter.sanctioned_load).toFixed(1)} kW sanctioned`
                    : ''}
                </div>
              )}
            </div>

            {/* Step 2 — Bill details */}
            <div style={{
              background: '#f9fafb', border: '1px solid rgba(0,0,0,0.07)',
              borderRadius: 10, padding: '16px 18px', marginBottom: 20,
            }}>
              <div style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', color: '#718096', marginBottom: 14 }}>
                Step 2 — MSEB Bill Details
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label>Billing Month *</label>
                  <input
                    type="month"
                    value={form.month}
                    onChange={e => setForm({ ...form, month: e.target.value })}
                  />
                </div>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label>Payment Due Date *</label>
                  <input
                    type="date"
                    value={form.dueDate}
                    onChange={e => setForm({ ...form, dueDate: e.target.value })}
                  />
                </div>
              </div>

              <div className="form-group" style={{ marginTop: 14, marginBottom: 0 }}>
                <label>Total MSEB Bill Amount ₹ (incl. all taxes) *</label>
                <input
                  type="number" step="0.01"
                  placeholder="e.g. 45000"
                  value={form.totalAmount}
                  onChange={e => setForm({ ...form, totalAmount: e.target.value })}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginTop: 14 }}>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label>Total Units Consumed (kWh) *</label>
                  <input
                    type="number" step="0.001"
                    placeholder="e.g. 3000"
                    value={form.totalUnits}
                    onChange={e => setForm({ ...form, totalUnits: e.target.value })}
                  />
                </div>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label>Base Tariff ₹/unit (excl. taxes) *</label>
                  <input
                    type="number" step="0.01"
                    placeholder="e.g. 8.50"
                    value={form.tariff}
                    onChange={e => setForm({ ...form, tariff: e.target.value })}
                  />
                </div>
              </div>
            </div>

            {/* Effective rate preview */}
            {effectiveRate && (
              <div style={{
                background: 'rgba(0, 255, 65, 0.08)',
                border: '1px solid rgba(0, 255, 65, 0.25)',
                borderRadius: 10, padding: '14px 18px', marginBottom: 20,
                display: 'flex', alignItems: 'center', gap: 16,
              }}>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: '#4a5568' }}>
                    Effective Unit Rate (B ÷ U)
                  </div>
                  <div style={{ fontSize: 26, fontWeight: 700, color: '#1a3c5e', marginTop: 2 }}>
                    ₹ {effectiveRate} <span style={{ fontSize: 14, color: '#4a5568', fontWeight: 400 }}>/ kWh</span>
                  </div>
                  <div style={{ fontSize: 12, color: '#718096', marginTop: 2 }}>
                    Total bill ÷ total units — all MSEB taxes included
                  </div>
                </div>
              </div>
            )}

            {/* INDRAM rate info */}
            <div style={{
              background: '#f0f9ff',
              border: '1px solid #bae6fd',
              borderRadius: 10,
              padding: '12px 16px',
              marginBottom: 20,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}>
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: '#0369a1', marginBottom: 2 }}>
                  INDRAM Platform Charge
                </div>
                <div style={{ fontSize: 13, color: '#0c4a6e' }}>
                  ₹{indramRate !== null ? toNum(indramRate).toFixed(4) : '1.5000'}/kWh
                  {indramRate === null && (
                    <span style={{ fontSize: 11, color: '#718096', marginLeft: 6 }}>
                      (default — set a custom rate in Societies settings)
                    </span>
                  )}
                </div>
              </div>
              <span style={{ fontSize: 20 }}>⚡</span>
            </div>

            {/* Step 3 — Bill photo */}
            <div className="form-group">
              <label>
                MSEB Bill Photo / PDF{' '}
                <span style={{ fontWeight: 400, color: '#718096' }}>(optional — for audit record only)</span>
              </label>
              <input ref={photoRef} type="file" accept="image/*,.pdf" style={{ width: 'auto' }} />
            </div>

            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 8 }}>
              <button
                onClick={() => setModalOpen(false)}
                style={{
                  padding: '9px 20px', border: '1.5px solid rgba(0,0,0,0.12)',
                  borderRadius: 8, background: '#ffffff', color: '#4a5568',
                  fontSize: 14, cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                onClick={generateBills}
                disabled={submitting}
                style={{
                  padding: '9px 28px', border: 'none', borderRadius: 8,
                  background: submitting ? '#a0aec0' : '#00ff41',
                  color: '#051005', fontSize: 14, fontWeight: 700,
                  cursor: submitting ? 'not-allowed' : 'pointer',
                }}
              >
                {submitting ? 'Generating…' : 'Generate Bills'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}