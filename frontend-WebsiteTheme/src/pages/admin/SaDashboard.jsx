import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../../api/client';
import { useToast } from '../../context/ToastContext';

function todayMonth() {
  const t = new Date();
  return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}`;
}

const QUICK_LINKS = [
  { to: '/admin/flats', title: 'Flats', sub: 'Manage flats & residents' },
  { to: '/admin/meters', title: 'Meters', sub: 'MSEB meter information' },
  { to: '/admin/sessions', title: 'Live', sub: 'Live charging view' },
  { to: '/admin/completed', title: 'History', sub: 'Completed sessions' },
  { to: '/admin/usage', title: 'Usage', sub: 'Monthly consumption' },
  { to: '/admin/bills', title: 'Bills', sub: 'Monthly bill history' },
  { to: '/admin/tariff', title: 'Tariff', sub: 'Rate history per meter' },
  { to: '/admin/tickets', title: 'Support', sub: 'Raise & track issues' },
  { to: '/admin/analytics', title: 'Analytics', sub: 'Charging insights & reports' },
];

export default function SaDashboard() {
  const { showToast } = useToast();
  const [societyName, setSocietyName] = useState('');
  const [cards, setCards] = useState({ active: '—', monthSessions: '—', monthUnits: '—', errors: '—' });
  const [meters, setMeters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [metersLoading, setMetersLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const society = await api('GET', '/api/usage/society');
      setSocietyName(society.name);

      const active = await api('GET', '/api/sessions/active');
      const completed = await api('GET', `/api/sessions/completed?month=${todayMonth()}`);
      const totalUnits = completed.reduce((s, x) => s + parseFloat(x.units_consumed || 0), 0);
      const errors = completed.filter(x => x.status === 'charging_ended_error').length;

      setCards({
        active: active.length,
        monthSessions: completed.length,
        monthUnits: totalUnits.toFixed(2),
        errors,
      });
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setLoading(false);
    }
  }

  async function loadMeters() {
    setMetersLoading(true);
    try {
      const data = await api('GET', '/api/sa/meters');
      setMeters(data);
    } catch {
      // meters are non-critical on dashboard — fail silently
    } finally {
      setMetersLoading(false);
    }
  }

  useEffect(() => {
    load();
    loadMeters();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const totalChargers = meters.reduce((s, m) => s + (m.charger_count || 0), 0);

  return (
    <div>
      {/* Header */}
      <div className="page-header">
        <div>
          <div className="page-title">Dashboard</div>
          <div style={{ fontSize: 13, color: '#4a5568', marginTop: 2 }}>{societyName}</div>
        </div>
        <button className="btn btn-secondary" onClick={load}>
          🔄 Refresh
        </button>
      </div>

      {/* KPI cards */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
        gap: 16,
        marginBottom: 28,
      }}>
        <div className="table-wrap" style={{ padding: 20 }}>
          <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: '#718096', marginBottom: 8 }}>
            Active Sessions
          </div>
          <div style={{ fontSize: 32, fontWeight: 700, color: '#1a202c' }}>
            {loading ? '—' : cards.active}
          </div>
          <Link to="/admin/sessions" style={{ fontSize: 12, color: '#15803d', textDecoration: 'none' }}>
            View all →
          </Link>
        </div>

        <div className="table-wrap" style={{ padding: 20 }}>
          <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: '#718096', marginBottom: 8 }}>
            This Month Sessions
          </div>
          <div style={{ fontSize: 32, fontWeight: 700, color: '#1a202c' }}>
            {loading ? '—' : cards.monthSessions}
          </div>
          <Link to="/admin/completed" style={{ fontSize: 12, color: '#15803d', textDecoration: 'none' }}>
            View all →
          </Link>
        </div>

        <div className="table-wrap" style={{ padding: 20 }}>
          <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: '#718096', marginBottom: 8 }}>
            This Month Units
          </div>
          <div style={{ fontSize: 32, fontWeight: 700, color: '#1a202c' }}>
            {loading ? '—' : cards.monthUnits}
          </div>
          <span style={{ fontSize: 12, color: '#4a5568' }}>kWh consumed</span>
        </div>

        <div className="table-wrap" style={{ padding: 20 }}>
          <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: '#718096', marginBottom: 8 }}>
            Error Sessions
          </div>
          <div style={{ fontSize: 32, fontWeight: 700, color: !loading && cards.errors > 0 ? '#c53030' : '#1a202c' }}>
            {loading ? '—' : cards.errors}
          </div>
          <Link to="/admin/completed" style={{ fontSize: 12, color: '#15803d', textDecoration: 'none' }}>
            View →
          </Link>
        </div>
      </div>

      {/* Meters overview strip */}
      <div style={{ marginBottom: 28 }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 12,
        }}>
          <div style={{ fontSize: 13, fontWeight: 700, textTransform: 'uppercase', color: '#718096' }}>
            Meters Overview
          </div>
          <span style={{ fontSize: 12, color: '#4a5568' }}>
            {metersLoading ? '' : `${meters.length} meter${meters.length !== 1 ? 's' : ''} · ${totalChargers} charger${totalChargers !== 1 ? 's' : ''} total`}
          </span>
        </div>

        {metersLoading ? (
          <div style={{ color: '#a0aec0', fontSize: 13 }}>Loading meters…</div>
        ) : meters.length === 0 ? (
          <div style={{
            background: '#fff8e1',
            border: '1px solid #fde68a',
            borderRadius: 10,
            padding: '14px 18px',
            fontSize: 13,
            color: '#92400e',
          }}>
            ⚠️ No meters configured for your society yet. Contact your super admin to add meters.
          </div>
        ) : (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
            gap: 12,
          }}>
            {meters.map(m => (
              <div key={m.id} style={{
                background: '#ffffff',
                border: '1px solid rgba(0,0,0,0.08)',
                borderRadius: 12,
                padding: '16px 18px',
                boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
              }}>
                <div style={{
                  fontSize: 12, fontWeight: 700,
                  textTransform: 'uppercase', color: '#718096', marginBottom: 4,
                }}>
                  {m.label}
                </div>
                <div style={{
                  fontFamily: 'monospace', fontSize: 11,
                  color: '#a0aec0', marginBottom: 10,
                }}>
                  {m.meter_number}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span className={`badge ${m.charger_count > 0 ? 'badge-green' : 'badge-gray'}`}>
                    {m.charger_count} charger{m.charger_count !== 1 ? 's' : ''}
                  </span>
                  {m.location && (
                    <span style={{ fontSize: 11, color: '#718096' }}>📍 {m.location}</span>
                  )}
                </div>
                {m.sanctioned_load && (
                  <div style={{ fontSize: 11, color: '#718096', marginTop: 6 }}>
                    ⚡ {parseFloat(m.sanctioned_load).toFixed(1)} kW sanctioned
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Quick access */}
      <div className="page-title" style={{ fontSize: 16, marginBottom: 14 }}>
        Quick Access
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 12 }}>
        {QUICK_LINKS.map(link => (
          <Link
            key={link.to}
            to={link.to}
            className="table-wrap"
            style={{
              padding: 18,
              textDecoration: 'none',
              display: 'block',
              transition: 'box-shadow .2s, border-color .2s',
            }}
            onMouseOver={e => {
              e.currentTarget.style.boxShadow = '0 8px 24px rgba(0,0,0,0.12)';
              e.currentTarget.style.borderColor = 'rgba(0,255,65,0.3)';
            }}
            onMouseOut={e => {
              e.currentTarget.style.boxShadow = '';
              e.currentTarget.style.borderColor = '';
            }}
          >
            <div style={{ fontSize: 14, fontWeight: 600, color: '#1a202c' }}>{link.title}</div>
            <div style={{ fontSize: 12, color: '#718096', marginTop: 2 }}>{link.sub}</div>
          </Link>
        ))}
      </div>
    </div>
  );
}