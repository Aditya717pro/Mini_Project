import { useMemo, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import {
  Activity,
  BookMarked,
  BookOpen,
  Building2,
  Database,
  FlaskConical,
  FolderKanban,
  KeyRound,
  Mail,
  MapPin,
  Package,
  Plus,
  ShieldCheck,
  Smile,
  Star,
  UploadCloud,
  Users,
  Workflow,
} from 'lucide-react';
import { useDemo } from '../store/DemoStore';
import { Badge, Button, Modal } from '../components/ui';
import { formatNumber } from '../lib/format';

// Standard "head and half torso" profile avatar
const StandardUserAvatar = () => (
  <svg
    viewBox="0 0 120 120"
    className="gh-avatar-svg"
    style={{
      width: '100%',
      height: '100%',
      borderRadius: '50%',
      background: 'linear-gradient(135deg, #f5f8fd 0%, #ffffff 100%)',
    }}
    aria-label="User avatar"
  >
    <defs>
      <linearGradient id="avatarGrad" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stopColor="#d7e3f1" />
        <stop offset="100%" stopColor="#0b2545" />
      </linearGradient>
    </defs>
    {/* Head */}
    <circle cx="60" cy="46" r="23" fill="url(#avatarGrad)" />
    {/* Shoulders & Torso */}
    <path
      d="M22,108 C22,86 38,76 60,76 C82,76 98,86 98,108 C98,114 94,116 88,116 L32,116 C26,116 22,114 22,108 Z"
      fill="url(#avatarGrad)"
    />
  </svg>
);

const formatColor = (format: string) => {
  const upper = (format || '').toUpperCase();
  if (upper === 'CSV') return '#0b2545';
  if (upper === 'JSON') return '#123a6b';
  if (upper === 'XLSX') return '#33547d';
  return '#64748b';
};

export const Profile = () => {
  const { user, role, updateProfile, datasets, synthSources, synthGenerated, jobs, requests } = useDemo();

  // Active tab state
  const [activeTab, setActiveTab] = useState<'overview' | 'repositories' | 'projects' | 'packages' | 'stars'>('overview');

  // Profile fields state
  const defaultHandle = user.email ? user.email.split('@')[0] : 'aditya';
  const [name, setName] = useState(user.name || 'Aditya S');
  const [handle, setHandle] = useState(() => localStorage.getItem('app_profile_handle') || defaultHandle);
  const [bio, setBio] = useState(() => localStorage.getItem('app_profile_bio') || 'Healthcare data researcher and bioinformatics analyst.');
  const [location, setLocation] = useState(() => localStorage.getItem('app_profile_location') || 'Erode');
  const [organisation, setOrganisation] = useState(user.organisation || 'VCET');
  const [title, setTitle] = useState(user.title || 'student');
  const [phone, setPhone] = useState(user.phone || '');
  const [statusMessage, setStatusMessage] = useState(() => localStorage.getItem('app_profile_status') || 'Working on MedDataHub & SynthMed');

  // Edit Modal State
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [statusInputOpen, setStatusInputOpen] = useState(false);

  // App repository items (actual datasets from THIS APP)
  const appRepos = useMemo(() => {
    const list: Array<{
      id: string;
      title: string;
      link: string;
      badge: string;
      tone: 'success' | 'purple' | 'info' | 'neutral';
      description: string;
      format: string;
      type: string;
      records: number;
    }> = [];

    // Repository datasets
    datasets.forEach((d) => {
      list.push({
        id: `repo-${d.id}`,
        title: d.title,
        link: `/datasets/${d.id}`,
        badge: d.access,
        tone: d.access === 'Open' ? 'success' : 'purple',
        description: d.description,
        format: d.format,
        type: 'Repository dataset',
        records: d.records,
      });
    });

    // Generated synthetic datasets
    synthGenerated.forEach((g) => {
      list.push({
        id: `synth-${g.id}`,
        title: g.datasetName,
        link: `/synthmed/generated/${g.id}`,
        badge: 'Synthetic',
        tone: 'purple',
        description: `Synthetic cohort generated using CTGAN on ${g.sourceDatasetName}.`,
        format: g.fileFormat,
        type: 'Synthetic cohort',
        records: g.recordCount,
      });
    });

    // Uploaded source datasets
    synthSources.forEach((s) => {
      list.push({
        id: `source-${s.id}`,
        title: s.datasetName,
        link: `/synthmed/upload`,
        badge: 'Source',
        tone: 'info',
        description: s.description || `Original source file: ${s.originalFilename}`,
        format: s.fileFormat,
        type: 'Source dataset',
        records: 0,
      });
    });

    return list;
  }, [datasets, synthGenerated, synthSources]);

  // Pinned items (top 6 actual datasets from the app)
  const pinnedRepos = useMemo(() => appRepos.slice(0, 6), [appRepos]);

  const handleSaveProfile = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await updateProfile({
        fullName: name.trim(),
        phoneNumber: phone.trim(),
        organisation: organisation.trim(),
        title: title.trim(),
      });
      localStorage.setItem('app_profile_handle', handle.trim());
      localStorage.setItem('app_profile_bio', bio.trim());
      localStorage.setItem('app_profile_location', location.trim());
      localStorage.setItem('app_profile_status', statusMessage.trim());
      setIsEditModalOpen(false);
    } catch {
      // notification handled in DemoStore
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="gh-page">
      {/* Sub-navigation Tabs */}
      <nav className="gh-tabs-nav" aria-label="User profile navigation">
        <div className="gh-tabs-inner">
          <button
            type="button"
            className={`gh-tab ${activeTab === 'overview' ? 'gh-tab-active' : ''}`}
            onClick={() => setActiveTab('overview')}
          >
            <BookOpen size={16} />
            <span>Overview</span>
          </button>
          <button
            type="button"
            className={`gh-tab ${activeTab === 'repositories' ? 'gh-tab-active' : ''}`}
            onClick={() => setActiveTab('repositories')}
          >
            <BookMarked size={16} />
            <span>Repositories</span>
            <span className="gh-counter-badge">{appRepos.length}</span>
          </button>
          <button
            type="button"
            className={`gh-tab ${activeTab === 'projects' ? 'gh-tab-active' : ''}`}
            onClick={() => setActiveTab('projects')}
          >
            <FolderKanban size={16} />
            <span>Projects</span>
          </button>
          <button
            type="button"
            className={`gh-tab ${activeTab === 'packages' ? 'gh-tab-active' : ''}`}
            onClick={() => setActiveTab('packages')}
          >
            <Package size={16} />
            <span>Packages</span>
          </button>
          <button
            type="button"
            className={`gh-tab ${activeTab === 'stars' ? 'gh-tab-active' : ''}`}
            onClick={() => setActiveTab('stars')}
          >
            <Star size={16} />
            <span>Stars</span>
            <span className="gh-counter-badge">0</span>
          </button>
        </div>
      </nav>

      <div className="gh-profile-container">
        {/* Left Column: Profile Sidebar */}
        <aside className="gh-profile-sidebar">
          <div className="gh-avatar-wrapper">
            <div className="gh-avatar-circle">
              <StandardUserAvatar />
            </div>
            {/* Status badge trigger */}
            <button
              type="button"
              className="gh-status-badge"
              title={statusMessage || 'Set status'}
              onClick={() => setStatusInputOpen(!statusInputOpen)}
              aria-label="Set status"
            >
              <Smile size={16} />
            </button>
          </div>

          {statusInputOpen && (
            <div className="gh-status-popup">
              <input
                type="text"
                className="gh-input gh-input-sm"
                value={statusMessage}
                onChange={(e) => setStatusMessage(e.target.value)}
                placeholder="What's happening?"
              />
              <button
                type="button"
                className="gh-btn gh-btn-sm"
                onClick={() => {
                  localStorage.setItem('app_profile_status', statusMessage);
                  setStatusInputOpen(false);
                }}
              >
                Set status
              </button>
            </div>
          )}

          {/* User Names */}
          <div className="gh-names-block">
            <h1 className="gh-full-name">{name || 'Aditya S'}</h1>
            <p className="gh-user-handle">@{handle || defaultHandle}</p>
          </div>

          {bio ? <p className="gh-bio">{bio}</p> : null}

          {/* Edit Profile Button */}
          <button
            type="button"
            className="gh-btn gh-btn-edit-profile"
            onClick={() => setIsEditModalOpen(true)}
          >
            Edit profile
          </button>

          {/* Follower Stats */}
          <div className="gh-followers-line">
            <Users size={16} className="gh-meta-icon" />
            <span className="gh-follow-stat"><strong>15</strong> followers</span>
            <span className="gh-dot-sep">·</span>
            <span className="gh-follow-stat"><strong>12</strong> following</span>
          </div>

          {/* User Meta Information (Clean app metadata, NO GitHub URLs) */}
          <div className="gh-meta-list">
            {organisation ? (
              <div className="gh-meta-item">
                <Building2 size={16} className="gh-meta-icon" />
                <span>{organisation}</span>
              </div>
            ) : null}

            {location ? (
              <div className="gh-meta-item">
                <MapPin size={16} className="gh-meta-icon" />
                <span>{location}</span>
              </div>
            ) : null}

            {user.email ? (
              <div className="gh-meta-item">
                <Mail size={16} className="gh-meta-icon" />
                <a href={`mailto:${user.email}`} className="gh-link">{user.email}</a>
              </div>
            ) : null}

            <div className="gh-meta-item">
              <ShieldCheck size={16} className="gh-meta-icon" />
              <span>Role: <strong style={{ color: 'var(--text)' }}>{role}</strong> ({title || 'Researcher'})</span>
            </div>

            <div className="gh-meta-item">
              <Database size={16} className="gh-meta-icon" />
              <span>{appRepos.length} datasets accessible</span>
            </div>
          </div>
        </aside>

        {/* Right Column: Main Content */}
        <main className="gh-profile-main">
          {activeTab === 'overview' && (
            <>
              {/* Repositories from THIS APP (Popular repositories section) */}
              <section className="gh-section">
                <div className="gh-section-header">
                  <h2 className="gh-section-title">Repositories &amp; Datasets</h2>
                  <button
                    type="button"
                    className="gh-link-action"
                    onClick={() => setActiveTab('repositories')}
                  >
                    View all ({appRepos.length})
                  </button>
                </div>

                {pinnedRepos.length === 0 ? (
                  <div className="gh-empty-tab">
                    <Database size={36} className="muted" />
                    <h3>No datasets uploaded yet</h3>
                    <p className="muted">Upload your first source dataset or intake research data.</p>
                    <Link to="/synthmed/upload">
                      <Button variant="primary" size="sm" icon={<UploadCloud size={14} />}>
                        Upload source dataset
                      </Button>
                    </Link>
                  </div>
                ) : (
                  <div className="gh-pinned-grid">
                    {pinnedRepos.map((repo) => (
                      <div key={repo.id} className="gh-pinned-card">
                        <div>
                          <div className="gh-card-header">
                            <Link to={repo.link} className="gh-repo-name">
                              {repo.title}
                            </Link>
                            <Badge tone={repo.tone}>
                              {repo.badge}
                            </Badge>
                          </div>

                          <p className="gh-repo-description">
                            {repo.description || 'No description provided.'}
                          </p>
                        </div>

                        <div className="gh-repo-footer">
                          <span className="gh-repo-language">
                            <span
                              className="gh-lang-dot"
                              style={{ backgroundColor: formatColor(repo.format) }}
                            />
                            <span>{repo.format || 'CSV'}</span>
                          </span>
                          {repo.records > 0 ? (
                            <span className="muted small">{formatNumber(repo.records)} records</span>
                          ) : (
                            <span className="muted small">{repo.type}</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>

              {/* Recent Platform Activity Timeline (Heatmap plot completely removed) */}
              <section className="gh-section">
                <div className="gh-section-header">
                  <h2 className="gh-section-title">Recent Activity</h2>
                </div>

                <div className="gh-activity-timeline" style={{ marginTop: 0 }}>
                  <div className="gh-timeline-month">
                    <div className="gh-timeline-header">
                      <span className="gh-month-badge">November 2026</span>
                      <span className="gh-timeline-line" />
                    </div>

                    <ul className="gh-activity-list">
                      {synthGenerated.length > 0 && (
                        <li className="gh-activity-item">
                          <FlaskConical size={16} className="gh-activity-icon" />
                          <div>
                            <strong>Generated {synthGenerated.length} synthetic dataset(s)</strong>
                            <div className="gh-activity-repos">
                              {synthGenerated.map((g) => g.datasetName).join(', ')}
                            </div>
                          </div>
                        </li>
                      )}

                      {synthSources.length > 0 && (
                        <li className="gh-activity-item">
                          <UploadCloud size={16} className="gh-activity-icon" />
                          <div>
                            <strong>Uploaded {synthSources.length} source file(s)</strong>
                            <div className="gh-activity-repos">
                              {synthSources.map((s) => s.datasetName).join(', ')}
                            </div>
                          </div>
                        </li>
                      )}

                      {jobs.length > 0 && (
                        <li className="gh-activity-item">
                          <Workflow size={16} className="gh-activity-icon" />
                          <div>
                            <strong>Processed {jobs.length} ETL pipeline jobs</strong>
                            <span className="muted small"> · Verified schema and data profiles</span>
                          </div>
                        </li>
                      )}

                      {requests.length > 0 && (
                        <li className="gh-activity-item">
                          <KeyRound size={16} className="gh-activity-icon" />
                          <div>
                            <strong>{requests.length} access request(s) recorded</strong>
                          </div>
                        </li>
                      )}

                      <li className="gh-activity-item">
                        <Activity size={16} className="gh-activity-icon" />
                        <div>
                          <strong>{datasets.length} research dataset(s) active in repository</strong>
                        </div>
                      </li>
                    </ul>
                  </div>
                </div>
              </section>
            </>
          )}

          {activeTab === 'repositories' && (
            <section className="gh-section">
              <div className="gh-section-header">
                <h2 className="gh-section-title">Repositories &amp; Datasets ({appRepos.length})</h2>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <Link to="/synthmed/upload">
                    <Button variant="secondary" size="sm" icon={<UploadCloud size={14} />}>
                      Upload source
                    </Button>
                  </Link>
                  <Link to="/upload">
                    <Button variant="primary" size="sm" icon={<Plus size={14} />}>
                      Intake dataset
                    </Button>
                  </Link>
                </div>
              </div>

              <div className="gh-repos-list">
                {appRepos.length === 0 ? (
                  <div className="gh-empty-tab">
                    <Database size={36} className="muted" />
                    <h3>No datasets available</h3>
                    <p className="muted">Upload or intake datasets to view them in your repository list.</p>
                  </div>
                ) : (
                  appRepos.map((repo) => (
                    <div key={repo.id} className="gh-repo-row">
                      <div className="gh-repo-main">
                        <div className="gh-card-header">
                          <Link to={repo.link} className="gh-repo-name">
                            {repo.title}
                          </Link>
                          <Badge tone={repo.tone}>
                            {repo.badge}
                          </Badge>
                        </div>
                        <p className="gh-repo-description">
                          {repo.description || 'No description provided.'}
                        </p>
                        <div className="gh-repo-footer">
                          <span className="gh-repo-language">
                            <span
                              className="gh-lang-dot"
                              style={{ backgroundColor: formatColor(repo.format) }}
                            />
                            <span>{repo.format || 'CSV'}</span>
                          </span>
                          {repo.records > 0 ? (
                            <span className="muted small">{formatNumber(repo.records)} records</span>
                          ) : (
                            <span className="muted small">{repo.type}</span>
                          )}
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </section>
          )}

          {activeTab === 'projects' && (
            <div className="gh-empty-tab">
              <FolderKanban size={36} className="muted" />
              <h3>Research Projects</h3>
              <p className="muted">Organize and manage clinical research cohorts, models, and data governance boards.</p>
            </div>
          )}

          {activeTab === 'packages' && (
            <div className="gh-empty-tab">
              <Package size={36} className="muted" />
              <h3>Synthetic Models &amp; Packages</h3>
              <p className="muted">SDV CTGAN, TVAE and GaussianCopula model configurations trained on your datasets.</p>
            </div>
          )}

          {activeTab === 'stars' && (
            <div className="gh-empty-tab">
              <Star size={36} className="muted" />
              <h3>Starred Datasets</h3>
              <p className="muted">Bookmark frequently accessed healthcare datasets and pipelines.</p>
            </div>
          )}
        </main>
      </div>

      {/* Edit Profile Modal (NO GitHub URLs) */}
      <Modal
        open={isEditModalOpen}
        title="Edit profile"
        subtitle="Update your profile details across MedDataHub"
        onClose={() => setIsEditModalOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsEditModalOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" disabled={saving} onClick={handleSaveProfile}>
              {saving ? 'Saving…' : 'Save profile'}
            </Button>
          </>
        }
      >
        <form onSubmit={handleSaveProfile} className="form-grid">
          <div className="field">
            <label className="field-label" htmlFor="edit-name">Full name</label>
            <input
              id="edit-name"
              className="input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Aditya S"
              required
            />
          </div>

          <div className="field">
            <label className="field-label" htmlFor="edit-handle">Username / Handle</label>
            <input
              id="edit-handle"
              className="input"
              value={handle}
              onChange={(e) => setHandle(e.target.value)}
              placeholder="e.g. aditya"
            />
          </div>

          <div className="field">
            <label className="field-label" htmlFor="edit-bio">Bio</label>
            <textarea
              id="edit-bio"
              className="textarea"
              rows={3}
              value={bio}
              onChange={(e) => setBio(e.target.value)}
              placeholder="Tell others about your research interests"
            />
          </div>

          <div className="field">
            <label className="field-label" htmlFor="edit-location">Location</label>
            <input
              id="edit-location"
              className="input"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="e.g. Erode"
            />
          </div>

          <div className="field">
            <label className="field-label" htmlFor="edit-org">Organisation</label>
            <input
              id="edit-org"
              className="input"
              value={organisation}
              onChange={(e) => setOrganisation(e.target.value)}
              placeholder="e.g. VCET"
            />
          </div>

          <div className="field">
            <label className="field-label" htmlFor="edit-title">Job title / designation</label>
            <input
              id="edit-title"
              className="input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Student / Researcher"
            />
          </div>

          <div className="field">
            <label className="field-label" htmlFor="edit-phone">Phone number</label>
            <input
              id="edit-phone"
              className="input"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+91..."
            />
          </div>
        </form>
      </Modal>
    </div>
  );
};
