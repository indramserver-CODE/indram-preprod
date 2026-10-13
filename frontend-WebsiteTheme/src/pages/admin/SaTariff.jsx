import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import { fmtMoney, fmtPeriod } from '../../utils/format';

const byTillDesc = (a, b) => (a.period_till < b.period_till ? 1 : a.period_till > b.period_till ? -1 : 0);

export default function SaTariff() {
  const { showToast } = useToast();
  const [societyName, setSocietyName] = useState('');
  const [meters, setMeters]           = useState([]);
  const [bills, setBills]             = useState([]);
  const [loading, setLoading]         = useState(true);
  const [meterFilter, setMeterFilter] = useState('');

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const [societyData, meterData, billData] = await Promise.all([
          api('GET', '/api/usage/society').catch(() => ({})),
          api('GET', '/api/sa/meters').catch(() => []),
          api('GET', '/api/billing?status=sent').catch(() => []),   // drafts / cancelled bills aren't rates
        ]);
        setSocietyName(societyData?.name || '');
        setMeters(meterData);
        setBills(billData);
        if (meterData.length === 1) setMeterFilter(String(meterData[0].id));
      } catch (e) {
        showToast(e.message, 'error');
      } finally {
        setLoading(false);
      }
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Build meter_id → meter map
  const meterMap = Object.fromEntries(meters.map(m => [m.id, m]));

  // Filter bills by selected meter
  const filteredBills = meterFilter
    ? bills.filter(b => String(b.meter_id) === meterFilter)
    : bills;

  // Most recent bill per meter (for "current rates" summary cards)
  const latestPerMeter = meters.map(m => {
    const meterBills = bills
      .filter(b => b.meter_id === m.id)
      .sort(byTillDesc);
    return { meter: m, latest: meterBills[0] || null };
  });

  return (
    <div>
      {/* Page header */}
      <div className="page-header">
        <div>
          <div className="page-title">Tariff & Rate History</div>
          <div style={{ fontSize: 13, color: '#4a5568', marginTop: 2 }}>{societyName}</div>
        </div>
      </div>

      {/* Info banner explaining how tariff works */}
      <div style={{
        background: 'rgba(0, 255, 65, 0.06)',
        border: '1px solid rgba(0, 255, 65, 0.2)',
        borderRadius: 12, padding: '16px 20px', marginBottom: 24,
        display: 'flex', alignItems: 'flex-start', gap: 14,
      }}>
        <span style={{ fontSize: 22, flexShrink: 0 }}>ℹ️</span>
        <div>
          <div style={{ fontWeight: 700, fontSize: 14, color: '#1a202c', marginBottom: 4 }}>
            How tariff rates work in INDRAM
          </div>
          <div style={{ fontSize: 13, color: '#4a5568', lineHeight: 1.7 }}>
            There is no fixed monthly tariff. Instead, the effective rate is calculated
            each billing cycle as <strong>Effective Rate = Total MSEB Bill ÷ Total Units Consumed</strong> for that meter.
            The tariff you enter during bill generation is used only for tax bifurcation display on flat bills.
            The table below shows all historical rates used across your billing cycles.
          </div>
        </div>
      </div>

      {/* Current rates — one card per meter */}
      {!loading && latestPerMeter.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 13, fontWeight: 700, textTransform: 'uppercase', color: '#718096', marginBottom: 12 }}>
            Most Recent Effective Rates
          </div>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
            gap: 14,
          }}>
            {latestPerMeter.map(({ meter, latest }) => (
              <div key={meter.id} style={{
                background: '#ffffff',
                border: '1px solid rgba(0,0,0,0.08)',
                borderRadius: 12,
                padding: '18px 20px',
                boxShadow: '0 2px 8px rgba(0,0,0,0.05)',
              }}>
                <div style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', color: '#718096', marginBottom: 6 }}>
                  {meter.label}
                </div>
                <div style={{
                  fontFamily: 'monospace', fontSize: 11, color: '#a0aec0',
                  marginBottom: 10,
                }}>
                  {meter.meter_number}
                </div>
                {latest ? (
                  <>
                    <div style={{ fontSize: 26, fontWeight: 700, color: '#1a202c' }}>
                      {fmtMoney(latest.effective_unit_rate, 4)}
                      <span style={{ fontSize: 13, color: '#718096', fontWeight: 400 }}>/kWh</span>
                    </div>
                    <div style={{ fontSize: 12, color: '#4a5568', marginTop: 6 }}>
                      {fmtPeriod(latest.period_from, latest.period_till)}
                    </div>
                    <div style={{ fontSize: 12, color: '#718096', marginTop: 2 }}>
                      Base tariff: {fmtMoney(latest.effective_unit_rate, 4)}/kWh
                    </div>
                  </>
                ) : (
                  <div style={{ fontSize: 14, color: '#a0aec0' }}>No bills generated yet</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Meter filter */}
      {meters.length > 1 && (
        <div className="selector-bar" style={{ marginBottom: 16 }}>
          <label style={{ margin: 0, whiteSpace: 'nowrap' }}>⚡ Filter by Meter:</label>
          <select
            value={meterFilter}
            onChange={e => setMeterFilter(e.target.value)}
            style={{ maxWidth: 320 }}
          >
            <option value="">All Meters</option>
            {meters.map(m => (
              <option key={m.id} value={String(m.id)}>
                {m.label} ({m.meter_number})
              </option>
            ))}
          </select>
          {meterFilter && (
            <button
              className="btn btn-sm btn-secondary"
              onClick={() => setMeterFilter('')}
            >
              Show all
            </button>
          )}
        </div>
      )}

      {/* Rate history table */}
      <div style={{ fontSize: 13, fontWeight: 700, textTransform: 'uppercase', color: '#718096', marginBottom: 10 }}>
        Full Rate History
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Billing Period</th>
              {meters.length > 1 && <th>Meter</th>}
              <th>Base Tariff (₹/kWh)</th>
              <th>Effective Rate (₹/kWh)</th>
              <th>Total Units (kWh)</th>
              <th>Total Bill (₹)</th>
              <th>Flats Billed</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr className="empty-row">
                <td colSpan={meters.length > 1 ? 7 : 6}>Loading…</td>
              </tr>
            ) : filteredBills.length === 0 ? (
              <tr className="empty-row">
                <td colSpan={meters.length > 1 ? 7 : 6}>
                  No billing history yet
                </td>
              </tr>
            ) : (
              filteredBills
                .slice()
                .sort(byTillDesc)
                .map((b, i) => {
                  const meter = meterMap[b.meter_id];
                  const isLatest = i === 0 || (meterFilter && i === 0);
                  return (
                    <tr key={b.id}>
                      <td>
                        <strong>{fmtPeriod(b.period_from, b.period_till)}</strong>
                        {isLatest && !meterFilter && (
                          <span className="badge badge-green" style={{ marginLeft: 8 }}>Latest</span>
                        )}
                      </td>
                      {meters.length > 1 && (
                        <td>
                          <div style={{ fontWeight: 600, fontSize: 13 }}>
                            {b.meter_label || meter?.label || '—'}
                          </div>
                          <div style={{ fontFamily: 'monospace', fontSize: 11, color: '#718096' }}>
                            {b.meter_number || meter?.meter_number || ''}
                          </div>
                        </td>
                      )}
                      <td>{fmtMoney(b.effective_unit_rate, 4)}</td>
                      <td>
                        <strong>{fmtMoney(b.effective_unit_rate, 4)}</strong>
                      </td>
                      <td>{parseFloat(b.total_units_consumed).toFixed(2)}</td>
                      <td>{fmtMoney(b.total_bill_amount)}</td>
                      <td>
                        <span className="badge badge-blue">{b.total_flats}</span>
                      </td>
                    </tr>
                  );
                })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}