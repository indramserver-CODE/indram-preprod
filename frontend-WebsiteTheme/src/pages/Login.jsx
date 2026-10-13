import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import ParticleBackground from '../components/common/ParticleBackground';
import styles from '../styles/Login.module.css';

export default function Login() {
  const { login, isAuthenticated, role } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail]           = useState('');
  const [password, setPassword]     = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError]           = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (isAuthenticated) {
      navigate(role === 'society_admin' ? '/admin/dashboard' : '/super-admin/dashboard', { replace: true });
    }
  }, [isAuthenticated, role, navigate]);

  async function handleLogin() {
    setError('');
    if (!email.trim() || !password) {
      setError('Please enter your email and password.');
      return;
    }
    setSubmitting(true);
    try {
      const data = await login(email.trim(), password);
      navigate(data.role === 'society_admin' ? '/admin/dashboard' : '/super-admin/dashboard', { replace: true });
    } catch (err) {
      setError(err.message || 'Cannot reach the server. Is the API running?');
    } finally {
      setSubmitting(false);
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter') handleLogin();
  }

  return (
    <div className={styles.page}>
      <ParticleBackground />
      <div className={styles.card}>

        {/* Logo block */}
        <div className={styles.logo}>
          <img src="/assets/brand-logo.svg" alt="Indram" />
          <p className={styles.productName}>Charger Management Software</p>
          <p className={styles.signInText}>Sign in to your account</p>
        </div>

        {error && <div className={styles.error}>{error}</div>}

        <div className={styles.formGroup}>
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            placeholder="admin@example.com"
            autoComplete="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            onKeyDown={handleKeyDown}
          />
        </div>

        <div className={styles.formGroup}>
          <label htmlFor="password">Password</label>
          <div className={styles.passwordWrap}>
            <input
              id="password"
              type={showPassword ? 'text' : 'password'}
              placeholder="••••••••"
              autoComplete="current-password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              onKeyDown={handleKeyDown}
            />
            <button
              type="button"
              className={styles.eyeBtn}
              onClick={() => setShowPassword(v => !v)}
              tabIndex={-1}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
            >
              {showPassword ? <EyeOff /> : <EyeOn />}
            </button>
          </div>
        </div>

        <Link to="/forgot-password" className={styles.forgotLink}>
          Forgot password?
        </Link>

        <button className={styles.btn} disabled={submitting} onClick={handleLogin}>
          {submitting ? 'Signing in…' : 'Sign In'}
        </button>
      </div>
    </div>
  );
}

/* ── Inline SVG eye icons — no extra dependency needed ─────────────────── */

function EyeOn() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function EyeOff() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
      <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  );
}