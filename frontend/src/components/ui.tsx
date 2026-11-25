import {
  useEffect,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type ReactNode,
} from 'react';
import {
  AlertTriangle,
  Beaker,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Globe,
  Info,
  Loader2,
  Lock,
  Search,
  X,
  XCircle,
} from 'lucide-react';
import type { AccessLevel, DatasetStatus, RequestStatus } from '../types';
import { DEMO_NOTICE } from '../data/mockData';
import { useDemo } from '../store/DemoStore';

export type Tone = 'neutral' | 'success' | 'info' | 'warning' | 'danger' | 'purple';

const cx = (...classes: (string | false | null | undefined)[]) =>
  classes.filter(Boolean).join(' ');

/* ---------------------------------- Button --------------------------------- */

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'success';
  size?: 'sm' | 'md';
  icon?: ReactNode;
}

export const Button = ({
  variant = 'primary',
  size = 'md',
  icon,
  className,
  children,
  ...rest
}: ButtonProps) => (
  <button className={cx('btn', `btn-${variant}`, `btn-${size}`, className)} {...rest}>
    {icon}
    {children}
  </button>
);

/* ----------------------------------- Card ---------------------------------- */

export const Card = ({
  children,
  className,
  style,
  id,
  ...rest
}: HTMLAttributes<HTMLElement> & {
  children: ReactNode;
}) => <section className={cx('card', className)} style={style} id={id} {...rest}>{children}</section>;

export const CardHeader = ({
  title,
  subtitle,
  action,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
}) => (
  <div className="card-header">
    <div>
      <h2 className="card-title">{title}</h2>
      {subtitle ? <p className="card-subtitle">{subtitle}</p> : null}
    </div>
    {action ? <div className="card-action">{action}</div> : null}
  </div>
);

/* ---------------------------------- Badges --------------------------------- */

export const Badge = ({
  children,
  tone = 'neutral',
  title,
}: {
  children: ReactNode;
  tone?: Tone;
  title?: string;
}) => (
  <span className={cx('badge', `badge-${tone}`)} title={title}>
    {children}
  </span>
);

const statusTone: Record<DatasetStatus, Tone> = {
  Available: 'success',
  Processing: 'info',
  'Pending review': 'warning',
  'Changes requested': 'warning',
  Failed: 'danger',
};

export const StatusBadge = ({ status }: { status: DatasetStatus }) => (
  <Badge tone={statusTone[status]}>{status}</Badge>
);

export const AccessBadge = ({ access }: { access: AccessLevel | 'Public' | 'Private' }) => {
  const isPublic = access === 'Open' || access === 'Public';
  return (
    <Badge tone={isPublic ? 'success' : 'neutral'}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
        {isPublic ? <Globe size={11} /> : <Lock size={11} />}
        {isPublic ? 'Public' : 'Private'}
      </span>
    </Badge>
  );
};

const requestTone: Record<RequestStatus, Tone> = {
  Pending: 'warning',
  Approved: 'success',
  Rejected: 'danger',
  Withdrawn: 'neutral',
};

export const RequestBadge = ({ status }: { status: RequestStatus }) => (
  <Badge tone={requestTone[status]}>{status}</Badge>
);

export const DemoBadge = ({ label = 'Demo data' }: { label?: string }) => (
  <span className="demo-badge" title="Synthetic data and simulated pipeline output for development.">
    <Beaker size={12} />
    {label}
  </span>
);

/* --------------------------------- Headings -------------------------------- */

export const PageHeader = ({
  title,
  description,
  actions,
  eyebrow,
}: {
  title: string;
  description: string;
  actions?: ReactNode;
  eyebrow?: string;
}) => (
  <div className="page-header">
    <div>
      {eyebrow ? <div className="eyebrow">{eyebrow}</div> : null}
      <h1>{title}</h1>
      <p>{description}</p>
    </div>
    {actions ? <div className="page-actions">{actions}</div> : null}
  </div>
);

export const SectionTitle = ({ children }: { children: ReactNode }) => (
  <h3 className="section-title">{children}</h3>
);

/* --------------------------------- StatCard -------------------------------- */

export const StatCard = ({
  label,
  value,
  hint,
  icon,
  tone = 'neutral',
  trend,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  icon: ReactNode;
  tone?: Tone;
  trend?: string;
}) => (
  <Card className="stat-card">
    <div className={cx('stat-icon', `tone-${tone}`)}>{icon}</div>
    <div className="stat-body">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {hint ? <div className="stat-hint">{hint}</div> : null}
    </div>
    {trend ? <div className="stat-trend">{trend}</div> : null}
  </Card>
);

/* ---------------------------------- Alert ---------------------------------- */

const alertIcon = {
  info: <Info size={18} />,
  warning: <AlertTriangle size={18} />,
  success: <CheckCircle2 size={18} />,
  danger: <XCircle size={18} />,
};

export const Alert = ({
  tone = 'info',
  title,
  children,
  ...rest
}: Omit<HTMLAttributes<HTMLDivElement>, 'title'> & {
  tone?: 'info' | 'warning' | 'success' | 'danger';
  title?: string;
  children: ReactNode;
}) => (
  <div className={cx('alert', `alert-${tone}`)} role="status" {...rest}>
    <div className="alert-icon">{alertIcon[tone]}</div>
    <div>
      {title ? <div className="alert-title">{title}</div> : null}
      <div className="alert-text">{children}</div>
    </div>
  </div>
);

export const DemoNotice = ({ text = DEMO_NOTICE }: { text?: string }) => (
  <div className="demo-notice">
    <DemoBadge />
    <span>{text}</span>
  </div>
);

/* -------------------------------- Progress -------------------------------- */

export const ProgressBar = ({
  value,
  tone = 'info',
  height = 8,
}: {
  value: number;
  tone?: Tone;
  height?: number;
}) => (
  <div className="progress-track" style={{ height }} role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
    <div className={cx('progress-fill', `tone-${tone}`)} style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
  </div>
);

/* -------------------------------- ScoreRing ------------------------------- */

export const ScoreRing = ({
  value,
  size = 112,
  label = 'score',
  sublabel,
}: {
  value: number | null;
  size?: number;
  label?: string;
  sublabel?: string;
}) => {
  const stroke = size > 90 ? 9 : 7;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const safe = value ?? 0;
  const offset = circumference - (safe / 100) * circumference;
  const tone = value == null ? 'neutral' : value >= 85 ? 'success' : value >= 70 ? 'warning' : 'danger';
  return (
    <div className="score-ring" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle className="ring-track" cx={size / 2} cy={size / 2} r={radius} strokeWidth={stroke} />
        {value != null ? (
          <circle
            className={cx('ring-value', `ring-${tone}`)}
            cx={size / 2}
            cy={size / 2}
            r={radius}
            strokeWidth={stroke}
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
          />
        ) : null}
      </svg>
      <div className="ring-center">
        <strong>{value == null ? '—' : value}</strong>
        <span>{sublabel ?? label}</span>
      </div>
    </div>
  );
};

/* ---------------------------------- Inputs -------------------------------- */

export const SearchInput = ({
  value,
  onChange,
  placeholder = 'Search…',
  ariaLabel,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  ariaLabel?: string;
}) => (
  <div className="search-input">
    <Search size={16} />
    <input
      type="search"
      value={value}
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
      aria-label={ariaLabel ?? placeholder}
    />
  </div>
);

export const Field = ({
  label,
  hint,
  error,
  required,
  htmlFor,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  htmlFor?: string;
  children: ReactNode;
}) => (
  <div className="field">
    <label className="field-label" htmlFor={htmlFor}>
      {label}
      {required ? <span className="required"> *</span> : null}
    </label>
    {children}
    {error ? <div className="field-error">{error}</div> : hint ? <div className="field-hint">{hint}</div> : null}
  </div>
);

/* --------------------------------- Tabs ----------------------------------- */

export const Tabs = ({
  tabs,
  active,
  onChange,
}: {
  tabs: { id: string; label: string; count?: number }[];
  active: string;
  onChange: (id: string) => void;
}) => (
  <div className="tabs" role="tablist">
    {tabs.map((tab) => (
      <button
        key={tab.id}
        role="tab"
        aria-selected={active === tab.id}
        className={cx('tab', active === tab.id && 'tab-active')}
        onClick={() => onChange(tab.id)}
      >
        {tab.label}
        {tab.count != null ? <span className="tab-count">{tab.count}</span> : null}
      </button>
    ))}
  </div>
);

/* --------------------------------- Modal ---------------------------------- */

export const Modal = ({
  open,
  title,
  subtitle,
  onClose,
  children,
  footer,
  wide,
}: {
  open: boolean;
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) => {
  useEffect(() => {
    if (!open) return;
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <div
        className={cx('modal', wide && 'modal-wide')}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <div>
            <h2>{title}</h2>
            {subtitle ? <p>{subtitle}</p> : null}
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close dialog">
            <X size={18} />
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer ? <div className="modal-footer">{footer}</div> : null}
      </div>
    </div>
  );
};

/* -------------------------------- Pagination ------------------------------- */

export const Pagination = ({
  page,
  pageCount,
  onPageChange,
  totalLabel,
}: {
  page: number;
  pageCount: number;
  onPageChange: (page: number) => void;
  totalLabel?: string;
}) => (
  <div className="pagination">
    <span className="pagination-label">{totalLabel}</span>
    <div className="pagination-controls">
      <button className="icon-btn" disabled={page <= 1} onClick={() => onPageChange(page - 1)} aria-label="Previous page">
        <ChevronLeft size={16} />
      </button>
      <span className="pagination-page">
        Page {page} of {Math.max(1, pageCount)}
      </span>
      <button
        className="icon-btn"
        disabled={page >= pageCount}
        onClick={() => onPageChange(page + 1)}
        aria-label="Next page"
      >
        <ChevronRight size={16} />
      </button>
    </div>
  </div>
);

/* -------------------------------- Empty/Load ------------------------------- */

export const EmptyState = ({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) => (
  <div className="empty-state">
    <div className="empty-icon">
      <Search size={20} />
    </div>
    <h3>{title}</h3>
    <p>{description}</p>
    {action}
  </div>
);

export const LoadingState = ({ label = 'Loading…' }: { label?: string }) => (
  <div className="loading-state">
    <Loader2 className="spin" size={20} />
    <span>{label}</span>
  </div>
);

export const InfoRow = ({ label, children }: { label: string; children: ReactNode }) => (
  <div className="info-row">
    <span className="info-label">{label}</span>
    <span className="info-value">{children}</span>
  </div>
);

/* --------------------------------- Toasts --------------------------------- */

export const ToastViewport = () => {
  const { toasts, dismissToast } = useDemo();
  if (toasts.length === 0) return null;
  return (
    <div className="toast-viewport" aria-live="polite">
      {toasts.map((toast) => (
        <div key={toast.id} className={cx('toast', `toast-${toast.type}`)}>
          <div className="toast-icon">
            {toast.type === 'success' ? <CheckCircle2 size={14} /> : toast.type === 'error' ? <XCircle size={14} /> : <Info size={14} />}
          </div>
          <div className="toast-body">
            <strong>{toast.title}</strong>
            {toast.message ? <p>{toast.message}</p> : null}
          </div>
          <button className="icon-btn toast-close" onClick={() => dismissToast(toast.id)} aria-label="Dismiss notification">
            <X size={11} />
          </button>
        </div>
      ))}
    </div>
  );
};
