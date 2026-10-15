// API client

// VITE_API_BASE is injected at build time (see .github/workflows/deploy.yml).
// When it is not set we fall back to the old hostname-based logic so local dev
// and the existing production build keep working unchanged.
const _envBase = (import.meta.env.VITE_API_BASE || '').replace(/\/+$/, '');

export const API_BASE =
  _envBase ||
  (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? `http://${window.location.hostname}:8000`
    : 'https://api.indram.in');

export function getToken() { return localStorage.getItem('token'); }
export function getRole() { return localStorage.getItem('role'); }
export function getFullName() { return localStorage.getItem('full_name') || 'Admin'; }

export function authHeaders() {
  return { Authorization: `Bearer ${getToken()}`, 'Content-Type': 'application/json' };
}

/**
 * Build a rich error from a non-OK response.
 * Attaches:
 *   e.status  — HTTP status code (425, 502, 504 etc.)
 *   e.detail  — raw detail value (string OR structured object from backend)
 *   e.message — human-readable string always safe to display
 *
 * Backend structured errors look like:
 *   { "detail": { "code": "CHARGER_OFFLINE", "message": "...", "hint": "...", "can_queue": true } }
 * Plain errors look like:
 *   { "detail": "Flat not found" }
 */
function buildError(status, data) {
  const detail = data?.detail;
  const isObj = detail !== null && typeof detail === 'object';
  const message = isObj
    ? (detail.message || 'Request failed')
    : (typeof detail === 'string' ? detail : 'Request failed');

  const err = new Error(message);
  err.status = status;
  err.detail = detail;   // full detail — object or string
  return err;
}

/**
 * Generic authenticated JSON request.
 * Usage: api('GET', '/api/flats'), api('POST', '/api/flats', { name: 'A-101' })
 */
export async function api(method, path, body = null) {
  const opts = { method, headers: authHeaders() };
  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(`${API_BASE}${path}`, opts);
  if (res.status === 204) return null;

  const data = await res.json();
  if (!res.ok) throw buildError(res.status, data);
  return data;
}

/** Authenticated multipart upload */
export async function apiUpload(path, formData, method = 'POST') {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { Authorization: `Bearer ${getToken()}` },
    body: formData,
  });
  const data = await res.json();
  if (!res.ok) throw buildError(res.status, data);
  return data;
}

/** Authenticated file download (PDF / image) — saves it with the server's filename */
export async function apiDownload(path, fallbackName = 'download.pdf') {
  const res = await fetch(`${API_BASE}${path}`, { headers: { Authorization: `Bearer ${getToken()}` } });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw buildError(res.status, data);
  }
  const match = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') || '');
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement('a');
  a.href = url;
  a.download = match ? match[1] : fallbackName;
  a.click();
  URL.revokeObjectURL(url);
}

/** Unauthenticated request — used for login */
export async function apiPublic(method, path, body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(`${API_BASE}${path}`, opts);
  const data = await res.json();
  if (!res.ok) throw buildError(res.status, data);
  return data;
}