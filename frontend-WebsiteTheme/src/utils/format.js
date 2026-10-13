// Safe number helpers: null / undefined / NaN / non-numeric values render as 0.
export function toNum(v) {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : 0;
}

export function fmtMoney(v, decimals = 2) {
  return `₹${toNum(v).toFixed(decimals)}`;
}
