import { useState } from 'react';
import { Link } from 'react-router-dom';
import { apiPublic } from '../api/client';
import ParticleBackground from '../components/common/ParticleBackground';
import styles from '../styles/Login.module.css';

export default function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  async function handleSubmit() {
    setError('');

    if (!email.trim()) {
      setError('Please enter your email.');
      return;
    }

    setSubmitting(true);
    try {
      // Backend always returns the same generic response whether or not
      // the email exists — we mirror that by showing the same confirmation
      // regardless of the result, so the UI never reveals which emails
      // are registered admins either.
      await apiPublic('POST', '/api/auth/forgot-password', { email: email.trim() });
      setSent(true);
    } catch (err) {
      setError(err.message || 'Cannot reach the server. Is the API running?');
    } finally {
      setSubmitting(false);
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter') handleSubmit();
  }

  return (
    <div className={styles.page}>
      <ParticleBackground />
      <div className={styles.card}>
        <div className={styles.logo}>
          <img src="/assets/brand-logo.svg" alt="Indram" />
          <p>Reset your password</p>
        </div>

        {sent ? (
          <>
            <div className={styles.success}>
              If that email is registered, a password reset link has been sent. Check your inbox
              (and spam folder) for an email from Indram.
            </div>
            <Link to="/login" className={styles.btn} style={{ display: 'block', textAlign: 'center', textDecoration: 'none', boxSizing: 'border-box' }}>
              Back to Sign In
            </Link>
          </>
        ) : (
          <>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 20, marginTop: -8 }}>
              Enter the email associated with your account and we'll send you a link to reset your
              password.
            </p>

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
                autoFocus
              />
            </div>

            <button className={styles.btn} disabled={submitting} onClick={handleSubmit}>
              {submitting ? 'Sending…' : 'Send Reset Link'}
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
