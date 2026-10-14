import { useState } from 'react';
import { api } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import Modal from '../../components/common/Modal';
import SocietySelector from '../../components/common/SocietySelector';
import DeleteAllButton from '../../components/common/DeleteAllButton';
import CsvUploadPanel from '../../components/common/CsvUploadPanel';

const SAMPLE_CSV = 'flat_number,owner_name,email\nA101,John Doe,john@example.com\nA102,Jane Smith,jane@example.com\n';

export default function Flats() {
  const { showToast } = useToast();
  const [societyId, setSocietyId] = useState(null);
  const [flats, setFlats] = useState([]);
  const [loading, setLoading] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);

  async function loadFlats(sid = societyId) {
    if (!sid) return;
    setLoading(true);
    try {
      const data = await api('GET', `/api/societies/${sid}/flats`);
      setFlats(data);
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setLoading(false);
    }
  }

  function onSocietyChange(id) {
    setSocietyId(id);
    setFlats([]);
    if (id) loadFlats(id);
  }

  async function handleDelete() {
    try {
      await api('DELETE', `/api/societies/${societyId}/flats/${deleteTarget.id}`);
      setDeleteTarget(null);
      showToast('Flat deleted');
      loadFlats();
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  return (
    <div>
      <div className="page-header" style={{ marginBottom: 20 }}>
        <div className="page-title">Flats</div>
        {societyId && <DeleteAllButton societyId={societyId} scope="flats" onDone={() => loadFlats()} />}
      </div>

      <SocietySelector value={societyId} onChange={onSocietyChange} />

      {societyId && (
        <>
          <CsvUploadPanel
            title="📤 Bulk Upload Flats (CSV)"
            hint={
              <>
                Required columns: <code>flat_number</code> &nbsp;|&nbsp; Optional: <code>owner_name</code>,{' '}
                <code>email</code>
              </>
            }
            uploadPath={`/api/societies/${societyId}/flats/csv`}
            sampleCsv={SAMPLE_CSV}
            sampleFilename="flats_sample.csv"
            skippedKey="flat_number"
            onUploaded={() => loadFlats()}
          />

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Flat No.</th>
                  <th>Owner</th>
                  <th>Email</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr className="empty-row">
                    <td colSpan={5}>Loading…</td>
                  </tr>
                ) : flats.length === 0 ? (
                  <tr className="empty-row">
                    <td colSpan={5}>No flats yet — upload a CSV</td>
                  </tr>
                ) : (
                  flats.map(f => (
                    <tr key={f.id}>
                      <td>{f.id}</td>
                      <td>
                        <strong>{f.flat_number}</strong>
                      </td>
                      <td>{f.owner_name || '—'}</td>
                      <td>{f.email || '—'}</td>
                      <td>
                        <button className="btn btn-sm btn-danger" onClick={() => setDeleteTarget(f)}>
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      <Modal
        open={!!deleteTarget}
        title="Delete Flat"
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        confirmLabel="Delete"
      >
        <p style={{ color: '#4a5568', fontSize: 14 }}>
          Delete flat <strong>{deleteTarget?.flat_number}</strong>? This will also delete its charger and RFID
          cards.
        </p>
      </Modal>
    </div>
  );
}
