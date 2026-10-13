import { useEffect, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { API_BASE, getToken } from '../../api/client';
import styles from '../../styles/Dashboard.module.css';

export default function Dashboard() {
  const { fullName, role, isSuperAdmin } = useAuth();
  const token = getToken();

  const [apiStatus, setApiStatus] = useState('—');
  const [me, setMe] = useState(null);
  const [meError, setMeError] = useState(null);
  const [meResponse, setMeResponse] = useState(null);
  const [tokenPayload, setTokenPayload] = useState(null);
  const [tokenError, setTokenError] = useState(false);

  async function testMe() {
    setMeError(null);
    try {
      const res = await fetch(`${API_BASE}/api/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!res.ok) {
        setMeError(data.detail || 'Request failed');
        return;
      }
      setMe(data);
      setMeResponse(JSON.stringify(data, null, 2));
    } catch {
      setMeError('Cannot reach API');
    }
  }

  function decodeToken() {
    try {
      const parts = token.split('.');
      const payload = JSON.parse(atob(parts[1]));
      payload._expires = new Date(payload.exp * 1000).toLocaleString();
      setTokenPayload(JSON.stringify(payload, null, 2));
      setTokenError(false);
    } catch {
      setTokenPayload('Failed to decode token');
      setTokenError(true);
    }
  }

  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then(r => r.json())
      .then(d => setApiStatus(d.status === 'ok' ? '🟢 Online' : '🔴 Error'))
      .catch(() => setApiStatus('🔴 Offline'));

    testMe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      <div className="page-title">Dashboard</div>

      <div className={styles.cards}>
        <div className={styles.card}>
          <div className={styles.cardLabel}>Logged in as</div>
          <div className={styles.cardValue} style={{ fontSize: 20 }}>{fullName}</div>
          <div className={styles.cardSub}>{me?.email || '—'}</div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardLabel}>Role</div>
          <div className={styles.cardValue} style={{ fontSize: 20 }}>
            {isSuperAdmin ? 'Super Admin' : 'Society Admin'}
          </div>
          <div className={styles.cardSub}>Access level</div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardLabel}>API Status</div>
          <div className={styles.cardValue} style={{ fontSize: 20 }}>{apiStatus}</div>
          <div className={styles.cardSub}>Backend connection</div>
        </div>
      </div>

      <div className={styles.panel}>
        <h2>🔐 Auth Test — GET /api/auth/me</h2>
        <div>
          {meError ? (
            <div className={styles.infoRow}>
              <span className={styles.infoLabel} style={{ color: '#c53030' }}>Error: {meError}</span>
            </div>
          ) : me ? (
            <>
              <div className={styles.infoRow}><span className={styles.infoLabel}>ID</span><span className={styles.infoValue}>{me.id}</span></div>
              <div className={styles.infoRow}><span className={styles.infoLabel}>Email</span><span className={styles.infoValue}>{me.email}</span></div>
              <div className={styles.infoRow}><span className={styles.infoLabel}>Full Name</span><span className={styles.infoValue}>{me.full_name || '—'}</span></div>
              <div className={styles.infoRow}>
                <span className={styles.infoLabel}>Role</span>
                <span className={styles.infoValue}>
                  <span className={`${styles.tag} ${me.role === 'super_admin' ? styles.tagBlue : styles.tagGreen}`}>{me.role}</span>
                </span>
              </div>
              <div className={styles.infoRow}><span className={styles.infoLabel}>Active</span><span className={styles.infoValue}>{me.is_active ? '✅ Yes' : '❌ No'}</span></div>
              <div className={styles.infoRow}><span className={styles.infoLabel}>Created</span><span className={styles.infoValue}>{new Date(me.created_at).toLocaleString()}</span></div>
            </>
          ) : (
            <div className={styles.infoRow}><span className={styles.infoLabel}>Loading…</span></div>
          )}
        </div>
        <br />
        <button className={styles.testBtn} onClick={testMe}>Re-fetch /api/auth/me</button>
        {meResponse && <div className={styles.responseBox} style={{ display: 'block' }}>{meResponse}</div>}
      </div>

      <div className={styles.panel}>
        <h2>🪙 Current JWT Token</h2>
        <div className={styles.infoRow}>
          <span className={styles.infoLabel}>Token (truncated)</span>
          <span className={styles.infoValue}>{token ? `${token.substring(0, 40)}…` : '—'}</span>
        </div>
        <div className={styles.infoRow}>
          <span className={styles.infoLabel}>Stored in</span>
          <span className={styles.infoValue}>localStorage</span>
        </div>
        <br />
        <button className={styles.testBtn} onClick={decodeToken}>Decode Token Payload</button>
        {tokenPayload && (
          <div className={styles.responseBox} style={{ display: 'block', color: tokenError ? '#c53030' : undefined }}>
            {tokenPayload}
          </div>
        )}
      </div>
    </div>
  );
}
