import styles from '../../styles/Analytics.module.css';

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

/** rows: [{ dow, hour, count }] */
export default function PeakHoursHeatmap({ rows }) {
  const matrix = {};
  let maxCount = 0;
  rows.forEach(r => {
    matrix[`${r.dow}_${r.hour}`] = r.count;
    if (r.count > maxCount) maxCount = r.count;
  });

  const hours = Array.from({ length: 24 }, (_, i) => i);

  return (
    <>
      <div className={styles.heatmapLabelRow}>
        <div className={styles.heatmapDayLabel}></div>
        {hours.map(h => (
          <div key={h} className={styles.heatmapHourLabel}>
            {h % 3 === 0 ? `${h}h` : ''}
          </div>
        ))}
      </div>
      <div>
        {DAYS.map((day, d) => (
          <div key={day} className={styles.heatmapGrid}>
            <div className={styles.heatmapDayLabel}>{day}</div>
            {hours.map(h => {
              const count = matrix[`${d}_${h}`] || 0;
              const alpha = maxCount > 0 ? (count / maxCount) * 0.85 + 0.05 : 0.05;
              return (
                <div
                  key={h}
                  className={styles.heatmapCell}
                  style={{ background: `rgba(79,134,247,${alpha.toFixed(2)})` }}
                  data-tip={`${count} sessions — ${day} ${h}:00`}
                />
              );
            })}
          </div>
        ))}
      </div>
    </>
  );
}
