import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import { useToast } from '../../context/ToastContext';

/**
 * MeterSelector — loads the society admin's meters and renders a styled
 * selector bar. Calls onChange(meter | null) with the full meter object
 * so callers have access to meter_number and label, not just the id.
 *
 * Props:
 *   value      — currently selected meter object (or null)
 *   onChange   — callback(meter | null)
 *   className  — optional extra class on the wrapper
 */
export default function MeterSelector({ value, onChange, className = '' }) {
  const { showToast } = useToast();
  const [meters, setMeters] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api('GET', '/api/sa/meters')
      .then(data => {
        setMeters(data);
        // If there's only one meter, auto-select it for convenience
        if (data.length === 1 && !value) {
          onChange(data[0]);
        }
      })
      .catch(e => showToast(e.message, 'error'))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleChange(e) {
    const id = e.target.value ? parseInt(e.target.value, 10) : null;
    onChange(id ? meters.find(m => m.id === id) || null : null);
  }

  return (
    <div className={`selector-bar ${className}`}>
      <label style={{ display: 'flex', alignItems: 'center', gap: 6, margin: 0, whiteSpace: 'nowrap' }}>
        ⚡ Meter:
      </label>
      <select value={value?.id ?? ''} onChange={handleChange} style={{ maxWidth: 340 }}>
        <option value="">
          {loading ? 'Loading meters…' : meters.length === 0 ? 'No meters configured' : '— Select a meter —'}
        </option>
        {meters.map(m => (
          <option key={m.id} value={m.id}>
            {m.label} ({m.meter_number})
            {m.charger_count !== undefined ? ` — ${m.charger_count} charger${m.charger_count !== 1 ? 's' : ''}` : ''}
          </option>
        ))}
      </select>

      {value && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          marginLeft: 8,
          padding: '4px 12px',
          background: 'rgba(0, 255, 65, 0.08)',
          border: '1px solid rgba(0, 255, 65, 0.2)',
          borderRadius: 8,
          fontSize: 13,
        }}>
          {value.location && (
            <span style={{ color: '#4a5568' }}>📍 {value.location}</span>
          )}
          {value.sanctioned_load && (
            <span style={{ color: '#4a5568' }}>⚡ {parseFloat(value.sanctioned_load).toFixed(1)} kW sanctioned</span>
          )}
          <span style={{ color: '#15803d', fontWeight: 600 }}>
            {value.charger_count} charger{value.charger_count !== 1 ? 's' : ''}
          </span>
        </div>
      )}
    </div>
  );
}