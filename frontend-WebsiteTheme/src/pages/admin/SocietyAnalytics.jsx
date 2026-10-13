import { useEffect, useState } from 'react';
import { api, API_BASE, authHeaders } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import { useChart, hexAlpha, CHART_COLORS } from '../../hooks/useChart';
import PeakHoursHeatmap from '../../components/common/PeakHoursHeatmap';
import styles from '../../styles/Analytics.module.css';
import { toNum } from '../../utils/format';

const { BLUE, GREEN, RED, AMBER, PURPLE, TEAL } = CHART_COLORS;

function todayMonth() {
  const t = new Date();
  return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}`;
}

function statusBadgeSpan(status) {
  if (!status) return <span className="badge badge-gray">Unknown</span>;
  const s = status.toLowerCase();
  const map = {
    offline: ['offline', 'badge-gray', 'Offline'],
    fault: ['fault', 'badge-red', 'Fault'],
    available: ['online', 'badge-green', 'Available'],
    charging: ['active', 'badge-blue', 'Charging'],
  };
  const [dot, cls, label] = map[s] || ['online', 'badge-gray', status];
  return (
    <>
      <span className={`${styles.statusDot} ${styles[dot]}`}></span>
      <span className={`badge ${cls}`}>{label}</span>
    </>
  );
}

export default function SocietyAnalytics() {
  const { showToast } = useToast();
  const [month, setMonth] = useState(todayMonth());
  const [societyName, setSocietyName] = useState('');
  const [loading, setLoading] = useState(false);

  const [energyRows, setEnergyRows] = useState([]);
  const [peakRows, setPeakRows] = useState([]);
  const [health, setHealth] = useState([]);
  const [faults, setFaults] = useState(null);
  const [durationRows, setDurationRows] = useState([]);
  const [rfidRows, setRfidRows] = useState([]);
  const [billingRows, setBillingRows] = useState([]);

  async function loadAll() {
    setLoading(true);
    try {
      api('GET', '/api/usage/society').then(s => setSocietyName(s.name)).catch(() => {});

      const [energy, peaks, healthR, faultsR, duration, rfid, billing] = await Promise.allSettled([
        api('GET', `/api/analytics/society/daily-energy?month=${month}`),
        api('GET', `/api/analytics/society/peak-hours?month=${month}`),
        api('GET', `/api/analytics/society/charger-health`),
        api('GET', `/api/analytics/society/fault-analysis?months=3`),
        api('GET', `/api/analytics/society/session-duration?month=${month}`),
        api('GET', `/api/analytics/society/rfid-usage?month=${month}`),
        api('GET', `/api/analytics/society/billing-trend?months=6`),
      ]);

      if (energy.status === 'fulfilled') setEnergyRows(energy.value);
      if (peaks.status === 'fulfilled') setPeakRows(peaks.value);
      if (healthR.status === 'fulfilled') setHealth(healthR.value);
      if (faultsR.status === 'fulfilled') setFaults(faultsR.value);
      if (duration.status === 'fulfilled') setDurationRows(duration.value);
      if (rfid.status === 'fulfilled') setRfidRows(rfid.value);
      if (billing.status === 'fulfilled') setBillingRows(billing.value);

      const names = ['daily-energy', 'peak-hours', 'charger-health', 'fault-analysis', 'session-duration', 'rfid-usage', 'billing-trend'];
      [energy, peaks, healthR, faultsR, duration, rfid, billing].forEach((r, i) => {
        if (r.status === 'rejected') showToast(`${names[i]}: ${r.reason?.message || 'Error'}`, 'error');
      });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [month]);

  // ── KPI derivations ──────────────────────────────────────────────
  const totalKwh = energyRows.reduce((s, r) => s + r.kwh, 0);
  const totalSessions = energyRows.reduce((s, r) => s + r.total_sessions, 0);
  const totalFaults = energyRows.reduce((s, r) => s + r.fault_sessions, 0);
  const faultPct = totalSessions > 0 ? ((totalFaults / totalSessions) * 100).toFixed(1) : '0.0';
  const co2 = (totalKwh * 0.82).toFixed(1);
  const good = totalSessions - totalFaults;

  const midpoints = { '0–30 min': 15, '30–60 min': 45, '1–2 hrs': 90, '2–4 hrs': 180, '4+ hrs': 300 };
  const durTotal = durationRows.reduce((s, r) => s + r.count, 0);
  const avgDur =
    durTotal > 0
      ? Math.round(durationRows.reduce((s, r) => s + (midpoints[r.bucket_label] || 0) * r.count, 0) / durTotal)
      : 0;

  // ── Charts ────────────────────────────────────────────────────────
  const energyChartRef = useChart(
    energyRows.length
      ? {
          type: 'bar',
          data: {
            labels: energyRows.map(r => r.date.slice(5)),
            datasets: [
              {
                label: 'kWh',
                data: energyRows.map(r => +r.kwh.toFixed(3)),
                backgroundColor: hexAlpha(BLUE, 0.75),
                borderColor: BLUE,
                borderWidth: 1,
                borderRadius: 4,
                yAxisID: 'yKwh',
                order: 2,
              },
              {
                label: 'Fault Sessions',
                data: energyRows.map(r => r.fault_sessions),
                type: 'line',
                borderColor: RED,
                backgroundColor: hexAlpha(RED, 0.15),
                borderWidth: 2,
                pointRadius: 3,
                tension: 0.3,
                yAxisID: 'yFault',
                order: 1,
              },
            ],
          },
          options: {
            responsive: true,
            interaction: { mode: 'index', intersect: false },
            plugins: { legend: { position: 'top' } },
            scales: {
              yKwh: { position: 'left', title: { display: true, text: 'kWh' } },
              yFault: { position: 'right', title: { display: true, text: 'Faults' }, grid: { drawOnChartArea: false } },
            },
          },
        }
      : null
  );

  const statusChartRef = useChart(
    totalSessions >= 0 && (good || totalFaults)
      ? {
          type: 'doughnut',
          data: {
            labels: ['Completed OK', 'Fault / Error'],
            datasets: [{ data: [good, totalFaults], backgroundColor: [GREEN, RED], borderWidth: 0 }],
          },
          options: {
            responsive: true,
            cutout: '65%',
            plugins: { legend: { position: 'bottom' }, tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${ctx.raw} sessions` } } },
          },
        }
      : null
  );

  const durationChartRef = useChart(
    durationRows.length
      ? {
          type: 'bar',
          data: {
            labels: durationRows.map(r => r.bucket_label),
            datasets: [
              {
                label: 'Sessions',
                data: durationRows.map(r => r.count),
                backgroundColor: [hexAlpha(BLUE, 0.7), hexAlpha(GREEN, 0.7), hexAlpha(TEAL, 0.7), hexAlpha(PURPLE, 0.7), hexAlpha(AMBER, 0.7)],
                borderRadius: 4,
                borderWidth: 0,
              },
            ],
          },
          options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
          },
        }
      : null
  );

  const billingChartRef = useChart(
    billingRows.length
      ? (() => {
          const sorted = [...billingRows].reverse();
          return {
            type: 'line',
            data: {
              labels: sorted.map(r => r.month),
              datasets: [
                {
                  label: 'Total Bill (₹)',
                  data: sorted.map(r => +toNum(r.total_bill_amount).toFixed(2)),
                  borderColor: BLUE,
                  backgroundColor: hexAlpha(BLUE, 0.1),
                  borderWidth: 2,
                  pointRadius: 4,
                  tension: 0.3,
                  fill: true,
                  yAxisID: 'yBill',
                },
                {
                  label: 'Indram Revenue (₹)',
                  data: sorted.map(r => +toNum(r.indram_charges_total).toFixed(2)),
                  borderColor: GREEN,
                  backgroundColor: 'transparent',
                  borderWidth: 2,
                  borderDash: [4, 4],
                  pointRadius: 3,
                  tension: 0.3,
                  yAxisID: 'yIndram',
                },
              ],
            },
            options: {
              responsive: true,
              interaction: { mode: 'index', intersect: false },
              plugins: { legend: { position: 'top' } },
              scales: {
                yBill: { position: 'left', title: { display: true, text: 'Total Bill (₹)' }, ticks: { callback: v => '₹' + v.toLocaleString('en-IN') } },
                yIndram: {
                  position: 'right',
                  title: { display: true, text: 'Indram Revenue (₹)' },
                  ticks: { callback: v => '₹' + v.toLocaleString('en-IN') },
                  grid: { drawOnChartArea: false },
                },
              },
            },
          };
        })()
      : null
  );

  async function downloadReport(format) {
    const ext = format === 'excel' ? 'xlsx' : format;
    try {
      const res = await fetch(`${API_BASE}/api/analytics/society/download-report`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ format, month, sections: ['energy', 'faults', 'billing', 'chargers'] }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Download failed');
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `indram-report-${month}.${ext}`;
      a.click();
      URL.revokeObjectURL(url);
      showToast(`${format.toUpperCase()} report downloaded`);
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  const onlineCount = health.filter(r => r.charger_status !== 'offline' && r.charger_status !== null).length;
  const maxRfidKwh = Math.max(0, ...rfidRows.map(r => r.total_kwh));

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">📈 Analytics</div>
          <div style={{ fontSize: 13, color: '#4a5568', marginTop: 2 }}>{societyName}</div>
        </div>
        <button className="btn btn-secondary" onClick={loadAll}>
          🔄 Refresh
        </button>
      </div>

      <div className={styles.controlsBar}>
        <label>Month</label>
        <input type="month" value={month} onChange={e => setMonth(e.target.value)} />
        <div className={styles.sep}></div>
        {loading && <span style={{ fontSize: 13, color: '#718096' }}>Loading…</span>}
      </div>

      <div className={styles.downloadBar}>
        <span>⬇ Download Report</span>
        <button className={styles.btnDownload} onClick={() => downloadReport('csv')}>
          📄 CSV
        </button>
        <button className={styles.btnDownload} onClick={() => downloadReport('excel')}>
          📊 Excel
        </button>
        <button className={styles.btnDownload} onClick={() => downloadReport('pdf')}>
          📑 PDF
        </button>
      </div>

      <div className={styles.kpiGrid}>
        <div className={`${styles.kpiCard} ${styles.blue}`}>
          <div className={styles.kpiLabel}>Total Sessions</div>
          <div className={styles.kpiValue}>{totalSessions}</div>
          <div className={styles.kpiSub}>this month</div>
        </div>
        <div className={`${styles.kpiCard} ${styles.green}`}>
          <div className={styles.kpiLabel}>Energy Consumed</div>
          <div className={styles.kpiValue}>{totalKwh.toFixed(2)}</div>
          <div className={styles.kpiSub}>kWh this month</div>
        </div>
        <div className={`${styles.kpiCard} ${styles.red}`}>
          <div className={styles.kpiLabel}>Fault Sessions</div>
          <div className={styles.kpiValue} style={{ color: totalFaults > 0 ? '#c53030' : '#1a202c' }}>
            {totalFaults}
          </div>
          <div className={styles.kpiSub}>{faultPct}% of total</div>
        </div>
        <div className={`${styles.kpiCard} ${styles.amber}`}>
          <div className={styles.kpiLabel}>Avg Session</div>
          <div className={styles.kpiValue}>{avgDur}</div>
          <div className={styles.kpiSub}>minutes duration</div>
        </div>
        <div className={`${styles.kpiCard} ${styles.teal}`}>
          <div className={styles.kpiLabel}>CO₂ Offset</div>
          <div className={styles.kpiValue}>{co2}</div>
          <div className={styles.kpiSub}>kg CO₂ saved</div>
        </div>
      </div>

      <div className={styles.chartGrid2}>
        <div className={styles.chartBox}>
          <div className={styles.chartBoxTitle}>Daily Energy (kWh)</div>
          <canvas ref={energyChartRef}></canvas>
        </div>
        <div className={styles.chartBox}>
          <div className={styles.chartBoxTitle}>Session Breakdown</div>
          <canvas ref={statusChartRef}></canvas>
        </div>
      </div>

      <div className={styles.heatmapWrap}>
        <div className={styles.heatmapTitle}>⏱ Peak Hours — Sessions by Day &amp; Hour</div>
        <PeakHoursHeatmap rows={peakRows} />
      </div>

      <div className={styles.chartGridEqual}>
        <div className={styles.chartBox}>
          <div className={styles.chartBoxTitle}>Session Duration Distribution</div>
          <canvas ref={durationChartRef}></canvas>
        </div>
        <div className={styles.chartBox}>
          <div className={styles.chartBoxTitle}>Billing Trend (₹)</div>
          <canvas ref={billingChartRef}></canvas>
        </div>
      </div>

      <div className={styles.analyticsSection}>
        <div className={styles.sectionTitle}>
          ⚡ Charger Health <span className="tag">{`${onlineCount}/${health.length} online`}</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Charger ID</th>
                <th>Flat</th>
                <th>Status</th>
                <th>Voltage</th>
                <th>Current</th>
                <th>Temp</th>
                <th>Fault Code</th>
                <th>Last Seen</th>
                <th>FW</th>
              </tr>
            </thead>
            <tbody>
              {health.length === 0 ? (
                <tr className="empty-row">
                  <td colSpan={9}>No chargers found</td>
                </tr>
              ) : (
                health.map(r => (
                  <tr key={r.charger_id}>
                    <td>
                      <code style={{ fontSize: 12 }}>{r.charger_id}</code>
                    </td>
                    <td>{r.flat_number || '—'}</td>
                    <td>{statusBadgeSpan(r.charger_status)}</td>
                    <td>{r.voltage != null ? `${r.voltage.toFixed(1)} V` : '—'}</td>
                    <td>{r.current != null ? `${r.current.toFixed(1)} A` : '—'}</td>
                    <td>{r.temperature_c != null ? `${r.temperature_c.toFixed(1)} °C` : '—'}</td>
                    <td>{r.fault_code && r.fault_code !== '0' ? <span className="badge badge-red">{r.fault_code}</span> : '—'}</td>
                    <td>{r.last_seen_at ? new Date(r.last_seen_at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) : '—'}</td>
                    <td style={{ fontSize: 11, color: '#4a5568' }}>{r.fw_version || '—'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className={styles.chartGridEqual}>
        <div className={styles.chartBox}>
          <div className={styles.chartBoxTitle}>Fault Analysis (last 3 months)</div>
          <div className={styles.faultBarWrap}>
            {!faults?.fault_summary?.length ? (
              <div style={{ color: '#718096', fontSize: 13 }}>No faults in the last 3 months ✅</div>
            ) : (
              <>
                {faults.fault_summary.map(f => {
                  const maxCount = Math.max(...faults.fault_summary.map(x => x.count));
                  const pct = maxCount > 0 ? ((f.count / maxCount) * 100).toFixed(0) : 0;
                  return (
                    <div key={f.fault_code}>
                      <div className={styles.faultBarItem}>
                        <div className={styles.faultBarLabel}>{f.fault_code}</div>
                        <div className={styles.faultBarTrack}>
                          <div className={styles.faultBarFill} style={{ width: `${pct}%` }}></div>
                        </div>
                        <div className={styles.faultBarCount}>{f.count}</div>
                      </div>
                      {f.avg_temp_c != null && (
                        <div style={{ fontSize: 11, color: '#718096', marginLeft: 86, marginTop: -6 }}>
                          avg temp: {f.avg_temp_c.toFixed(1)}°C
                        </div>
                      )}
                    </div>
                  );
                })}
                {faults.top_offender_charger && (
                  <div style={{ marginTop: 14, padding: 10, background: 'rgba(197,48,48,0.08)', borderRadius: 8, fontSize: 12, color: '#c53030' }}>
                    ⚠ Top offender: <strong>{faults.top_offender_charger}</strong>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
        <div className={styles.chartBox}>
          <div className={styles.chartBoxTitle}>RFID Card Usage</div>
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr>
                  <th>RFID UID</th>
                  <th>Flat</th>
                  <th>Sessions</th>
                  <th>kWh</th>
                </tr>
              </thead>
              <tbody>
                {rfidRows.length === 0 ? (
                  <tr className="empty-row">
                    <td colSpan={4}>No RFID sessions this month</td>
                  </tr>
                ) : (
                  rfidRows.map(r => (
                    <tr key={r.rfid_uid}>
                      <td>
                        <code style={{ fontSize: 11 }}>{r.rfid_uid}</code>
                      </td>
                      <td>{r.flat_number || <span style={{ color: '#718096' }}>Unassigned</span>}</td>
                      <td>{r.sessions}</td>
                      <td>
                        {r.total_kwh.toFixed(2)}
                        <div className={styles.rfidKwhBar}>
                          <div className={styles.rfidKwhFill} style={{ width: `${maxRfidKwh > 0 ? (r.total_kwh / maxRfidKwh) * 100 : 0}%` }}></div>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
