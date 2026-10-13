import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { apiPublic } from '../api/client';
import ParticleBackground from '../components/common/ParticleBackground';
import styles from '../styles/Login.module.css';

export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get('token');

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  async function handleSubmit() {
    setError('');

    if (!password || !confirm) {
      setError('Please fill in both fields.');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }

    setSubmitting(true);
    try {
      await apiPublic('POST', '/api/auth/reset-password', { token, new_password: password });
      setDone(true);
      setTimeout(() => navigate('/login', { replace: true }), 2500);
    } catch (err) {
      // Backend returns a specific message for invalid/expired/reused tokens —
      // surface it as-is, it's already written to be user-facing.
      setError(err.message || 'Something went wrong. Please request a new reset link.');
    } finally {
      setSubmitting(false);
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter') handleSubmit();
  }

  if (!token) {
    return (
      <div className={styles.page}>
        <ParticleBackground />
        <div className={styles.card}>
          <div className={styles.logo}>
            <img src="/assets/brand-logo.svg" alt="Indram" />
            <p>Reset your password</p>
          </div>
          <div className={styles.error}>
            This reset link is missing its token. Please use the link from your email, or request
            a new one.
          </div>
          <Link to="/forgot-password" className={styles.btn} style={{ display: 'block', textAlign: 'center', textDecoration: 'none', boxSizing: 'border-box' }}>
            Request New Link
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <ParticleBackground />
      <div className={styles.card}>
        <div className={styles.logo}>
          <img src="/assets/brand-logo.svg" alt="Indram" />
          <p>Choose a new password</p>
        </div>

        {done ? (
          <div className={styles.success}>
            Password reset successfully. Redirecting you to sign in…
          </div>
        ) : (
          <>
            {error && (
              <div className={styles.error}>
                {error}
                {error.toLowerCase().includes('invalid') || error.toLowerCase().includes('expired') ? (
                  <>
                    {' '}
                    <Link to="/forgot-password" style={{ color: 'inherit', textDecoration: 'underline' }}>
                      Request a new link
                    </Link>
                  </>
                ) : null}
              </div>
            )}

            <div className={styles.formGroup}>
              <label htmlFor="password">New Password</label>
              <input
                id="password"
                type="password"
                placeholder="Min 8 characters"
                autoComplete="new-password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                onKeyDown={handleKeyDown}
                autoFocus
              />
            </div>

            <div className={styles.formGroup}>
              <label htmlFor="confirm">Confirm Password</label>
              <input
                id="confirm"
                type="password"
                placeholder="Re-enter new password"
                autoComplete="new-password"
                value={confirm}
                onChange={e => setConfirm(e.target.value)}
                onKeyDown={handleKeyDown}
              />
            </div>

            <button className={styles.btn} disabled={submitting} onClick={handleSubmit}>
              {submitting ? 'Resetting…' : 'Reset Password'}
            </button>

            <Link to="/login" className={styles.backLink}>
              ← Back to Sign In
            </Link>
          </>
        )}
      </div>
    </div>
  );
}
