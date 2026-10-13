import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import { useToast } from '../../context/ToastContext';

export default function SaMeters() {
  const { showToast } = useToast();
  const [societyName, setSocietyName] = useState('');
  const [meters, setMeters]           = useState([]);
  const [loading, setLoading]         = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [society, meterData] = await Promise.all([
          api('GET', '/api/usage/society').catch(() => ({})),
          api('GET', '/api/sa/meters'),
        ]);
        setSocietyName(society?.name || '');
        setMeters(meterData);
      } catch (e) {
        showToast(e.message, 'error');
      } finally {
        setLoading(false);
      }
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const totalChargers     = meters.reduce((s, m) => s + (m.charger_count || 0), 0);
  const totalSanctionedKw = meters.reduce((s, m) => s + parseFloat(m.sanctioned_load || 0), 0);

  return (
    <div>
      {/* Header */}
      <div className="page-header">
        <div>
          <div className="page-title">Electricity Meters</div>
          <div style={{ fontSize: 13, color: '#4a5568', marginTop: 2 }}>{societyName}</div>
        </div>
      </div>

      {/* Info banner */}
      <div style={{
        background: 'rgba(0, 255, 65, 0.06)',
        border: '1px solid rgba(0, 255, 65, 0.2)',
        borderRadius: 12,
        padding: '16px 20px',
        marginBottom: 24,
        display: 'flex',
        alignItems: 'flex-start',
        gap: 14,
      }}>
        <span style={{ fontSize: 22, flexShrink: 0 }}>ℹ️</span>
        <div>
          <div style={{ fontWeight: 700, fontSize: 14, color: '#1a202c', marginBottom: 4 }}>
            About your society's meters
          </div>
          <div style={{ fontSize: 13, color: '#4a5568', lineHeight: 1.7 }}>
            Each meter represents a physical MSEB electricity meter installed in your society.
            Chargers are grouped under meters — billing is generated separately per meter each month.
            Meter details can only be changed by your super admin.
          </div>
        </div>
      </div>

      {/* Summary strip */}
      {!loading && meters.length > 0 && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
          gap: 12,
          marginBottom: 24,
        }}>
          {[
            { label: 'Total Meters',          value: meters.length,               unit: '' },
            { label: 'Total Chargers',         value: totalChargers,               unit: '' },
            { label: 'Total Sanctioned Load',  value: totalSanctionedKw.toFixed(1), unit: ' kW' },
          ].map(item => (
            <div key={item.label} style={{
              background: '#ffffff',
              border: '1px solid rgba(0,0,0,0.08)',
              borderRadius: 12,
              padding: '16px 18px',
              boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
            }}>
              <div style={{
                fontSize: 11, fontWeight: 700,
                textTransform: 'uppercase', color: '#718096', marginBottom: 6,
              }}>
                {item.label}
              </div>
              <div style={{ fontSize: 26, fontWeight: 700, color: '#1a202c' }}>
                {item.value}
                <span style={{ fontSize: 13, color: '#718096', fontWeight: 400 }}>{item.unit}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Meters grid */}
      {loading ? (
        <div style={{ color: '#a0aec0', fontSize: 14, padding: 32, textAlign: 'center' }}>
          Loading meters…
        </div>
      ) : meters.length === 0 ? (
        <div style={{
          background: '#fff8e1',
          border: '1px solid #fde68a',
          borderRadius: 12,
          padding: '28px 24px',
          textAlign: 'center',
        }}>
          <div style={{ fontSize: 28, marginBottom: 10 }}>⚠️</div>
          <div style={{ fontWeight: 700, fontSize: 15, color: '#92400e', marginBottom: 6 }}>
            No meters configured
          </div>
          <div style={{ fontSize: 13, color: '#78350f' }}>
            Contact your super admin to set up the MSEB meters for your society.
            Billing and charger assignment require at least one meter.
          </div>
        </div>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
          gap: 16,
        }}>
          {meters.map(m => (
            <div key={m.id} style={{
              background: '#ffffff',
              border: '1px solid rgba(0,0,0,0.08)',
              borderRadius: 14,
              overflow: 'hidden',
              boxShadow: '0 2px 12px rgba(0,0,0,0.05)',
            }}>
              {/* Card header */}
              <div style={{
                background: 'linear-gradient(135deg, #315906 0%, #1A2F03 100%)',
                padding: '18px 20px',
              }}>
                <div style={{
                  fontSize: 16, fontWeight: 700, color: '#ffffff', marginBottom: 4,
                }}>
                  {m.label}
                </div>
                <div style={{
                  fontFamily: 'monospace', fontSize: 12,
                  color: 'rgba(255,255,255,0.7)',
                  background: 'rgba(0,0,0,0.2)',
                  display: 'inline-block',
                  padding: '2px 8px',
                  borderRadius: 4,
                }}>
                  {m.meter_number}
                </div>
              </div>

              {/* Card body */}
              <div style={{ padding: '18px 20px' }}>

                {/* Charger count */}
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  marginBottom: 14,
                  paddingBottom: 14,
                  borderBottom: '1px solid rgba(0,0,0,0.06)',
                }}>
                  <span style={{ fontSize: 13, color: '#4a5568', fontWeight: 500 }}>
                    Chargers assigned
                  </span>
                  <span className={`badge ${m.charger_count > 0 ? 'badge-green' : 'badge-gray'}`}
                    style={{ fontSize: 13 }}>
                    {m.charger_count}  charger{m.charger_count !== 1 ? 's' : ''}
                  </span>
                </div>

                {/* Details rows */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <DetailRow
                    icon="📍"
                    label="Location"
                    value={m.location || null}
                    fallback="Not specified"
                  />
                  <DetailRow
                    icon="⚡"
                    label="Sanctioned Load"
                    value={m.sanctioned_load
                      ? `${parseFloat(m.sanctioned_load).toFixed(1)} kW`
                      : null}
                    fallback="Not specified"
                  />
                </div>

                {/* Billing note */}
                <div style={{
                  marginTop: 16,
                  padding: '10px 12px',
                  background: 'rgba(0,255,65,0.06)',
                  border: '1px solid rgba(0,255,65,0.15)',
                  borderRadius: 8,
                  fontSize: 12,
                  color: '#15803d',
                }}>
                  💡 Monthly bills for flats under this meter are generated separately
                  from the <strong>Bills</strong> page.
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DetailRow({ icon, label, value, fallback }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
      <span style={{ fontSize: 14, flexShrink: 0, marginTop: 1 }}>{icon}</span>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: '#718096', marginBottom: 2 }}>
          {label}
        </div>
        <div style={{ fontSize: 13, color: value ? '#1a202c' : '#a0aec0' }}>
          {value || fallback}
        </div>
      </div>
    </div>
  );
}