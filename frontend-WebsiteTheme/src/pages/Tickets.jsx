import { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import { useToast } from '../context/ToastContext';
import styles from '../styles/Tickets.module.css';

const PAGE_SIZE = 25;
const dateFmt = new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
const fmtDate = iso => (iso ? dateFmt.format(new Date(iso)) : '—');

const STATUS_BADGE = {
  open: styles.badgeOpen,
  in_progress: styles.badgeInProgress,
  resolved: styles.badgeResolved,
  closed: styles.badgeClosed,
};
const PRIORITY_BADGE = {
  high: styles.badgeHigh,
  medium: styles.badgeMedium,
  low: styles.badgeLow,
};

function StatusBadge({ status }) {
  return <span className={`${styles.badge} ${STATUS_BADGE[status] || ''}`}>{status.replace('_', ' ')}</span>;
}
function PriorityBadge({ priority }) {
  return <span className={`${styles.badge} ${PRIORITY_BADGE[priority] || ''}`}>{priority}</span>;
}

/**
 * scope: 'super' — all societies, with admin controls (status/priority edit, delete) + stats cards
 *        'society' — own tickets, with create-ticket modal + comment count column
 */
export default function Tickets({ scope }) {
  const { showToast } = useToast();
  const isSuper = scope === 'super';

  const [filters, setFilters] = useState({ status: '', priority: '', category: '', search: '' });
  const [page, setPage] = useState(1);
  const [result, setResult] = useState(null); // { items, total, page, page_size, pages }
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(null);

  const [currentTicketId, setCurrentTicketId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [ctrlStatus, setCtrlStatus] = useState('open');
  const [ctrlPriority, setCtrlPriority] = useState('low');
  const [newComment, setNewComment] = useState('');
  const [isInternal, setIsInternal] = useState(false);

  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState({ title: '', category: 'other', priority: 'medium', description: '' });

  const debounceRef = useRef(null);

  async function loadStats() {
    if (!isSuper) return;
    try {
      const s = await api('GET', '/api/tickets/stats');
      setStats(s);
    } catch (e) {
      console.warn('Stats fetch failed:', e.message);
    }
  }

  async function loadTickets(p = page) {
    const params = new URLSearchParams();
    if (filters.status) params.set('status', filters.status);
    if (filters.priority) params.set('priority', filters.priority);
    if (filters.category) params.set('category', filters.category);
    if (filters.search) params.set('search', filters.search);
    params.set('page', p);
    params.set('page_size', PAGE_SIZE);

    setLoading(true);
    try {
      const res = await api('GET', `/api/tickets/?${params}`);
      setResult(res);
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadStats();
    loadTickets(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    loadTickets(page);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  function onFilterChange(patch) {
    setFilters(f => ({ ...f, ...patch }));
    setPage(1);
  }

  function onSearchInput(value) {
    setFilters(f => ({ ...f, search: value }));
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setPage(1);
      loadTickets(1);
    }, 350);
  }

  // Reload when non-search filters change (search is debounced separately)
  useEffect(() => {
    loadTickets(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.status, filters.priority, filters.category]);

  async function openDetail(id) {
    setCurrentTicketId(id);
    setDetail(null);
    setDetailLoading(true);
    try {
      const t = await api('GET', `/api/tickets/${id}`);
      setDetail(t);
      setCtrlStatus(t.status);
      setCtrlPriority(t.priority);
    } catch (e) {
      showToast(e.message, 'error');
      setCurrentTicketId(null);
    } finally {
      setDetailLoading(false);
    }
  }

  function closeDetail() {
    setCurrentTicketId(null);
    setDetail(null);
    setNewComment('');
    setIsInternal(false);
  }

  async function saveTicketChanges() {
    try {
      const t = await api('PATCH', `/api/tickets/${currentTicketId}`, { status: ctrlStatus, priority: ctrlPriority });
      showToast('Ticket updated');
      setDetail(t);
      loadTickets();
      loadStats();
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  async function deleteCurrentTicket() {
    if (!confirm('Delete this ticket permanently?')) return;
    try {
      await api('DELETE', `/api/tickets/${currentTicketId}`);
      showToast('Ticket deleted');
      closeDetail();
      loadTickets();
      loadStats();
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  async function submitComment() {
    const body = newComment.trim();
    if (!body) {
      showToast('Comment cannot be empty', 'error');
      return;
    }
    try {
      const c = await api('POST', `/api/tickets/${currentTicketId}/comments`, {
        body,
        is_internal: isSuper ? isInternal : false,
      });
      setNewComment('');
      setIsInternal(false);
      showToast('Comment posted');
      setDetail(d => ({ ...d, comments: [...d.comments, c] }));
      loadTickets();
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  function openCreateModal() {
    setCreateForm({ title: '', category: 'other', priority: 'medium', description: '' });
    setCreateOpen(true);
  }

  async function submitCreateTicket() {
    const { title, description, category, priority } = createForm;
    if (!title.trim() || title.trim().length < 3) {
      showToast('Title must be at least 3 characters', 'error');
      return;
    }
    if (!description.trim() || description.trim().length < 10) {
      showToast('Description must be at least 10 characters', 'error');
      return;
    }
    try {
      await api('POST', '/api/tickets/', { title: title.trim(), description: description.trim(), category, priority });
      showToast('Ticket submitted successfully');
      setCreateOpen(false);
      setPage(1);
      loadTickets(1);
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  function pageButtons(current, total) {
    const delta = 2;
    const start = Math.max(1, current - delta);
    const end = Math.min(total, current + delta);
    const buttons = [];
    for (let i = start; i <= end; i++) {
      buttons.push(
        <button key={i} className={`${styles.pageBtn} ${i === current ? styles.active : ''}`} onClick={() => setPage(i)}>
          {i}
        </button>
      );
    }
    return buttons;
  }

  return (
    <div>
      <div className={styles.pageTitle}>
        {isSuper ? '🎫 Support Tickets — All Societies' : '🎫 Support Tickets'}
        {!isSuper && (
          <button className={styles.btnPrimary} onClick={openCreateModal}>
            + New Ticket
          </button>
        )}
      </div>

      {isSuper && stats && (
        <div className={styles.cards}>
          <div className={styles.card}>
            <div className={styles.cardLabel}>Open</div>
            <div className={styles.cardValue}>{stats.open}</div>
          </div>
          <div className={styles.card}>
            <div className={styles.cardLabel}>In Progress</div>
            <div className={styles.cardValue}>{stats.in_progress}</div>
          </div>
          <div className={styles.card}>
            <div className={styles.cardLabel}>Resolved</div>
            <div className={styles.cardValue}>{stats.resolved + stats.closed}</div>
          </div>
          <div className={styles.card}>
            <div className={styles.cardLabel}>Total</div>
            <div className={styles.cardValue}>{stats.total}</div>
          </div>
        </div>
      )}

      <div className={styles.filterBar}>
        <select value={filters.status} onChange={e => onFilterChange({ status: e.target.value })}>
          <option value="">All Statuses</option>
          <option value="open">Open</option>
          <option value="in_progress">In Progress</option>
          <option value="resolved">Resolved</option>
          <option value="closed">Closed</option>
        </select>
        <select value={filters.priority} onChange={e => onFilterChange({ priority: e.target.value })}>
          <option value="">All Priorities</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        <select value={filters.category} onChange={e => onFilterChange({ category: e.target.value })}>
          <option value="">All Categories</option>
          <option value="billing">Billing</option>
          <option value="charger">Charger</option>
          <option value="rfid">RFID</option>
          <option value="account">Account</option>
          <option value="other">Other</option>
        </select>
        <input type="text" placeholder="Search title…" value={filters.search} onChange={e => onSearchInput(e.target.value)} />
      </div>

      <div className={styles.panel}>
        {loading ? (
          <div className={styles.loadingMsg}>Loading tickets…</div>
        ) : !result?.items?.length ? (
          <div className={styles.emptyMsg}>No tickets found.</div>
        ) : (
          <table className={styles.dataTable}>
            <thead>
              <tr>
                <th>#</th>
                <th>Title</th>
                {isSuper && <th>Society</th>}
                {isSuper && <th>Raised By</th>}
                <th>Category</th>
                <th>Priority</th>
                <th>Status</th>
                {isSuper ? <th>Assigned</th> : <th>Comments</th>}
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {result.items.map(t => (
                <tr key={t.id}>
                  <td>#{t.id}</td>
                  <td style={{ maxWidth: 220, wordBreak: 'break-word' }}>{t.title}</td>
                  {isSuper && <td>{t.society_name || '—'}</td>}
                  {isSuper && <td>{t.created_by_name || '—'}</td>}
                  <td>{t.category}</td>
                  <td>
                    <PriorityBadge priority={t.priority} />
                  </td>
                  <td>
                    <StatusBadge status={t.status} />
                  </td>
                  {isSuper ? <td>{t.assigned_to_name || '—'}</td> : <td style={{ textAlign: 'center' }}>{t.comment_count}</td>}
                  <td>{fmtDate(t.created_at)}</td>
                  <td>
                    <button className={styles.viewBtn} onClick={() => openDetail(t.id)}>
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {result && result.pages > 1 && (
        <div className={styles.pagination}>
          <span className={styles.pageInfo}>
            Showing {(result.page - 1) * result.page_size + 1}–{Math.min(result.page * result.page_size, result.total)} of{' '}
            {result.total}
          </span>
          <div className={styles.pageControls}>
            <button className={styles.pageBtn} disabled={result.page === 1} onClick={() => setPage(1)}>
              «
            </button>
            <button className={styles.pageBtn} disabled={result.page === 1} onClick={() => setPage(result.page - 1)}>
              ‹
            </button>
            {pageButtons(result.page, result.pages)}
            <button className={styles.pageBtn} disabled={result.page === result.pages} onClick={() => setPage(result.page + 1)}>
              ›
            </button>
            <button className={styles.pageBtn} disabled={result.page === result.pages} onClick={() => setPage(result.pages)}>
              »
            </button>
          </div>
        </div>
      )}

      {/* Create ticket modal (society scope only) */}
      {createOpen && (
        <div className={styles.modalOverlay} onClick={() => setCreateOpen(false)}>
          <div className={styles.modal} onClick={e => e.stopPropagation()}>
            <div className={styles.modalHeader}>
              <h2>New Support Ticket</h2>
              <button className={styles.modalClose} onClick={() => setCreateOpen(false)}>
                ✕
              </button>
            </div>
            <div className={styles.modalBody}>
              <label>Title *</label>
              <input
                type="text"
                placeholder="Brief summary of the issue"
                value={createForm.title}
                onChange={e => setCreateForm({ ...createForm, title: e.target.value })}
              />
              <label>Category *</label>
              <select value={createForm.category} onChange={e => setCreateForm({ ...createForm, category: e.target.value })}>
                <option value="billing">Billing</option>
                <option value="charger">Charger</option>
                <option value="rfid">RFID</option>
                <option value="account">Account</option>
                <option value="other">Other</option>
              </select>
              <label>Priority</label>
              <select value={createForm.priority} onChange={e => setCreateForm({ ...createForm, priority: e.target.value })}>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
              <label>Description *</label>
              <textarea
                rows={5}
                placeholder="Describe the issue in detail…"
                value={createForm.description}
                onChange={e => setCreateForm({ ...createForm, description: e.target.value })}
              />
            </div>
            <div className={styles.modalFooter}>
              <button className={styles.btnSecondary} onClick={() => setCreateOpen(false)}>
                Cancel
              </button>
              <button className={styles.btnPrimary} onClick={submitCreateTicket}>
                Submit Ticket
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Detail modal */}
      {currentTicketId && (
        <div className={styles.modalOverlay} onClick={closeDetail}>
          <div className={`${styles.modal} ${styles.modalWide}`} onClick={e => e.stopPropagation()}>
            <div className={styles.modalHeader}>
              <h2>{detail ? `#${detail.id} — ${detail.title}` : `Ticket #${currentTicketId}`}</h2>
              <button className={styles.modalClose} onClick={closeDetail}>
                ✕
              </button>
            </div>
            <div className={styles.modalBody}>
              {detailLoading || !detail ? (
                <span className={styles.metaItem}>Loading…</span>
              ) : (
                <>
                  <div className={styles.detailMeta}>
                    <span className={styles.metaItem}>
                      <StatusBadge status={detail.status} />
                    </span>
                    <span className={styles.metaItem}>
                      <PriorityBadge priority={detail.priority} />
                    </span>
                    <span className={styles.metaItem}>
                      <strong>Category:</strong> {detail.category}
                    </span>
                    {isSuper && (
                      <span className={styles.metaItem}>
                        <strong>Society:</strong> {detail.society_name || '—'}
                      </span>
                    )}
                    {isSuper && (
                      <span className={styles.metaItem}>
                        <strong>Raised by:</strong> {detail.created_by_name || '—'}
                      </span>
                    )}
                    <span className={styles.metaItem}>
                      <strong>Created:</strong> {fmtDate(detail.created_at)}
                    </span>
                    {detail.resolved_at && (
                      <span className={styles.metaItem}>
                        <strong>Resolved:</strong> {fmtDate(detail.resolved_at)}
                      </span>
                    )}
                    {!isSuper && detail.assigned_to_name && (
                      <span className={styles.metaItem}>
                        <strong>Assigned to:</strong> {detail.assigned_to_name}
                      </span>
                    )}
                  </div>

                  {isSuper && (
                    <div className={styles.adminControls}>
                      <label>Status</label>
                      <select value={ctrlStatus} onChange={e => setCtrlStatus(e.target.value)}>
                        <option value="open">Open</option>
                        <option value="in_progress">In Progress</option>
                        <option value="resolved">Resolved</option>
                        <option value="closed">Closed</option>
                      </select>
                      <label>Priority</label>
                      <select value={ctrlPriority} onChange={e => setCtrlPriority(e.target.value)}>
                        <option value="low">Low</option>
                        <option value="medium">Medium</option>
                        <option value="high">High</option>
                      </select>
                      <button className={styles.btnPrimary} onClick={saveTicketChanges}>
                        Save Changes
                      </button>
                      <button className={styles.btnDanger} onClick={deleteCurrentTicket}>
                        Delete Ticket
                      </button>
                    </div>
                  )}

                  <div className={styles.detailDesc}>{detail.description}</div>

                  <div className={styles.commentsSection}>
                    <h3>Comments</h3>
                    <div>
                      {detail.comments.length === 0 ? (
                        <p style={{ color: '#718096', fontSize: 13 }}>No comments yet.</p>
                      ) : (
                        detail.comments.map(c => (
                          <div key={c.id} className={`${styles.commentBubble} ${c.is_internal ? styles.internal : styles.public}`}>
                            <div className={styles.commentMeta}>
                              {c.author_name || 'Unknown'}
                              {isSuper && (
                                <span style={{ fontWeight: 400, color: '#718096', marginLeft: 6 }}>{c.author_role || ''}</span>
                              )}
                              <span style={{ fontWeight: 400, marginLeft: 6 }}>{fmtDate(c.created_at)}</span>
                              {c.is_internal && <span className={styles.internalTag}>{isSuper ? 'Internal Note' : 'Internal'}</span>}
                            </div>
                            <div className={styles.commentBody}>{c.body}</div>
                          </div>
                        ))
                      )}
                    </div>
                    <div className={styles.commentForm}>
                      <textarea
                        rows={3}
                        placeholder={isSuper ? 'Reply to this ticket…' : 'Add a comment…'}
                        value={newComment}
                        onChange={e => setNewComment(e.target.value)}
                      />
                      {isSuper && (
                        <label className={styles.internalLabel}>
                          <input type="checkbox" checked={isInternal} onChange={e => setIsInternal(e.target.checked)} />
                          Internal note (hidden from society admin)
                        </label>
                      )}
                      <button className={styles.btnPrimary} onClick={submitComment}>
                        Post Comment
                      </button>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
