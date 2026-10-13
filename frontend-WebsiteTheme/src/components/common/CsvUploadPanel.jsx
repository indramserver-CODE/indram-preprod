import { useRef, useState } from 'react';
import { apiUpload } from '../../api/client';

/**
 * Generic CSV upload panel.
 * props:
 *  - title: heading text
 *  - hint: JSX/string describing required columns
 *  - uploadPath: API path to POST the FormData to
 *  - sampleCsv: string content for the "download sample" link
 *  - sampleFilename: filename for the sample download
 *  - onUploaded: callback(result) after a successful upload
 *  - skippedKey: field name in each skipped_details row to show (e.g. 'flat_number')
 */
export default function CsvUploadPanel({ title, hint, uploadPath, sampleCsv, sampleFilename, onUploaded, skippedKey }) {
  const fileRef = useRef(null);
  const [result, setResult] = useState(null); // { type: 'success'|'error', message, skippedDetails }

  async function handleUpload() {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setResult({ type: 'error', message: 'Select a CSV file first' });
      return;
    }
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await apiUpload(uploadPath, formData);
      setResult({
        type: 'success',
        message: `✅ Imported: ${res.imported}`,
        skipped: res.skipped,
        skippedDetails: res.skipped_details || [],
      });
      fileRef.current.value = '';
      onUploaded?.(res);
    } catch (e) {
      setResult({ type: 'error', message: '❌ ' + e.message });
    }
  }

  function downloadSample(e) {
    e.preventDefault();
    const blob = new Blob([sampleCsv], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = sampleFilename;
    a.click();
  }

  return (
    <div className="upload-panel">
      <h3>{title}</h3>
      <p style={{ fontSize: 13, color: '#4a5568', marginBottom: 10 }}>{hint}</p>
      <div className="upload-row">
        <input ref={fileRef} type="file" accept=".csv" style={{ width: 'auto' }} />
        <button className="btn btn-primary" onClick={handleUpload}>
          Upload
        </button>
        <a href="#" onClick={downloadSample} style={{ fontSize: 13, color: '#15803d' }}>
          Download sample CSV
        </a>
      </div>
      {result && (
        <div
          className={`upload-result ${result.type}`}
          style={{ display: 'block' }}
        >
          {result.message}
          {result.skipped > 0 && (
            <>
              {' '}
              &nbsp;|&nbsp; ⚠️ Skipped: {result.skipped}
              {result.skippedDetails.length > 0 && (
                <ul style={{ marginTop: 6, paddingLeft: 16 }}>
                  {result.skippedDetails.map((d, i) => (
                    <li key={i}>
                      Row {d.row}
                      {skippedKey && d[skippedKey] ? ` (${d[skippedKey]})` : ''}: {d.reason}
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
