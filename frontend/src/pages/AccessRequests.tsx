import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  CheckCircle2,
  Eye,
  FilterX,
  KeyRound,
  ShieldCheck,
  Undo2,
  XCircle,
} from 'lucide-react';
import {
  Alert,
  Button,
  Card,
  CardHeader,
  DemoNotice,
  EmptyState,
  Field,
  Modal,
  PageHeader,
  RequestBadge,
  SearchInput,
  StatCard,
  Tabs,
} from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { formatDateTime } from '../lib/format';
import type { AccessRequest } from '../types';

export const AccessRequests = () => {
  const { requests, datasets, role, decideRequest, withdrawRequest, user } = useDemo();
  const [tab, setTab] = useState('incoming');
  const [status, setStatus] = useState('all');
  const [search, setSearch] = useState('');
  const [activeId, setActiveId] = useState<string | null>(null);
  const [note, setNote] = useState('');
  const [error, setError] = useState('');

  const incoming = requests.filter((request) => request.direction === 'Incoming');
  const outgoing = requests.filter((request) => request.direction === 'Outgoing');

  const tabs = [
    { id: 'incoming', label: 'Incoming', count: incoming.filter((request) => request.status === 'Pending').length },
    { id: 'outgoing', label: 'My requests', count: outgoing.filter((request) => request.status === 'Pending').length },
  ];

  const source = tab === 'incoming' ? incoming : outgoing;

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return source
      .filter((request) => {
        if (status !== 'all' && request.status !== status) return false;
        if (!query) return true;
        return [request.id, request.datasetTitle, request.requester, request.organisation, request.projectTitle, request.purpose]
          .join(' ')
          .toLowerCase()
          .includes(query);
      })
      .sort((a, b) => b.requestedAt.localeCompare(a.requestedAt));
  }, [search, source, status, tab]);
  const active = requests.find((request) => request.id === activeId) ?? null;
  const activeDataset = active ? datasets.find((dataset) => dataset.id === active.datasetId) : null;

  const canDecide = (request: AccessRequest) =>
    request.status === 'Pending' && request.direction === 'Incoming' && (role === 'Administrator' || role === 'Researcher' || role === 'Contributor');

  const openRequest = (request: AccessRequest) => {
    setActiveId(request.id);
    setNote('');
    setError('');
  };

  const closeModal = () => {
    setActiveId(null);
    setNote('');
    setError('');
  };

  const handleDecision = (decision: 'Approved' | 'Rejected') => {
    if (!active) return;
    if (decision === 'Rejected' && note.trim().length < 10) {
      setError('Provide a brief reason (at least 10 characters) for rejecting the request.');
      return;
    }
    decideRequest(active.id, decision, note);
    closeModal();
  };

  const pendingIncoming = incoming.filter((request) => request.status === 'Pending').length;
  const pendingOutgoing = outgoing.filter((request) => request.status === 'Pending').length;
  const approved = requests.filter((request) => request.status === 'Approved').length;

  return (
    <>
      <PageHeader
        eyebrow="Governance"
        title="Access requests"
        description="Review controlled and restricted dataset applications, record decisions and keep an auditable rationale."
        actions={
          <Link to="/settings">
            <Button variant="secondary" icon={<ShieldCheck size={16} />}>Demo role: {role}</Button>
          </Link>
        }
      />

      <DemoNotice text="Requests and decisions live only in this browser session. Backend approval workflow, notifications and immutable audit logging arrive in PHASE 11." />

      <div className="stats-grid">
        <StatCard label="Incoming pending" value={pendingIncoming} hint="Awaiting your decision" icon={<KeyRound size={20} />} tone={pendingIncoming > 0 ? 'warning' : 'success'} />
        <StatCard label="My pending requests" value={pendingOutgoing} hint="Outgoing access applications" icon={<ArrowRight size={20} />} tone="info" />
        <StatCard label="Approved" value={approved} hint="Across incoming and outgoing" icon={<CheckCircle2 size={20} />} tone="success" />
        <StatCard label="Decision maker" value={role} hint="Demo role switch is not authentication" icon={<ShieldCheck size={20} />} tone="purple" />
      </div>

      <Alert tone="info" title="Role-aware controls (demo)">
        Incoming requests can be reviewed from this session. Administrators can review governance queues; researchers
        and contributors review requests for datasets they own. Switch the demo role in Settings to inspect the
        different permission states. Real authentication and audit enforcement will be backend responsibilities.
      </Alert>

      <Card>
        <div className="table-toolbar table-toolbar-wrap">
          <Tabs tabs={tabs} active={tab} onChange={(id) => { setTab(id); setStatus('all'); }} />
          <div className="toolbar-filters">
            <SearchInput value={search} onChange={setSearch} placeholder="Search requests…" />
            <select className="input input-sm" value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Filter by request status">
              <option value="all">All statuses</option>
              {['Pending', 'Approved', 'Rejected', 'Withdrawn'].map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            {(search || status !== 'all') ? (
              <button className="icon-btn" onClick={() => { setSearch(''); setStatus('all'); }} title="Clear filters" aria-label="Clear filters">
                <FilterX size={16} />
              </button>
            ) : null}
          </div>
        </div>

        {filtered.length === 0 ? (
          <EmptyState
            title={tab === 'incoming' ? 'No incoming requests' : 'No outgoing requests'}
            description="Access requests for controlled and restricted datasets will appear here with their decision history."
            action={tab === 'outgoing' ? <Link to="/repository"><Button variant="secondary">Browse repository</Button></Link> : undefined}
          />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Request</th>
                  <th>Dataset</th>
                  <th>{tab === 'incoming' ? 'Requester' : 'Reviewer'}</th>
                  <th>Project</th>
                  <th>Requested</th>
                  <th>Status</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((request) => (
                  <tr key={request.id}>
                    <td>
                      <strong className="table-title mono">{request.id}</strong>
                      <span className="table-sub">{request.direction} · {request.role}</span>
                    </td>
                    <td>
                      <Link to={`/datasets/${request.datasetId}`} className="table-title">{request.datasetTitle}</Link>
                      <span className="table-sub">{request.datasetId}</span>
                    </td>
                    <td>
                      <strong className="cell-strong">{tab === 'incoming' ? request.requester : request.reviewer ?? 'Awaiting review'}</strong>
                      <span className="table-sub">{request.organisation}</span>
                    </td>
                    <td className="muted cell-wrap">{request.projectTitle}</td>
                    <td className="muted small">{formatDateTime(request.requestedAt)}</td>
                    <td><RequestBadge status={request.status} /></td>
                    <td>
                      <div className="row-actions">
                        {canDecide(request) ? (
                          <Button size="sm" variant="secondary" onClick={() => openRequest(request)}>Review</Button>
                        ) : (
                          <button className="icon-btn" onClick={() => openRequest(request)} title="View request" aria-label={`View request ${request.id}`}>
                            <Eye size={15} />
                          </button>
                        )}
                        {request.status === 'Pending' && request.direction === 'Outgoing' ? (
                          <button
                            className="icon-btn"
                            title="Withdraw request"
                            aria-label="Withdraw request"
                            onClick={() => withdrawRequest(request.id)}
                          >
                            <Undo2 size={15} />
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="grid-2">
        <Card>
          <CardHeader title="Governance workflow" subtitle="Approval is required before file access" />
          <ol className="pipeline-steps compact-steps">
            <li><span>1</span><div><strong>Request</strong><p>Researcher submits purpose, project and security arrangements.</p></div></li>
            <li><span>2</span><div><strong>Review</strong><p>Dataset owner or administrator checks ethics, consent and data-use terms.</p></div></li>
            <li><span>3</span><div><strong>Decision</strong><p>Approve or reject with a written rationale recorded in the audit log.</p></div></li>
            <li><span>4</span><div><strong>Access</strong><p>Backend issues a scoped, signed download link to the named researcher.</p></div></li>
          </ol>
        </Card>
        <Card>
          <CardHeader title="Decision guidance" subtitle="Consistency matters more than speed" />
          <ul className="bullet-list">
            <li>Confirm that the stated purpose fits the dataset's consent scope.</li>
            <li>Check that ethics approval and data management plans are supplied.</li>
            <li>Verify that the requester's organisation is permitted by the licence.</li>
            <li>Reject requests that lack a secure analysis environment or re-identification controls.</li>
            <li>Record reasons: an unexplained rejection is not acceptable governance.</li>
          </ul>
          <div className="approver-note">
            <ShieldCheck size={16} />
            <span>Decisions are currently stored client-side for demonstration. No audit log is written to a database yet.</span>
          </div>
        </Card>
      </div>

      <Modal
        open={Boolean(active)}
        title={active ? `Access request ${active.id}` : 'Access request'}
        subtitle={active ? `${active.datasetTitle} · ${active.datasetId}` : undefined}
        onClose={closeModal}
        wide
        footer={
          active ? (
            active.status === 'Pending' && canDecide(active) ? (
              <>
                <Button variant="ghost" onClick={closeModal}>Cancel</Button>
                <Button variant="danger" icon={<XCircle size={16} />} onClick={() => handleDecision('Rejected')}>Reject</Button>
                <Button variant="success" icon={<CheckCircle2 size={16} />} onClick={() => handleDecision('Approved')}>Approve</Button>
              </>
            ) : (
              <Button variant="secondary" onClick={closeModal}>Close</Button>
            )
          ) : null
        }
      >
        {active ? (
          <div className="stack-sm">
            <div className="request-summary">
              <div>
                <span>Requester</span>
                <strong>{active.requester}</strong>
                <small>{active.organisation} · {active.role}</small>
              </div>
              <div>
                <span>Access class</span>
                <strong>{activeDataset?.access ?? 'Unknown'}</strong>
                <small>{activeDataset?.license ?? 'Licence not recorded'}</small>
              </div>
              <div>
                <span>Requested</span>
                <strong>{formatDateTime(active.requestedAt)}</strong>
                <small>{active.direction} request</small>
              </div>
              <div>
                <span>Status</span>
                <strong><RequestBadge status={active.status} /></strong>
                <small>{active.decidedAt ? formatDateTime(active.decidedAt) : 'No decision yet'}</small>
              </div>
            </div>

            <Field label="Project title">
              <input className="input" value={active.projectTitle} readOnly />
            </Field>
            <Field label="Purpose and analysis plan">
              <textarea className="input textarea" rows={4} value={active.purpose} readOnly />
            </Field>

            {active.decisionNote ? (
              <Alert tone={active.status === 'Approved' ? 'success' : 'danger'} title={`Decision: ${active.status}`}>
                {active.decisionNote}
                {active.reviewer ? <div className="muted small">Reviewer: {active.reviewer}</div> : null}
              </Alert>
            ) : null}

            {active.status === 'Pending' && canDecide(active) ? (
              <>
                <Field
                  label="Decision rationale"
                  hint="Required for rejection; strongly recommended for approval. This text is what the requester sees."
                  error={error}
                >
                  <textarea
                    className="input textarea"
                    rows={3}
                    value={note}
                    onChange={(event) => {
                      setNote(event.target.value);
                      setError('');
                    }}
                    placeholder="e.g. Approved under the controlled-access agreement; secure environment confirmed."
                  />
                </Field>
                <Alert tone="warning">
                  This decision is browser-only. In the backend implementation it will be transactional and written to
                  an immutable audit log with the reviewer identity.
                </Alert>
              </>
            ) : null}

            {active.status === 'Pending' && active.direction === 'Outgoing' ? (
              <Button variant="ghost" icon={<Undo2 size={15} />} onClick={() => { withdrawRequest(active.id); closeModal(); }}>
                Withdraw this request
              </Button>
            ) : null}

            {activeDataset ? (
              <Link to={`/datasets/${activeDataset.id}`} className="inline-link" onClick={closeModal}>
                Open dataset record <ArrowRight size={13} />
              </Link>
            ) : null}
            <p className="muted small">Signed in as {user.name} · demo role {role}</p>
          </div>
        ) : null}
      </Modal>
    </>
  );
};
