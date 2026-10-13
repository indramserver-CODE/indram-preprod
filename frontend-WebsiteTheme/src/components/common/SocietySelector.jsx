import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import { useToast } from '../../context/ToastContext';

/**
 * Loads the society list and renders a <select>.
 * Calls onChange(id | null, name | null) so callers
 * have access to the society name without a second fetch.
 */
export default function SocietySelector({ value, onChange }) {
  const { showToast } = useToast();
  const [societies, setSocieties] = useState([]);

  useEffect(() => {
    api('GET', '/api/societies')
      .then(setSocieties)
      .catch(e => showToast(e.message, 'error'));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleChange(e) {
    const id = e.target.value ? parseInt(e.target.value, 10) : null;
    const society = id ? societies.find(s => s.id === id) : null;
    onChange(id, society?.name || null);
  }

  return (
    <div className="selector-bar">
      <label>Society:</label>
      <select value={value ?? ''} onChange={handleChange}>
        <option value="">— Select a society —</option>
        {societies.map(s => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </select>
    </div>
  );
}