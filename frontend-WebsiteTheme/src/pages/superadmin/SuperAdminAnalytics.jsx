import { useEffect, useState } from 'react';
import { api, API_BASE, authHeaders } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import { useChart, hexAlpha, CHART_COLORS, PALETTE } from '../../hooks/useChart';
import PeakHoursHeatmap from '../../components/common/PeakHoursHeatmap';
import styles from '../../styles/Analytics.module.css';

const { BLUE, GREEN, RED, AMBER, PURPLE, TEAL } = CHART_COLORS;

function todayMonth() {
  const t = new Date();
  return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}`;
}

function statusDotBadge(status) {
  const s = status;
  let dot = 'online';
  if (s === 'fault') dot = 'fault';
  else if (s === 'offline') dot = 'offline';
  else if (s === 'active' || s === 'charging') dot = 'active';
  return <span className={`${styles.statusDot} ${styles[dot]}`}></span>;
}

export default function SuperAdminAnalytics() {
  const { showToast } = useToast();
  const [month, setMonth] = useState(todayMonth());
  const [societies, setSocieties] = useState([]);
  const [societyId, setSocietyId] = useState('');
  const [loading, setLoading] = useState(false);

  const [overview, setOverview] = useState(null);
  const [comparison, setComparison] = useState([]);
  const [firmware, setFirmware] = useState([]);
  const [growth, setGrowth] = useState([]);

  const [daily, setDaily] = useState([]);
  const [peaks, setPeaks] = useState([]);
  const [health, setHealth] = useState([]);
  const [faults, setFaults] = useState(null);
  const [duration, setDuration] = useState([]);
  const [billing, setBilling] = useState([]);

  useEffect(() => {
    api('GET', '/api/societies')
      .then(setSocieties)
      .catch(() => {});
  }, []);

  async function loadAll() {
    setLoading(true);
    const sid = societyId || '';
    const sidParam = sid ? `&society_id=${sid}` : '';

    try {
      const [ov, cmp, fw, gr] = await Promise.allSettled([
        api('GET', `/api/analytics/admin/overview${sid ? '?society_id=' + sid : ''}`),
        api('GET', `/api/analytics/admin/society-comparison?month=${month}`),
        api('GET', `/api/analytics/admin/firmware-distribution${sid ? '?society_id=' + sid : ''}`),
        api('GET', `/api/analytics/admin/growth-trend?months=12${sidParam}`),
      ]);
      if (ov.status === 'fulfilled') setOverview(ov.value);
      if (cmp.status === 'fulfilled') setComparison(cmp.value);
      if (fw.status === 'fulfilled') setFirmware(fw.value);
      if (gr.status === 'fulfilled') setGrowth(gr.value);

      const names1 = ['overview', 'society-comparison', 'firmware-distribution', 'growth-trend'];
      [ov, cmp, fw, gr].forEach((r, i) => {
        if (r.status === 'rejected') showToast(`${names1[i]}: ${r.reason?.message || 'Error'}`, 'error');
      });

      if (sid) {
        const base = '/api/analytics/admin/society-detail';
        const q = `society_id=${sid}`;
        const [d, pk, hl, ft, du, bl] = await Promise.allSettled([
          api('GET', `${base}/daily-energy?${q}&month=${month}`),
          api('GET', `${base}/peak-hours?${q}&month=${month}`),
          api('GET', `${base}/charger-health?${q}`),
          api('GET', `${base}/fault-analysis?${q}`),
          api('GET', `${base}/session-duration?${q}&month=${month}`),
          api('GET', `${base}/billing-trend?${q}&months=6`),
        ]);
        if (d.status === 'fulfilled') setDaily(d.value);
        if (pk.status === 'fulfilled') setPeaks(pk.value);
        if (hl.status === 'fulfilled') setHealth(hl.value);
        if (ft.status === 'fulfilled') setFaults(ft.value);
        if (du.status === 'fulfilled') setDuration(du.value);
        if (bl.status === 'fulfilled') setBilling(bl.value);

        const names2 = ['daily-energy', 'peak-hours', 'charger-health', 'fault-analysis', 'session-duration', 'billing-trend'];
        [d, pk, hl, ft, du, bl].forEach((r, i) => {
          if (r.status === 'rejected') showToast(`${names2[i]}: ${r.reason?.message || 'Error'}`, 'error');
        });
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [month, societyId]);

  const platformOnly = !societyId;
  const selectedName = societyId ? societies.find(s => s.id === parseInt(societyId))?.name : null;

  // ── Comparison chart (top 8) ─────────────────────────────────────
  const top8 = comparison.slice(0, 8);
  const comparisonChartRef = useChart(
    top8.length
      ? {
          type: 'bar',
          data: {
            labels: top8.map(r => r.society_name),
            datasets: [
              {
                label: 'kWh',
                data: top8.map(r => +r.total_kwh.toFixed(2)),
                backgroundColor: top8.map((_, i) => hexAlpha(PALETTE[i % PALETTE.length], 0.75)),
                borderColor: top8.map((_, i) => PALETTE[i % PALETTE.length]),
                borderWidth: 1,
                borderRadius: 4,
              },
            ],
          },
          options: {
            indexAxis: 'y',
            responsive: true,
            plugins: { legend: { display: false } },
            scales: { x: { beginAtZero: true, title: { display: true, text: 'kWh' } } },
          },
        }
      : null
  );

  const firmwareChartRef = useChart(
    firmware.length
      ? {
          type: 'doughnut',
          data: {
            labels: firmware.map(r => r.fw_version || 'Unknown'),
            datasets: [{ data: firmware.map(r => r.count), backgroundColor: PALETTE.slice(0, firmware.length), borderWidth: 0 }],
          },
          options: {
            responsive: true,
            cutout: '60%',
            plugins: {
              legend: { position: 'right', labels: { boxWidth: 12 } },
              tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${ctx.raw} chargers (${firmware[ctx.dataIndex].pct}%)` } },
            },
          },
        }
      : null
  );

  const growthChartRef = useChart(
    growth.length
      ? {
          type: 'line',
          data: {
            labels: growth.map(r => r.month),
            datasets: [
              {
                label: 'kWh',
                data: growth.map(r => +r.kwh.toFixed(2)),
                borderColor: BLUE,
                backgroundColor: hexAlpha(BLUE, 0.1),
                borderWidth: 2.5,
                pointRadius: 4,
                tension: 0.35,
                fill: true,
                yAxisID: 'yKwh',
              },
              {
                label: 'Sessions',
                data: growth.map(r => r.sessions),
                borderColor: GREEN,
                backgroundColor: 'transparent',
                borderWidth: 2,
                borderDash: [5, 4],
                pointRadius: 3,
                tension: 0.35,
                yAxisID: 'ySessions',
              },
              {
                label: 'Active Societies',
                data: growth.map(r => r.active_societies),
                borderColor: AMBER,
                backgroundColor: 'transparent',
                borderWidth: 2,
                borderDash: [2, 3],
                pointRadius: 3,
                tension: 0.3,
                yAxisID: 'ySocieties',
              },
            ],
          },
          options: {
            responsive: true,
            interaction: { mode: 'index', intersect: false },
            plugins: { legend: { position: 'top' } },
            scales: {
              yKwh: { position: 'left', title: { display: true, text: 'kWh' } },
              ySessions: { position: 'right', title: { display: true, text: 'Sessions' }, grid: { drawOnChartArea: false } },
              ySocieties: { display: false },
            },
          },
        }
      : null
  );

  const dailyEnergyChartRef = useChart(
    daily.length
      ? {
          type: 'bar',
          data: {
            labels: daily.map(r => r.date.substring(8)),
            datasets: [
              {
                label: 'kWh',
                data: daily.map(r => +r.kwh.toFixed(3)),
                backgroundColor: hexAlpha(BLUE, 0.7),
                borderColor: BLUE,
                borderWidth: 1,
                borderRadius: 3,
                yAxisID: 'yKwh',
              },
              {
                label: 'Fault sessions',
                type: 'line',
                data: daily.map(r => r.fault_sessions),
                borderColor: RED,
                backgroundColor: 'transparent',
                borderWidth: 2,
                pointRadius: 4,
                pointBackgroundColor: RED,
                tension: 0.2,
                yAxisID: 'yFaults',
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'top' } },
            scales: {
              yKwh: { position: 'left', title: { display: true, text: 'kWh' }, beginAtZero: true },
              yFaults: { position: 'right', title: { display: true, text: 'Faults' }, beginAtZero: true, grid: { drawOnChartArea: false }, ticks: { stepSize: 1 } },
            },
          },
        }
      : null
  );

  const sessionDurationChartRef = useChart(
    duration.length
      ? {
          type: 'bar',
          data: {
            labels: duration.map(r => r.bucket_label),
            datasets: [
              {
                label: 'Sessions',
                data: duration.map(r => r.count),
                backgroundColor: [hexAlpha(BLUE, 0.75), hexAlpha(GREEN, 0.75), hexAlpha(TEAL, 0.75), hexAlpha(PURPLE, 0.75), hexAlpha(AMBER, 0.75)],
                borderRadius: 4,
                borderWidth: 0,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } },
          },
        }
      : null
  );

  const billingTrendChartRef = useChart(
    billing.length
      ? (() => {
          const sorted = [...billing].reverse();
          return {
            type: 'line',
            data: {
              labels: sorted.map(r => r.month),
              datasets: [
                {
                  label: 'Total Billing (₹)',
                  data: sorted.map(r => +r.total_bill_amount.toFixed(2)),
                  borderColor: AMBER,
                  backgroundColor: hexAlpha(AMBER, 0.08),
                  borderWidth: 2.5,
                  tension: 0.4,
                  fill: true,
                  pointRadius: 4,
                  yAxisID: 'yBilling',
                },
                {
                  label: 'Units (kWh)',
                  data: sorted.map(r => +r.total_units_consumed.toFixed(2)),
                  borderColor: GREEN,
                  backgroundColor: 'transparent',
                  borderWidth: 2,
                  borderDash: [5, 4],
                  tension: 0.4,
                  pointRadius: 3,
                  yAxisID: 'yKwh',
                },
              ],
            },
            options: {
              responsive: true,
              maintainAspectRatio: false,
              interaction: { mode: 'index', intersect: false },
              plugins: { legend: { position: 'top' } },
              scales: {
                yBilling: { position: 'left', title: { display: true, text: '₹ Billed' }, ticks: { callback: v => '₹' + (v >= 1000 ? (v / 1000).toFixed(0) + 'k' : v) } },
                yKwh: { position: 'right', title: { display: true, text: 'kWh' }, grid: { drawOnChartArea: false } },
              },
            },
          };
        })()
      : null
  );

  async function downloadReport(format) {
    const ext = format === 'excel' ? 'xlsx' : format;
    const sid = societyId ? parseInt(societyId) : null;
    const scope = sid ? `society-${sid}` : 'platform';
    const filename = `indram-${scope}-report-${month}.${ext}`;
    try {
      const body = { format, month, sections: ['energy', 'faults', 'billing', 'chargers'] };
      if (sid) body.society_id = sid;
      const res = await fetch(`${API_BASE}/api/analytics/admin/download-report`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Download failed');
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      showToast(`${format.toUpperCase()} report downloaded`);
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  const revenue = overview?.indram_revenue_month ?? 0;
  const revenueLabel = revenue >= 100000 ? `₹${(revenue / 100000).toFixed(1)}L` : revenue >= 1000 ? `₹${(revenue / 1000).toFixed(1)}K` : `₹${revenue.toFixed(0)}`;

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">📈 Platform Analytics</div>
          <div style={{ fontSize: 13, color: '#4a5568', marginTop: 2 }}>Super Admin — {selectedName || 'All Societies'}</div>
        </div>
        <button className="btn btn-secondary" onClick={loadAll}>
          🔄 Refresh
        </button>
      </div>

      <div className={styles.controlsBar}>
        <label>Month</label>
        <input type="month" value={month} onChange={e => setMonth(e.target.value)} />
        <div className={styles.sep}></div>
        <label>Society</label>
        <select value={societyId} onChange={e => setSocietyId(e.target.value)}>
          <option value="">All Societies</option>
          {societies.map(s => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
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

      {overview && (
        <div className={styles.kpiGrid}>
          <div className={`${styles.kpiCard} ${styles.blue}`}>
            <div className={styles.kpiLabel}>{societyId ? 'Society' : 'Total Societies'}</div>
            <div className={styles.kpiValue} style={{ fontSize: societyId && selectedName?.length > 12 ? 16 : undefined }}>
              {societyId ? selectedName : overview.total_societies}
            </div>
            <div className={styles.kpiSub}>{societyId ? 'selected' : 'registered'}</div>
          </div>
          <div className={`${styles.kpiCard} ${styles.green}`}>
            <div className={styles.kpiLabel}>Platform Energy</div>
            <div className={styles.kpiValue}>{overview.platform_kwh_month.toFixed(1)}</div>
            <div className={styles.kpiSub}>kWh this month</div>
          </div>
          <div className={`${styles.kpiCard} ${styles.teal}`}>
            <div className={styles.kpiLabel}>Platform Sessions</div>
            <div className={styles.kpiValue}>{overview.platform_sessions_month}</div>
            <div className={styles.kpiSub}>this month</div>
          </div>
          <div className={`${styles.kpiCard} ${styles.amber}`}>
            <div className={styles.kpiLabel}>Indram Revenue</div>
            <div className={styles.kpiValue}>{revenueLabel}</div>
            <div className={styles.kpiSub}>this month</div>
          </div>
          <div className={`${styles.kpiCard} ${styles.blue}`}>
            <div className={styles.kpiLabel}>Fleet Availability</div>
            <div className={styles.kpiValue}>{overview.fleet_availability_pct.toFixed(1)}%</div>
            <div className={styles.kpiSub}>
              {overview.chargers_online} of {overview.total_chargers} online
            </div>
          </div>
          <div className={`${styles.kpiCard} ${styles.red}`}>
            <div className={styles.kpiLabel}>Fault Rate</div>
            <div className={styles.kpiValue} style={{ color: overview.fault_rate_pct > 5 ? '#c53030' : '#1a202c' }}>
              {overview.fault_rate_pct.toFixed(1)}%
            </div>
            <div className={styles.kpiSub}>of sessions this month</div>
          </div>
          <div className={`${styles.kpiCard} ${styles.purple}`}>
            <div className={styles.kpiLabel}>Active Sessions</div>
            <div className={styles.kpiValue}>{overview.active_sessions}</div>
            <div className={styles.kpiSub}>right now</div>
          </div>
          <div className={`${styles.kpiCard} ${styles.teal}`}>
            <div className={styles.kpiLabel}>CO₂ Offset</div>
            <div className={styles.kpiValue}>{(overview.platform_kwh_month * 0.82).toFixed(0)}</div>
            <div className={styles.kpiSub}>kg saved this month</div>
          </div>
        </div>
      )}

      {platformOnly && (
        <div className={styles.chartGrid2}>
          <div className={styles.chartBox}>
            <div className={styles.chartBoxTitle}>Society Comparison — kWh (this month)</div>
            <canvas ref={comparisonChartRef}></canvas>
          </div>
          <div className={styles.chartBox}>
            <div className={styles.chartBoxTitle}>Firmware Distribution</div>
            <canvas ref={firmwareChartRef}></canvas>
          </div>
        </div>
      )}

      {overview?.chargers_outdated_fw > 0 && overview?.latest_fw_version && (
        <div style={{ background: '#fffbeb', border: '1.5px solid #fbd38d', borderRadius: 10, padding: '12px 18px', marginBottom: 22, fontSize: 13, color: '#f6ad55' }}>
          ⚠ <strong>
            {overview.chargers_outdated_fw} charger{overview.chargers_outdated_fw > 1 ? 's' : ''}
          </strong>{' '}
          not on latest firmware <strong>{overview.latest_fw_version}</strong>. {overview.chargers_on_latest_fw} up-to-date.
        </div>
      )}

      <div className={`${styles.chartBox} ${styles.analyticsSection}`}>
        <div className={styles.chartBoxTitle}>Platform Growth — Monthly kWh &amp; Sessions</div>
        <canvas ref={growthChartRef} style={{ maxHeight: 280 }}></canvas>
      </div>

      {societyId && (
        <div>
          <div className={`${styles.chartBox} ${styles.analyticsSection}`}>
            <div className={styles.chartBoxTitle}>Daily Energy — kWh &amp; Fault Sessions</div>
            <canvas ref={dailyEnergyChartRef} style={{ maxHeight: 260 }}></canvas>
          </div>

          <div className={`${styles.chartGridEqual} ${styles.analyticsSection}`}>
            <div className={styles.heatmapWrap} style={{ marginBottom: 0 }}>
              <div className={styles.heatmapTitle}>Peak Charging Hours — Sessions by Hour &amp; Day</div>
              <PeakHoursHeatmap rows={peaks} />
            </div>
            <div className={styles.chartBox} style={{ marginBottom: 0 }}>
              <div className={styles.chartBoxTitle}>Session Duration Distribution</div>
              <canvas ref={sessionDurationChartRef} style={{ maxHeight: 260 }}></canvas>
            </div>
          </div>

          <div className={`${styles.chartBox} ${styles.analyticsSection}`}>
            <div className={styles.chartBoxTitle}>Billing Trend — Last 6 Months</div>
            <canvas ref={billingTrendChartRef} style={{ maxHeight: 240 }}></canvas>
          </div>

          <div className={styles.analyticsSection}>
            <div className={styles.sectionTitle}>
              ⚡ Fault Analysis{' '}
              <span className="tag">{faults?.fault_summary?.length ? `${faults.fault_summary.length} fault codes` : '0 fault codes'}</span>
            </div>
            <div className={styles.faultBarWrap}>
              {!faults?.fault_summary?.length ? (
                <div style={{ color: '#4a5568', fontSize: 13, padding: '8px 0' }}>No faults recorded in this period 🎉</div>
              ) : (
                faults.fault_summary.map(f => {
                  const maxCount = Math.max(...faults.fault_summary.map(x => x.count));
                  return (
                    <div key={f.fault_code} className={styles.faultBarItem}>
                      <div className={styles.faultBarLabel}>{f.fault_code}</div>
                      <div className={styles.faultBarTrack}>
                        <div className={styles.faultBarFill} style={{ width: `${((f.count / maxCount) * 100).toFixed(1)}%` }}></div>
                      </div>
                      <div className={styles.faultBarCount}>{f.count}</div>
                      <div style={{ fontSize: 11, color: '#718096', marginLeft: 8 }}>
                        {f.avg_temp_c != null ? `${f.avg_temp_c.toFixed(1)}°C` : ''} {f.chargers_affected?.length ? '· ' + f.chargers_affected.join(', ') : ''}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
            {(faults?.top_offender_charger || faults?.avg_temp_at_fault) && (
              <div style={{ marginTop: 10, fontSize: 12, color: '#4a5568' }}>
                {faults.top_offender_charger && (
                  <>
                    <strong>Top offender:</strong> {faults.top_offender_charger}
                  </>
                )}
                {faults.avg_temp_at_fault && (
                  <>
                    &nbsp;·&nbsp;<strong>Avg temp at fault:</strong> {faults.avg_temp_at_fault.toFixed(1)}°C
                  </>
                )}
              </div>
            )}
          </div>

          <div className={styles.analyticsSection}>
            <div className={styles.sectionTitle}>🔌 Charger Health</div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Charger ID</th>
                    <th>Flat</th>
                    <th>Status</th>
                    <th>Voltage (V)</th>
                    <th>Current (A)</th>
                    <th>Temp (°C)</th>
                    <th>Fault Code</th>
                    <th>FW Version</th>
                    <th>Last Seen</th>
                  </tr>
                </thead>
                <tbody>
                  {health.length === 0 ? (
                    <tr className="empty-row">
                      <td colSpan={9}>Select a society to view charger health</td>
                    </tr>
                  ) : (
                    health.map(r => (
                      <tr key={r.charger_id}>
                        <td style={{ fontWeight: 600 }}>{r.charger_id}</td>
                        <td>{r.flat_number || '—'}</td>
                        <td>
                          {statusDotBadge(r.charger_status)}
                          {r.charger_status || '—'}
                        </td>
                        <td>{r.voltage != null ? r.voltage.toFixed(1) : '—'}</td>
                        <td>{r.current != null ? r.current.toFixed(2) : '—'}</td>
                        <td>{r.temperature_c != null ? r.temperature_c.toFixed(1) : '—'}</td>
                        <td>{r.fault_code && r.fault_code !== '0' ? <span style={{ color: '#c53030', fontWeight: 600 }}>{r.fault_code}</span> : '—'}</td>
                        <td>{r.fw_version || '—'}</td>
                        <td style={{ color: '#4a5568', fontSize: 12 }}>{r.last_seen_at ? new Date(r.last_seen_at).toLocaleString() : 'Never'}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      <div className={styles.analyticsSection}>
        <div className={styles.sectionTitle}>
          🏢 Society Leaderboard <span className="tag">{`${comparison.length} societies`}</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Society</th>
                <th>Chargers</th>
                <th>Flats</th>
                <th>Sessions</th>
                <th>kWh</th>
                <th>kWh / Charger</th>
                <th>Revenue (₹)</th>
                <th>Fault %</th>
                <th>Availability %</th>
              </tr>
            </thead>
            <tbody>
              {comparison.length === 0 ? (
                <tr className="empty-row">
                  <td colSpan={10}>No data for this month</td>
                </tr>
              ) : (
                comparison.map((r, i) => {
                  const faultColor = r.fault_rate_pct > 10 ? '#c53030' : r.fault_rate_pct > 5 ? '#f6ad55' : '#15803d';
                  const availColor = r.availability_pct < 70 ? '#c53030' : r.availability_pct < 90 ? '#f6ad55' : '#15803d';
                  return (
                    <tr key={r.society_name}>
                      <td style={{ color: '#718096', fontWeight: 700 }}>{i + 1}</td>
                      <td style={{ fontWeight: 600 }}>{r.society_name}</td>
                      <td>{r.charger_count}</td>
                      <td>{r.flat_count}</td>
                      <td>{r.sessions}</td>
                      <td>{r.total_kwh.toFixed(2)}</td>
                      <td>{r.kwh_per_charger.toFixed(2)}</td>
                      <td>₹{r.indram_revenue.toFixed(0)}</td>
                      <td style={{ color: faultColor, fontWeight: 600 }}>{r.fault_rate_pct.toFixed(1)}%</td>
                      <td style={{ color: availColor, fontWeight: 600 }}>{r.availability_pct.toFixed(1)}%</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
