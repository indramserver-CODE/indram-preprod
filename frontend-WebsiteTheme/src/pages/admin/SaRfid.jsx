import { useEffect, useMemo, useState } from 'react';
import { api } from '../../api/client';
import { useToast } from '../../context/ToastContext';

export default function SaRfid() {
  const { showToast } = useToast();
  const [societyName, setSocietyName] = useState('');
  const [cards, setCards] = useState([]);
  const [flats, setFlats] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter]   = useState('');
  const [cardsFilter, setCardsFilter]     = useState('');
  const [chargerFilter, setChargerFilter] = useState('');
  const [meterFilter, setMeterFilter]     = useState('');

  // ── Data loading ────────────────────────────────────────────────────

  async function load() {
    setLoading(true);
    try {
      const [c, f] = await Promise.all([
        api('GET', '/api/sa/rfid'),
        api('GET', '/api/sa/flats'),
      ]);
      setCards(c);
      setFlats(f);
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    api('GET', '/api/usage/society').then(s => setSocietyName(s.name)).catch(() => { });
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Flat groups ─────────────────────────────────────────────────────

  const groups = useMemo(() => {
    const map = {};
    flats.forEach(f => {
      map[f.id] = { flat_id: f.id, flat_number: f.flat_number, charger_id: f.charger_id || null, meter_id: f.meter_id ?? null, cards: [] };
    });
    cards.forEach(c => {
      if (map[c.flat_id]) map[c.flat_id].cards.push(c);
    });
    let list = Object.values(map);
    const q = search.toLowerCase().trim();
    if (q) list = list.filter(g =>
      (g.flat_number || '').toLowerCase().includes(q) ||
      g.cards.some(c => (c.uid || '').toLowerCase().includes(q))
    );
    if (meterFilter) list = list.filter(g => String(g.meter_id) === meterFilter);
    if (chargerFilter) list = list.filter(g => (chargerFilter === 'with') === !!g.charger_id);
    if (cardsFilter === 'none') list = list.filter(g => g.cards.length === 0);
    else if (cardsFilter === 'some') list = list.filter(g => g.cards.length > 0);
    else if (cardsFilter === 'full') list = list.filter(g => g.cards.length >= 3);
    if (statusFilter) {
      const wantActive = statusFilter === 'active';
      list = list
        .map(g => ({ ...g, cards: g.cards.filter(c => !!c.is_active === wantActive) }))
        .filter(g => g.cards.length > 0);
    }
    return list.sort((a, b) => a.flat_number.localeCompare(b.flat_number));
  }, [flats, cards, search, statusFilter, cardsFilter, chargerFilter, meterFilter]);

  const meters = useMemo(() => {
    const m = new Map();
    flats.forEach(f => { if (f.meter_id != null) m.set(f.meter_id, f.meter_label || `Meter ${f.meter_id}`); });
    return [...m.entries()];
  }, [flats]);

  const filtersActive = !!(search || statusFilter || cardsFilter || chargerFilter || meterFilter);
  function clearFilters() {
    setSearch(''); setStatusFilter(''); setCardsFilter(''); setChargerFilter(''); setMeterFilter('');
  }

  // ── Stats ────────────────────────────────────────────────────────────

  const totalCards = cards.length;
  const activeCards = cards.filter(c => c.is_active).length;
  const flatsWithCards = new Set(cards.map(c => c.flat_id)).size;

  // ── Render ───────────────────────────────────────────────────────────

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">RFID Cards</div>
          <div style={{ fontSize: 13, color: '#4a5568', marginTop: 2 }}>{societyName}</div>
        </div>
        <button className="btn btn-secondary" onClick={load}>🔄 Refresh</button>
      </div>

      {/* Summary strip */}
      {!loading && cards.length > 0 && (
        <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
          {[
            { label: 'Total Cards', value: totalCards, color: '#1a202c' },
            { label: 'Active', value: activeCards, color: '#15803d' },
            { label: 'Inactive', value: totalCards - activeCards, color: totalCards - activeCards > 0 ? '#c53030' : '#a0aec0' },
            { label: 'Flats with Cards', value: flatsWithCards, color: '#4338ca' },
          ].map(item => (
            <div key={item.label} style={{
              background: '#ffffff',
              border: '1px solid rgba(0,0,0,0.08)',
              borderRadius: 10,
              padding: '10px 16px',
              minWidth: 120,
            }}>
              <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: '#718096', marginBottom: 3 }}>
                {item.label}
              </div>
              <div style={{ fontSize: 20, fontWeight: 700, color: item.color }}>{item.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Search + filters */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
        <input
          type="text"
          placeholder="Search by flat number or UID…"
          style={{ maxWidth: 300, flex: '1 1 200px' }}
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{ maxWidth: 160, flex: '0 1 160px' }}>
          <option value="">All Card Status</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>
        <select value={cardsFilter} onChange={e => setCardsFilter(e.target.value)} style={{ maxWidth: 180, flex: '0 1 180px' }}>
          <option value="">All Flats</option>
          <option value="some">Has cards</option>
          <option value="none">No cards</option>
          <option value="full">All 3 slots used</option>
        </select>
        <select value={chargerFilter} onChange={e => setChargerFilter(e.target.value)} style={{ maxWidth: 170, flex: '0 1 170px' }}>
          <option value="">All Chargers</option>
          <option value="with">With charger</option>
          <option value="without">No charger</option>
        </select>
        {meters.length > 1 && (
          <select value={meterFilter} onChange={e => setMeterFilter(e.target.value)} style={{ maxWidth: 220, flex: '0 1 220px' }}>
            <option value="">All Meters</option>
            {meters.map(([id, label]) => <option key={id} value={String(id)}>{label}</option>)}
          </select>
        )}
        {filtersActive && (
          <>
            <button className="btn btn-sm btn-secondary" onClick={clearFilters}>Clear filters</button>
            <span style={{ fontSize: 13, color: '#718096' }}>
              {groups.length} of {flats.length} flats
            </span>
          </>
        )}
      </div>

      {/* Grouped flat cards — read-only */}
      {loading ? (
        <div style={{ color: '#718096', padding: 32, textAlign: 'center' }}>Loading…</div>
      ) : groups.length === 0 ? (
        <div style={{ color: '#718096', padding: 32, textAlign: 'center' }}>
          {flats.length === 0 ? 'No flats found' : 'No flats match your filters'}
        </div>
      ) : (
        groups.map(g => (
          <div className="table-wrap" style={{ marginBottom: 16 }} key={g.flat_id}>
            {/* Flat header */}
            <div style={{
              padding: '12px 16px',
              background: 'rgba(0,0,0,0.03)',
              borderBottom: '1px solid rgba(0,0,0,0.08)',
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              flexWrap: 'wrap',
            }}>
              <strong style={{ fontSize: 14 }}>🏠 {g.flat_number}</strong>
              {g.charger_id ? (
                <code style={{ fontSize: 12, color: '#4a5568' }}>{g.charger_id}</code>
              ) : (
                <span style={{ fontSize: 12, color: '#c53030' }}>No charger</span>
              )}
              <span style={{ fontSize: 12, color: '#718096' }}>{g.cards.length}/3 cards</span>
            </div>

            {/* Cards table */}
            <table>
              <thead>
                <tr>
                  <th>UID</th>
                  <th>Label</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {g.cards.length === 0 ? (
                  <tr className="empty-row">
                    <td colSpan={3}>No RFID cards assigned</td>
                  </tr>
                ) : (
                  g.cards.map(c => (
                    <tr key={c.id}>
                      <td><code style={{ fontSize: 13 }}>{c.uid}</code></td>
                      <td style={{ color: '#4a5568' }}>
                        {c.label || <span style={{ color: '#a0aec0' }}>—</span>}
                      </td>
                      <td>
                        <span className={`badge ${c.is_active ? 'badge-green' : 'badge-red'}`}>
                          {c.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        ))
      )}
    </div>
  );
}