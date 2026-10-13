import { useEffect, useRef, useState } from 'react';
import { api, apiUpload, API_BASE, getToken } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import { toNum } from '../../utils/format';

// Society admin: what residents see on every bill and receipt.

const FIELDS = [
  ['payee_name',      'Pay to (account holder)', 'e.g. PK Hillcrest Co-op Housing Society'],
  ['bank_name',       'Bank',                    'e.g. HDFC Bank, Baner branch'],
  ['bank_account_no', 'Account number',          ''],
  ['bank_ifsc',       'IFSC',                    'e.g. HDFC0001234'],
  ['upi_id',          'UPI ID',                  'e.g. society@hdfc'],
];

const card = { background: '#ffffff', border: '1px solid rgba(0,0,0,0.08)', borderRadius: 12, padding: 24, marginBottom: 20 };
const h2   = { fontSize: 16, fontWeight: 700, color: '#1a202c', marginBottom: 4 };
const sub  = { fontSize: 13, color: '#4a5568', marginBottom: 16 };

export default function SaBillingSettings() {
  const { showToast } = useToast();
  const [society, setSociety]   = useState(null);
  const [form, setForm]         = useState({});
  const [saving, setSaving]     = useState(false);
  const [uploading, setUploading] = useState(false);
  const [letterheadUrl, setLetterheadUrl] = useState(null);
  const fileRef = useRef(null);

  async function loadLetterhead() {
    setLetterheadUrl(old => { if (old) URL.revokeObjectURL(old); return null; });
    const res = await fetch(`${API_BASE}/api/sa/society/letterhead`, { headers: { Authorization: `Bearer ${getToken()}` } });
    if (res.ok) setLetterheadUrl(URL.createObjectURL(await res.blob()));
  }

  function apply(s) {
    setSociety(s);
    setForm(Object.fromEntries([...FIELDS.map(([k]) => k), 'payment_note'].map(k => [k, s[k] || ''])));
  }

  useEffect(() => {
    api('GET', '/api/sa/society')
      .then(s => { apply(s); if (s.has_letterhead) loadLetterhead(); })
      .catch(e => showToast(e.message, 'error'));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function savePayment() {
    setSaving(true);
    try {
      apply(await api('PUT', '/api/sa/society/payment-details', form));
      showToast('Payment details saved — they appear on the next bills you send');
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setSaving(false);
    }
  }

  async function uploadLetterhead() {
    const file = fileRef.current?.files?.[0];
    if (!file) { showToast('Choose a PNG or JPG image first', 'error'); return; }
    if (file.size > 2 * 1024 * 1024) { showToast('Letterhead must be 2 MB or smaller', 'error'); return; }
    const fd = new FormData();
    fd.append('file', file);
    setUploading(true);
    try {
      apply(await apiUpload('/api/sa/society/letterhead', fd, 'PUT'));
      fileRef.current.value = '';
      await loadLetterhead();
      showToast('Letterhead uploaded');
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setUploading(false);
    }
  }

  async function removeLetterhead() {
    if (!window.confirm('Remove the letterhead? New bills will show the society name as a plain header.')) return;
    try {
      await api('DELETE', '/api/sa/society/letterhead');
      setSociety(s => ({ ...s, has_letterhead: false }));
      setLetterheadUrl(old => { if (old) URL.revokeObjectURL(old); return null; });
      showToast('Letterhead removed');
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  if (!society) return <div style={{ color: '#4a5568' }}>Loading…</div>;

  return (
    <div style={{ maxWidth: 760 }}>
      <div className="page-header">
        <div>
          <div className="page-title">Billing Settings</div>
          <div style={{ fontSize: 13, color: '#4a5568', marginTop: 2 }}>{society.name}</div>
        </div>
      </div>

      <div style={card}>
        <div style={h2}>Letterhead</div>
        <div style={sub}>Printed at the top of every resident bill, receipt and your society total. PNG or JPG, up to 2 MB — a wide banner works best.</div>
        {letterheadUrl ? (
          <img src={letterheadUrl} alt="Society letterhead"
               style={{ maxWidth: '100%', maxHeight: 160, border: '1px solid rgba(0,0,0,0.08)', borderRadius: 8, marginBottom: 12 }} />
        ) : (
          <div style={{ fontSize: 13, color: '#718096', fontStyle: 'italic', marginBottom: 12 }}>
            No letterhead yet — bills show the society name and address as a plain header.
          </div>
        )}
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <input ref={fileRef} type="file" accept="image/png,image/jpeg" style={{ width: 'auto' }} />
          <button className="btn btn-primary" onClick={uploadLetterhead} disabled={uploading}>
            {uploading ? 'Uploading…' : society.has_letterhead ? 'Replace' : 'Upload'}
          </button>
          {society.has_letterhead && <button className="btn btn-danger" onClick={removeLetterhead}>Remove</button>}
        </div>
      </div>

      <div style={card}>
        <div style={h2}>Payment details</div>
        <div style={sub}>Shown on every bill so residents know how to pay the society.</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
          {FIELDS.map(([key, label, placeholder]) => (
            <div key={key} className="form-group" style={{ marginBottom: 0 }}>
              <label>{label}</label>
              <input placeholder={placeholder} value={form[key] || ''} onChange={e => setForm({ ...form, [key]: e.target.value })} />
            </div>
          ))}
        </div>
        <div className="form-group" style={{ marginTop: 14 }}>
          <label>Note for residents <span style={{ fontWeight: 400, color: '#718096' }}>(optional)</span></label>
          <input placeholder="e.g. Mention your flat number in the payment remarks"
                 value={form.payment_note || ''} onChange={e => setForm({ ...form, payment_note: e.target.value })} />
        </div>
        <button className="btn btn-primary" onClick={savePayment} disabled={saving}>{saving ? 'Saving…' : 'Save payment details'}</button>
      </div>

      <div style={card}>
        <div style={h2}>Rates &amp; late fees</div>
        <div style={sub}>Set by Indram. Contact Indram to change them.</div>
        <table style={{ width: '100%', fontSize: 14 }}>
          <tbody>
            {[
              ['Indram service charge', `₹${toNum(society.indram_rate).toFixed(2)}/kWh + 18% GST`],
              ['Late fee on residents’ bills', `${toNum(society.resident_late_fee_pct)}% of the bill, from ${society.resident_late_fee_grace_days} day(s) after the due date`],
              ['Late fee on Indram’s invoice', `${toNum(society.indram_late_fee_pct)}% + GST, from ${society.indram_late_fee_grace_days} day(s) after the due date`],
              ['Society GSTIN', society.gstin || '—'],
            ].map(([k, v]) => (
              <tr key={k}>
                <td style={{ padding: '6px 0', color: '#4a5568', width: '45%' }}>{k}</td>
                <td style={{ padding: '6px 0', fontWeight: 600 }}>{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
