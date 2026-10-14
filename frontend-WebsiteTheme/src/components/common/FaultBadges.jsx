import styles from '../../styles/FaultBadge.module.css';

const ACTIVE_FAULT_DESCRIPTIONS = {
  E01: 'Power loss during session — session unrecoverable',
  E04: 'Energy meter failure (PZEM gave invalid readings)',
  E05: 'Overvoltage — line voltage exceeded 270V',
  E06: 'Under-voltage — line voltage dropped below 160V',
  E07: 'Low current — at or below 0.2A for 30s (car full or unplugged)',
  E08: 'Overtemperature — charger reached ≥60°C, relay opened for safety',
  E09: 'Charger deactivated by admin',
  E10: 'Overcurrent — current exceeded 32A',
};

const COMPLETED_FAULT_DESCRIPTIONS = {
  E01: 'Power was cut while a session was active — session unrecoverable',
  E04: 'PZEM energy meter gave all-NaN reads for >120s during resume window',
  E05: 'Overvoltage — line voltage exceeded 270V during a charging session',
  E06: 'Undervoltage — line voltage dropped below 160V during a charging session',
  E07: 'Low current timeout — current stayed below 0.2A for 30s, EV likely disconnected',
  E08: 'Overtemperature — NTC sensor read ≥60°C, relay opened for safety',
  E09: 'Charger deactivated by admin — all new sessions are blocked',
  E10: 'Overcurrent — current exceeded 32A, session terminated for safety',
  ADM: 'Admin-issued DEACTIVATE command while a session was running',
};

/** For the Active Sessions page — badge driven by charger_status + fault_code */
export function LiveStatusBadge({ status, faultCode }) {
  const fc = faultCode ? String(faultCode) : null;
  const hasFault = fc && fc !== '200';
  if (hasFault) {
    const desc = ACTIVE_FAULT_DESCRIPTIONS[fc] || `Fault: ${fc}`;
    return (
      <div className={styles.faultWrap}>
        <span className="badge badge-red" style={{ cursor: 'pointer' }}>
          ⚠ Fault · {fc}
        </span>
        <div className={styles.faultTooltip}>{desc}</div>
      </div>
    );
  }
  const map = {
    available: ['badge-green', '🟢 Available'],
    charging: ['badge-blue', '⚡ Charging'],
    fault: ['badge-red', '🔴 Fault'],
    idle: ['badge-gray', '⚪ Idle'],
    offline: ['badge-gray', '⚫ Offline'],
    active: ['badge-blue', '⚡ Charging'],
  };
  const [cls, label] = map[status] || ['badge-gray', status || '—'];
  return <span className={`badge ${cls}`}>{label}</span>;
}

// ── Charger status (chargers.status, kept current from charger messages) ──

const CHARGER_STATUS = {
  charging:        ['badge-blue',  'Charging'],
  available:       ['badge-green', 'Available'],
  locked:          ['badge-amber', 'Locked'],
  fault:           ['badge-red',   'Fault'],
  offline:         ['badge-gray',  'Offline'],
  never_connected: ['badge-gray',  'Never connected'],
};

const BLOCKING_FAULTS = {
  E04: 'Energy meter not responding — no new sessions until it answers again',
  E08: 'Too hot (60°C or more) — no new sessions until it cools down',
  504: 'Energy meter stopped responding',
};

const LOCK_REASONS = {
  billing: 'Unpaid bill (Deactivate)',
  society: 'Whole society (Deactivate all)',
  tamper:  'Tamper detected',
};

const PENDING = {
  DEACTIVATE:     'Deactivate pending',
  DEACTIVATE_ALL: 'Deactivate pending',
  ACTIVE:         'Activate pending',
  ACTIVATE_ALL:   'Activate pending',
};

/**
 * Charger pages (super admin + society admin): status as last reported by the charger,
 * the fault or lock reason on hover, and a tag while a queued (de)activation awaits the charger.
 */
export function ChargerStatusBadge({ status, faultCode, lockReasons = [], pendingCmd, lastSeenAt }) {
  const [cls, label] = CHARGER_STATUS[status] || ['badge-gray', status || '—'];
  let detail = null;
  if (status === 'fault' && faultCode) detail = `${faultCode}: ${BLOCKING_FAULTS[faultCode] || 'Fault'}`;
  if (status === 'locked') detail = lockReasons.length ? lockReasons.map(r => LOCK_REASONS[r] || r).join(' · ') : 'Locked';
  if (status === 'offline' && lastSeenAt) {
    detail = `Last heard from ${new Date(lastSeenAt).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' })}`;
  }
  const short = status === 'fault' && faultCode ? ` · ${faultCode}`
    : status === 'locked' && lockReasons.length === 1 ? ` · ${lockReasons[0]}` : '';
  return (
    <span style={{ display: 'inline-flex', gap: 4, flexWrap: 'wrap', alignItems: 'center' }}>
      {detail ? (
        <span className={styles.faultWrap}>
          <span className={`badge ${cls}`} style={{ cursor: 'help' }}>{label}{short}</span>
          <span className={styles.faultTooltip}>{detail}</span>
        </span>
      ) : (
        <span className={`badge ${cls}`}>{label}</span>
      )}
      {pendingCmd && PENDING[pendingCmd] && (
        <span className="badge badge-amber" title="Queued — applies when the charger confirms">{PENDING[pendingCmd]}</span>
      )}
    </span>
  );
}

/** For the Completed Sessions page — badge driven by session status + fault_code */
export function CompletedStatusBadge({ status, faultCode }) {
  if (status === 'charging_ended_error') {
    const code = faultCode && faultCode !== 'null' ? String(faultCode) : null;
    const desc = code ? COMPLETED_FAULT_DESCRIPTIONS[code] || `Fault code: ${code}` : 'Fault code not recorded — session predates fault tracking';
    const label = code ? `⚠ Error · ${code}` : '⚠ Error';
    return (
      <div className={styles.faultWrap}>
        <span className="badge badge-red" style={{ cursor: 'pointer' }}>
          {label}
        </span>
        <div className={styles.faultTooltip}>{desc}</div>
      </div>
    );
  }
  if (status === 'charging_stopped_by_admin') {
    return <span className="badge badge-blue">Admin Stop</span>;
  }
  return <span className="badge badge-green">Completed</span>;
}
