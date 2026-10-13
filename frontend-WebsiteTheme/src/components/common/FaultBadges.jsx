import styles from '../../styles/FaultBadge.module.css';

const ACTIVE_FAULT_DESCRIPTIONS = {
  E01: 'Power loss during session — session unrecoverable',
  E04: 'Energy meter failure (PZEM gave invalid readings)',
  E05: 'Overvoltage — line voltage exceeded 270V',
  E06: 'Low current timeout — possible cable/connector issue',
  E07: 'Ground fault detected',
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
