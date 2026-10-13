import { useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';

export const IDLE_TIMEOUT_MS = 30 * 60 * 1000; // 30 minutes of inactivity
const ACTIVITY_KEY = 'last_activity';
const EVENTS = ['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart', 'click'];

/**
 * Logs the user out after IDLE_TIMEOUT_MS without activity.
 * Last-activity time is shared via localStorage so activity in any tab counts,
 * and it is re-checked when the tab becomes visible again (timers are throttled
 * in background tabs / while the device sleeps).
 */
export default function useIdleLogout() {
  const { logout } = useAuth();
  const { showToast } = useToast();

  useEffect(() => {
    let timer;
    let lastWrite = 0;

    const getLast = () => Number(localStorage.getItem(ACTIVITY_KEY)) || Date.now();

    const expire = () => {
      showToast('You were logged out due to inactivity', 'error');
      logout();
    };

    const schedule = () => {
      clearTimeout(timer);
      const remaining = IDLE_TIMEOUT_MS - (Date.now() - getLast());
      if (remaining <= 0) return expire();
      timer = setTimeout(schedule, remaining);
    };

    const onActivity = () => {
      const now = Date.now();
      if (now - lastWrite < 5000) return; // throttle
      lastWrite = now;
      localStorage.setItem(ACTIVITY_KEY, String(now));
      schedule();
    };

    const onVisible = () => { if (document.visibilityState === 'visible') schedule(); };

    localStorage.setItem(ACTIVITY_KEY, String(Date.now()));
    schedule();
    EVENTS.forEach(e => window.addEventListener(e, onActivity, { passive: true }));
    document.addEventListener('visibilitychange', onVisible);

    return () => {
      clearTimeout(timer);
      EVENTS.forEach(e => window.removeEventListener(e, onActivity));
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [logout, showToast]);
}
