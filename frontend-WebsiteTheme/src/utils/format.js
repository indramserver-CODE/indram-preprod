// Safe number helpers: null / undefined / NaN / non-numeric values render as 0.
export function toNum(v) {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : 0;
}

export function fmtMoney(v, decimals = 2) {
  return `₹${toNum(v).toFixed(decimals)}`;
}

// Dates arrive from the API as "YYYY-MM-DD" — parse as local dates, not UTC midnight.
export function fmtDate(iso) {
  if (!iso) return '—';
  const [y, m, d] = String(iso).slice(0, 10).split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

export function fmtPeriod(from, till) {
  return `${fmtDate(from)} – ${fmtDate(till)}`;
}

export function todayIso() {
  const t = new Date();
  return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`;
}

export function addDaysIso(iso, days) {
  const [y, m, d] = iso.split('-').map(Number);
  const t = new Date(y, m - 1, d + days);
  return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`;
}
