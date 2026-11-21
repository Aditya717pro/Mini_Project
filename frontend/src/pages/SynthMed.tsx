import { Link } from 'react-router-dom';
import {
  FlaskConical,
  GitCompare,
  ShieldCheck,
  UploadCloud,
  Wand2,
} from 'lucide-react';
import { Alert, Button, Card, CardHeader, PageHeader, StatCard } from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { formatNumber } from '../lib/format';

export const SynthMed = () => {
  const { synthSources, synthGenerated } = useDemo();
  const totalRecords = synthGenerated.reduce((sum, dataset) => sum + dataset.recordCount, 0);

  return (
    <>
      <PageHeader
        eyebrow="Synthetic data"
        title="SynthMed Dashboard"
        description="A separate module for uploading authorised source data, managing synthetic datasets and downloading governed outputs."
        actions={
          <Link to="/synthmed/upload">
            <Button icon={<UploadCloud size={16} />}>Upload source dataset</Button>
          </Link>
        }
      />

      <div className="stats-grid">
        <StatCard
          label="Source datasets"
          value={formatNumber(synthSources.length)}
          hint="Uploaded by your account"
          icon={<UploadCloud size={20} />}
          tone="info"
        />
        <StatCard
          label="Generated datasets"
          value={formatNumber(synthGenerated.length)}
          hint="Stored separately from sources"
          icon={<FlaskConical size={20} />}
          tone="success"
        />
        <StatCard
          label="Synthetic records"
          value={formatNumber(totalRecords)}
          hint="Across generated datasets"
          icon={<Wand2 size={20} />}
          tone="purple"
        />
        <StatCard
          label="Evaluations"
          value={formatNumber(synthGenerated.length)}
          hint="Quality & privacy reports available"
          icon={<ShieldCheck size={20} />}
          tone="purple"
        />
      </div>

      <div className="grid-2">
        <Card>
          <CardHeader title="SynthMed workflow" subtitle="Module navigation" />
          <ul className="activity-list">
            <li>
              <span className="activity-icon activity-upload"><UploadCloud size={15} /></span>
              <div>
                <Link to="/synthmed/upload"><strong>Upload Source Dataset</strong></Link>
                <span>CSV, XLSX or JSON with server-side validation and exact original storage.</span>
              </div>
            </li>
            <li>
              <span className="activity-icon activity-processing"><Wand2 size={15} /></span>
              <div>
                <Link to="/synthmed/generate"><strong>Generate Synthetic Data</strong></Link>
                 <span>Train a real SDV CTGAN model with configurable epochs, batch size, seed and column controls.</span>

              </div>
            </li>
            <li>
              <span className="activity-icon activity-quality"><GitCompare size={15} /></span>
              <div>
                <Link to="/synthmed/comparison"><strong>Original vs Synthetic Comparison</strong></Link>
                <span>Compare shared columns with real distribution distances, category frequencies and saved history.</span>
              </div>
            </li>
            <li>
              <span className="activity-icon activity-quality"><ShieldCheck size={15} /></span>
              <div>
                <Link to="/synthmed/evaluation"><strong>Quality &amp; Privacy Evaluation</strong></Link>
                  <span>Review SDMetrics quality scores and privacy-risk screening with explicit limitations.</span>

              </div>
            </li>

            <li>
              <span className="activity-icon activity-publish"><FlaskConical size={15} /></span>
              <div>
                <Link to="/synthmed/generated"><strong>Generated Datasets</strong></Link>
                <span>View and download synthetic datasets with full quality and privacy evaluation reports.</span>
              </div>
            </li>
          </ul>
        </Card>
        <Card>
          <CardHeader title="Governance notice" subtitle="Authorised use only" />
          <p className="muted">
            Only upload and process source data you are authorised to use. Do not upload identifiable patient
            information without appropriate authorisation and safeguards. Synthetic outputs must not be treated as
            clinically validated or inherently anonymous.
          </p>
          <Alert tone="warning" title="Source files are immutable">
            SynthMed never deletes or overwrites an uploaded original when generating synthetic data.
          </Alert>
          <Link to="/synthmed/generated">
            <Button variant="ghost">Open Generated Datasets</Button>
          </Link>
        </Card>
      </div>
    </>
  );
};
