import { Suspense, useState, type FormEvent } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  Activity,
  BadgeCheck,
  Bell,
  BrainCircuit,
  Database,
  FolderOpen,
  KeyRound,
  LayoutDashboard,
  Menu,
  Search,
  Settings,
  UploadCloud,
  Users,
  Workflow,
  X,
} from 'lucide-react';
import { useDemo } from '../store/DemoStore';
import { formatNumber, initials } from '../lib/format';
import { LoadingState, ToastViewport } from '../components/ui';

const navGroups = [
  {
    label: 'Overview',
    items: [{ to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true }],
  },
  {
    label: 'Data',
    items: [
      { to: '/upload', label: 'Upload Dataset', icon: UploadCloud, end: false },
      { to: '/datasets', label: 'My Datasets', icon: FolderOpen, end: false },
      { to: '/repository', label: 'Dataset Repository', icon: Database, end: false },
    ],
  },
  {
    label: 'Assessment',
    items: [
      { to: '/etl', label: 'ETL Processing', icon: Workflow, end: false },
      { to: '/quality', label: 'Data Quality', icon: BadgeCheck, end: false },
      { to: '/readiness', label: 'AI Readiness', icon: BrainCircuit, end: false },
      { to: '/representativeness', label: 'Representativeness', icon: Users, end: false },
    ],
  },
  {
    label: 'Governance',
    items: [
      { to: '/access-requests', label: 'Access Requests', icon: KeyRound, end: false },
      { to: '/settings', label: 'Settings', icon: Settings, end: false },
    ],
  },
];

export const AppLayout = () => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [search, setSearch] = useState('');
  const { user, role, requests, jobs, datasets } = useDemo();
  const navigate = useNavigate();
  const location = useLocation();

  const pendingIncoming = requests.filter((request) => request.direction === 'Incoming' && request.status === 'Pending').length;
  const activeJobs = jobs.filter((job) => job.status === 'Running' || job.status === 'Queued').length;
  const badgeFor = (to: string) => {
    if (to === '/access-requests') return pendingIncoming;
    if (to === '/etl') return activeJobs;
    return 0;
  };

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    navigate(search.trim() ? `/repository?q=${encodeURIComponent(search.trim())}` : '/repository');
    setSearch('');
  };

  const currentTitle = location.pathname.startsWith('/datasets/')
    ? 'Dataset Details'
    : [...navGroups.flatMap((group) => group.items)].find((item) =>
        item.end ? location.pathname === item.to : location.pathname.startsWith(item.to),
      )?.label ?? 'MedDataHub';

  return (
    <div className="app-shell">
      <div
        className={`sidebar-overlay ${sidebarOpen ? 'visible' : ''}`}
        onClick={() => setSidebarOpen(false)}
        aria-hidden="true"
      />
      <aside className={`sidebar ${sidebarOpen ? 'sidebar-open' : ''}`}>
        <div className="brand">
          <div className="brand-mark">
            <Activity size={22} />
          </div>
          <div>
            <div className="brand-name">MedDataHub</div>
            <div className="brand-sub">Research Data Platform</div>
          </div>
          <button className="icon-btn sidebar-close" onClick={() => setSidebarOpen(false)} aria-label="Close navigation">
            <X size={18} />
          </button>
        </div>

        <nav className="nav">
          {navGroups.map((group) => (
            <div className="nav-group" key={group.label}>
              <div className="nav-label">{group.label}</div>
              {group.items.map((item) => {
                const Icon = item.icon;
                const count = badgeFor(item.to);
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.end}
                    className={({ isActive }) => `nav-item ${isActive ? 'nav-item-active' : ''}`}
                    onClick={() => setSidebarOpen(false)}
                  >
                    <Icon size={18} />
                    <span>{item.label}</span>
                    {count > 0 ? <span className="nav-badge">{count}</span> : null}
                  </NavLink>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="demo-strip">
            <span className="demo-dot" />
            Demo environment · synthetic data
          </div>
          <NavLink to="/settings" className="sidebar-user">
            <div className="avatar">{initials(user.name)}</div>
            <div className="sidebar-user-text">
              <strong>{user.name}</strong>
              <span>{role}</span>
            </div>
            <Settings size={15} />
          </NavLink>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <button className="icon-btn menu-btn" onClick={() => setSidebarOpen(true)} aria-label="Open navigation">
            <Menu size={20} />
          </button>
          <span className="topbar-title">{currentTitle}</span>

          <form className="topbar-search" onSubmit={submitSearch} role="search">
            <Search size={16} />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search datasets, domains, tags…"
              aria-label="Search the dataset repository"
            />
            <kbd>↵</kbd>
          </form>

          <div className="topbar-right">
            <span className="topbar-stat" title="Datasets visible to you">
              <Database size={14} />
              {formatNumber(datasets.length)} datasets
            </span>
            <button className="icon-btn bell" onClick={() => navigate('/access-requests')} aria-label="Pending access requests">
              <Bell size={18} />
              {pendingIncoming > 0 ? <span className="bell-dot">{pendingIncoming}</span> : null}
            </button>
            <NavLink to="/settings" className="user-chip">
              <div className="avatar avatar-sm">{initials(user.name)}</div>
              <div className="user-chip-text">
                <strong>{user.name.replace(/^(Dr\.|Prof\.)\s/, '')}</strong>
                <span>{role}</span>
              </div>
            </NavLink>
          </div>
        </header>

        <main className="page">
          <Suspense
            fallback={
              <div className="page-loading">
                <LoadingState label="Loading view…" />
              </div>
            }
          >
            <Outlet />
          </Suspense>
        </main>
      </div>
      <ToastViewport />
    </div>
  );
};
