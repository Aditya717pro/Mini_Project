import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Download, FileText, RefreshCw } from 'lucide-react';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  InfoRow,
  LoadingState,
  PageHeader,
  SectionTitle,
  type Tone,
} from '../components/ui';
import { formatBytes, formatDateTime } from '../lib/format';
import { useDemo } from '../store/DemoStore';
import type { ResearchReport, ResearchReportStatus } from '../types';

const STATUS_TONE: Record<ResearchReportStatus, Tone> = {
  Queued: 'warning',
  Generating: 'info',
  Completed: 'success',
  Failed: 'danger',
};

export const ResearchReportDetail = () => {
  const { reportId = '' } = useParams();
  const { getResearchReport, getResearchReportStatus, downloadResearchReport } = useDemo();
  const [report, setReport] = useState<ResearchReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    let timer: number | undefined;
    const load = async () => {
      try {
        const current = await getResearchReport(reportId);
        if (!active) return;
        setReport(current);
        setError('');
        if (current.status === 'Queued' || current.status === 'Generating') {
          const status = await getResearchReportStatus(reportId);
          if (!active) return;
          setReport((previous) =>
            previous
              ? {
                  ...previous,
                  status: status.status,
                  error: status.error,
                  completedAt: status.completedAt,
                }
              : previous,
          );
          timer = window.setTimeout(() => void load(), 1500);
        }
      } catch (loadError) {
        if (active) setError(loadError instanceof Error ? loadError.message : 'Unable to load the research report.');
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => {
      active = false;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [getResearchReport, getResearchReportStatus, reportId]);

  const references = report
    ? [
        ['Dataset ID', report.datasetId],
        ['Dataset version ID', report.datasetVersionId],
        ['Generation job ID', report.generationJobId],
        ['Generated dataset ID', report.generatedDatasetId],
        ['Comparison ID', report.comparisonId],
        ['Privacy evaluation ID', report.privacyEvaluationId],
        ['Utility evaluation ID', report.utilityEvaluationId],
        ['Experiment ID', report.experimentId],
      ].filter((entry): entry is [string, string] => Boolean(entry[1]))
    : [];

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Reporting"
        title={report?.title ?? 'Research report'}
        description="Immutable PDF record with persisted source references and download verification."
        actions={
          <div className="table-actions">
            <Button
              variant="secondary"
              icon={<RefreshCw size={15} />}
              onClick={() => {
                setLoading(true);
                void getResearchReport(reportId)
                  .then((current) => setReport(current))
                  .catch((loadError) =>
                    setError(loadError instanceof Error ? loadError.message : 'Unable to refresh the report.'),
                  )
                  .finally(() => setLoading(false));
              }}
            >
              Refresh
            </Button>
            <Button
              icon={<Download size={15} />}
              disabled={report?.status !== 'Completed'}
              onClick={() => void downloadResearchReport(reportId)}
            >
              Download PDF
            </Button>
          </div>
        }
      />

      {error ? (
        <Alert tone="danger" title="Report unavailable">
          {error}
        </Alert>
      ) : null}

      {loading && !report ? (
        <Card>
          <div className="card-body">
            <LoadingState label="Loading research report…" />
          </div>
        </Card>
      ) : !report ? null : (
        <>
          <div className="grid-2 grid-2-wide">
            <Card>
              <CardHeader title="Report record" subtitle={report.reportId} />
              <div className="card-body detail-list">
                <InfoRow label="Status">
                  <Badge tone={STATUS_TONE[report.status]}>{report.status}</Badge>
                </InfoRow>
                <InfoRow label="Report type"><span className="mono">{report.reportType}</span></InfoRow>
                <InfoRow label="Template version"><span className="mono">v{report.templateVersion}</span></InfoRow>
                <InfoRow label="Owner"><span className="mono">{report.ownerId}</span></InfoRow>
                <InfoRow label="Created">{report.createdAt ? formatDateTime(report.createdAt) : '—'}</InfoRow>
                <InfoRow label="Completed">{report.completedAt ? formatDateTime(report.completedAt) : '—'}</InfoRow>
                {report.error ? (
                  <InfoRow label="Error"><span className="field-error">{report.error}</span></InfoRow>
                ) : null}
              </div>
            </Card>

            <Card>
              <CardHeader title="Integrity" subtitle="Verification applied before PDF download." />
              <div className="card-body detail-list">
                <InfoRow label="SHA-256 checksum"><span className="mono">{report.fileChecksum || '—'}</span></InfoRow>
                <InfoRow label="File size">{report.fileSize ? formatBytes(report.fileSize) : '—'}</InfoRow>
                <InfoRow label="File name"><span className="mono">{report.reportId}.pdf</span></InfoRow>
                <InfoRow label="Storage rule">New immutable file per generation attempt</InfoRow>
              </div>
            </Card>
          </div>

          <Card>
            <CardHeader title="Persisted source references" subtitle="No source data is invented or recreated by the report." />
            <div className="card-body detail-list">
              {references.length === 0 ? (
                <p className="muted">No persisted source references were recorded for this report.</p>
              ) : (
                references.map(([label, value]) => (
                  <InfoRow key={label} label={label}><span className="mono">{value}</span></InfoRow>
                ))
              )}
            </div>
          </Card>

          <Card>
            <CardHeader title="Privacy statement" subtitle="Reporting safeguards applied to the PDF content." />
            <div className="card-body detail-list">
              <SectionTitle>Protected content</SectionTitle>
              <InfoRow label="Patient identifiers">Redacted or omitted from every table and chart</InfoRow>
              <InfoRow label="Categorical values">Not disclosed in dataset distribution tables</InfoRow>
              <InfoRow label="Patient-level rows">Never included in charts, tables, metadata, or filenames</InfoRow>
              <InfoRow label="Unavailable methods">Marked NOT AVAILABLE or NOT EVALUATED</InfoRow>
            </div>
          </Card>
        </>
      )}

      <div className="inline-actions">
        <Link className="btn btn-secondary btn-md" to="/reports">
          <FileText size={15} /> Back to reports
        </Link>
      </div>
    </div>
  );
};
