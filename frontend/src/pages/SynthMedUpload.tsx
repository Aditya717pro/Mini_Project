import { useCallback, useEffect, useRef, useState, type ChangeEvent, type DragEvent, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import {
  CheckCircle2,
  FileJson,
  FileSpreadsheet,
  FileText,
  FlaskConical,
  UploadCloud,
  Wand2,
  X,
} from 'lucide-react';
import { Alert, Badge, Button, Card, CardHeader, Field, PageHeader, ProgressBar } from '../components/ui';
import { useDemo } from '../store/DemoStore';
import { extractFile, MAX_FILE_BYTES, UploadValidationError } from '../lib/extract';
import { formatBytes, formatDateTime, formatNumber } from '../lib/format';
import type { FileFormat, SynthMedSourceDataset } from '../types';

const ACCEPTED_EXTENSIONS = ['.csv', '.xlsx', '.json'];

const extensionToFormat = (filename: string): FileFormat | null => {
  const extension = filename.toLowerCase().slice(filename.lastIndexOf('.'));
  if (extension === '.csv') return 'CSV';
  if (extension === '.xlsx') return 'XLSX';
  if (extension === '.json') return 'JSON';
  return null;
};

const formatIcon = (format: FileFormat) => {
  if (format === 'CSV') return <FileText size={22} />;
  if (format === 'JSON') return <FileJson size={22} />;
  return <FileSpreadsheet size={22} />;
};

export const SynthMedUpload = () => {
  const { uploadSynthMedSource, getSynthMedSource, notify, user } = useDemo();
  const inputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [format, setFormat] = useState<FileFormat | null>(null);
  const [datasetName, setDatasetName] = useState('');
  const [description, setDescription] = useState('');
  const [localChecksum, setLocalChecksum] = useState('');
  const [rowCount, setRowCount] = useState(0);
  const [dragOver, setDragOver] = useState(false);
  const [fileError, setFileError] = useState('');
  const [nameError, setNameError] = useState('');
  const [uploadError, setUploadError] = useState('');
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [created, setCreated] = useState<SynthMedSourceDataset | null>(null);

  useEffect(() => {
    return () => {
      if (inputRef.current) inputRef.current.value = '';
    };
  }, []);

  const handleFile = useCallback(
    async (candidate: File) => {
      setFileError('');
      setUploadError('');
      setCreated(null);
      setFile(candidate);
      setFormat(extensionToFormat(candidate.name));
      setLocalChecksum('');
      setRowCount(0);

      try {
        const result = await extractFile(candidate);
        setFormat(result.format);
        setLocalChecksum(result.checksum);
        setRowCount(result.preview.rowCount);
        setDatasetName((previous) => previous || candidate.name.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' '));
        notify('success', 'File checked locally', `${candidate.name} is ready for server validation.`);
      } catch (error) {
        const message =
          error instanceof UploadValidationError
            ? error.message
            : 'The file could not be read. Check that it is not corrupt or password protected.';
        setFileError(message);
        setFile(null);
        setFormat(null);
        notify('error', 'File rejected', message);
      }
    },
    [notify],
  );

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragOver(false);
    const dropped = event.dataTransfer.files?.[0];
    if (dropped) void handleFile(dropped);
  };

  const onInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    const selected = event.target.files?.[0];
    if (selected) void handleFile(selected);
    event.target.value = '';
  };

  const clearFile = () => {
    setFile(null);
    setFormat(null);
    setLocalChecksum('');
    setRowCount(0);
    setFileError('');
    setUploadError('');
    setCreated(null);
    setProgress(0);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setUploadError('');
    if (!file || !format || fileError) {
      setUploadError('Choose a valid CSV, XLSX or JSON file before uploading.');
      return;
    }
    if (datasetName.trim().length < 3) {
      setNameError('Enter a dataset name of at least 3 characters.');
      return;
    }
    setNameError('');

    setUploading(true);
    setProgress(0);
    try {
      const id = await uploadSynthMedSource(
        { file, datasetName: datasetName.trim(), description: description.trim() },
        setProgress,
      );
      const dataset = await getSynthMedSource(id);
      setCreated(dataset);
      notify(
        'success',
        'Source dataset uploaded',
        `${dataset.datasetName} was stored without modification and its metadata saved.`,
      );
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : 'The upload could not be completed.');
    } finally {
      setUploading(false);
      setProgress(0);
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="Synthetic data"
        title="Upload source dataset"
        description="Upload an authorised source file to SynthMed. The original bytes are preserved exactly and validated independently by the server."
        actions={
          <Link to="/synthmed/generated">
            <Button variant="secondary" icon={<FlaskConical size={16} />}>Generated datasets</Button>
          </Link>
        }
      />

      <Alert tone="warning" title="Synthetic or authorised data only">
        Do not upload identifiable patient information unless you have explicit authorisation and safeguards in place.
      </Alert>

      {created ? (
        <Card className="success-panel">
          <CardHeader
            title={
              <span className="success-title">
                <CheckCircle2 size={19} /> Upload complete
              </span>
            }
            subtitle="The source file is stored separately from generated synthetic datasets."
            action={
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <Link to={`/synthmed/generate?sourceId=${encodeURIComponent(created.id)}`}>
                  <Button icon={<Wand2 size={14} />}>Generate</Button>
                </Link>
                <Link to="/synthmed/generated">
                  <Button variant="secondary" size="sm" icon={<FlaskConical size={14} />}>
                    Generated datasets
                  </Button>
                </Link>
              </div>
            }
          />
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px', padding: '14px 16px', background: 'var(--surface-2)', borderRadius: '8px', margin: '14px 0' }}>
            <div>
              <strong style={{ fontSize: '14px', display: 'block' }}>Ready to generate synthetic data</strong>
              <span style={{ fontSize: '12px', color: 'var(--text-2)' }}>Proceed to model selection, column conditioning, and training with this dataset.</span>
            </div>
            <Link to={`/synthmed/generate?sourceId=${encodeURIComponent(created.id)}`}>
              <Button icon={<Wand2 size={15} />}>
                Generate
              </Button>
            </Link>
          </div>
          <div className="table-wrap">
            <table className="table table-compact">
              <thead>
                <tr>
                  <th>Field</th>
                  <th>Value</th>
                </tr>
              </thead>
              <tbody>
                <tr><td>Dataset ID</td><td><code className="code">{created.id}</code></td></tr>
                <tr><td>Dataset name</td><td>{created.datasetName}</td></tr>
                <tr><td>Original filename</td><td>{created.originalFilename}</td></tr>
                <tr><td>File format</td><td><Badge tone="info">{created.fileFormat}</Badge></td></tr>
                <tr><td>File size</td><td>{formatBytes(created.fileSizeBytes)}</td></tr>
                <tr><td>Upload date and time</td><td>{formatDateTime(created.uploadDate)}</td></tr>
                <tr><td>Uploaded by</td><td>{created.uploadedBy}</td></tr>
                <tr><td>Upload status</td><td><Badge tone="success">{created.uploadStatus}</Badge></td></tr>
                <tr><td>SHA-256 checksum</td><td><code className="code small">{created.checksumSha256}</code></td></tr>
              </tbody>
            </table>
          </div>
          {localChecksum && localChecksum !== created.checksumSha256 ? (
            <p className="muted">Browser and server checksums differ; the server-stored checksum is authoritative.</p>
          ) : null}
        </Card>
      ) : null}

      <form className="upload-layout" onSubmit={(event) => void submit(event)}>
        <div className="upload-main">
          <Card>
            <CardHeader title="1. Choose a source file" subtitle="CSV, XLSX or JSON · maximum 25 MB" />
            <input ref={inputRef} type="file" accept={ACCEPTED_EXTENSIONS.join(',')} onChange={onInputChange} hidden />
            {file ? (
              <div className="file-card">
                <div className="file-icon">{format ? formatIcon(format) : <FileText size={22} />}</div>
                <div className="file-meta">
                  <strong>{file.name}</strong>
                  <span>{formatBytes(file.size)} · {format ?? 'Unknown format'} · selected</span>
                  {localChecksum ? <code className="code small">SHA-256 {localChecksum}</code> : null}
                  {rowCount > 0 ? <span>{formatNumber(rowCount)} rows read locally</span> : null}
                </div>
                <button type="button" className="icon-btn" onClick={clearFile} aria-label="Remove selected file">
                  <X size={16} />
                </button>
              </div>
            ) : (
              <div
                className={`dropzone ${dragOver ? 'dropzone-active' : ''} ${fileError ? 'dropzone-error' : ''}`}
                onDragOver={(event) => {
                  event.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={onDrop}
                onClick={() => inputRef.current?.click()}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    inputRef.current?.click();
                  }
                }}
                role="button"
                tabIndex={0}
                aria-label="Choose a source dataset file"
              >
                <UploadCloud size={30} />
                <strong>Drag and drop your file here</strong>
                <span>or click to browse files</span>
                <Button type="button" variant="secondary" size="sm" onClick={() => inputRef.current?.click()}>
                  Browse Files
                </Button>
              </div>
            )}
            {fileError ? <Alert tone="danger" title="File not accepted">{fileError}</Alert> : null}
            {uploadError ? <Alert tone="danger" title="Upload failed">{uploadError}</Alert> : null}
          </Card>

          <Card>
            <CardHeader title="2. Describe the dataset" subtitle="The name is shown across generated datasets and pipelines." />
            <Field label="Dataset name" htmlFor="synthmed-dataset-name" required error={nameError}>
              <input
                id="synthmed-dataset-name"
                className="input"
                value={datasetName}
                onChange={(event) => {
                  setDatasetName(event.target.value);
                  setNameError('');
                }}
                placeholder="e.g. Synthetic antenatal cohort"
                maxLength={250}
              />
            </Field>
            <Field label="Description" htmlFor="synthmed-description" hint="Optional context for future reviewers.">
              <textarea
                id="synthmed-description"
                className="textarea"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Describe the source and intended synthetic data use"
                rows={3}
              />
            </Field>
          </Card>

          {uploading ? (
            <Card>
              <CardHeader title="Uploading" subtitle="Sending the original file to the SynthMed API." />
              <ProgressBar value={progress} tone="info" />
              <p className="muted">{progress}% transferred</p>
            </Card>
          ) : null}
        </div>

        <aside className="upload-side">
          <Card>
            <CardHeader
              title={created ? 'Next step' : 'Upload controls'}
              subtitle={created ? 'Ready for generation' : 'Server-verified'}
            />
            {created ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <Link to={`/synthmed/generate?sourceId=${encodeURIComponent(created.id)}`}>
                  <Button style={{ width: '100%' }} icon={<Wand2 size={16} />}>
                    Generate
                  </Button>
                </Link>
                <Button variant="secondary" style={{ width: '100%' }} onClick={clearFile}>
                  Upload another file
                </Button>
              </div>
            ) : (
              <Button type="submit" disabled={uploading || !file || Boolean(fileError)} icon={<UploadCloud size={16} />}>
                {uploading ? 'Uploading…' : 'Upload source dataset'}
              </Button>
            )}
            <p className="muted">
              Signed in as {user.name}. Uploaded files are private to your account unless an administrator accesses them.
            </p>
          </Card>
          <Card>
            <CardHeader title="What happens next" subtitle="Original file stays untouched" />
            <ul className="checklist">
              <li>Extension, MIME type, size and content are validated on the backend.</li>
              <li>The exact uploaded bytes are written to sources storage.</li>
              <li>Metadata, including SHA-256 checksum, is saved in the database.</li>
              <li>The file is saved securely and ready to train synthetic models.</li>
            </ul>
          </Card>
          <Card>
            <CardHeader title="Limits" subtitle="Client and server agree" />
            <p className="muted">Accepted formats: CSV, XLSX, JSON. Maximum size: {formatBytes(MAX_FILE_BYTES)}.</p>
          </Card>
        </aside>
      </form>
    </>
  );
};
