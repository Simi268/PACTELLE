import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { Link, Navigate, NavLink, Route, Routes, useNavigate } from 'react-router-dom';
import {
  Activity, AlertTriangle, BookOpenCheck, CalendarClock, Check, ChevronDown,
  ChevronRight, CircleAlert, ClipboardCheck, FileText, Gauge, LogOut, Menu, Plus,
  RefreshCw, ShieldCheck, Sparkles, Users, X, Pencil, UserPlus, Search,
} from 'lucide-react';
import { apiCall, message } from './api';

type Session = {
  access_token: string;
  user: { id: string; full_name: string; email: string };
  organization: { id: string; name: string };
};
type Member = { user_id: string; full_name: string; email: string; role: string; joined_at?: string };
type Option = { value: string; label: string };

const getSession = (): Session | null => {
  try { return JSON.parse(localStorage.getItem('pactelle_session') || 'null'); } catch { return null; }
};

function useSession() {
  const [session, setSession] = useState<Session | null>(getSession);
  const save = (value: Session) => {
    localStorage.setItem('pactelle_token', value.access_token);
    localStorage.setItem('pactelle_session', JSON.stringify(value));
    setSession(value);
  };
  const logout = () => {
    localStorage.removeItem('pactelle_token');
    localStorage.removeItem('pactelle_session');
    setSession(null);
  };
  return { session, save, logout };
}

function Auth({ mode, save }: { mode: 'login' | 'register'; save: (value: Session) => void }) {
  const navigate = useNavigate();
  const [fullName, setFullName] = useState('');
  const [organization, setOrganization] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const result = mode === 'login'
        ? await apiCall.login(email, password)
        : await apiCall.register({ full_name: fullName, email, password, organization_name: organization });
      save(result); navigate('/');
    } catch (err) { setError(message(err)); } finally { setBusy(false); }
  };
  return <div className="auth">
    <section className="auth-left">
      <div className="brand inverse"><b className="mark">P</b><span>PACTELLE<small>AGREEMENT INTELLIGENCE</small></span></div>
      <div className="hero-copy"><small>INTELLIGENCE BEHIND EVERY AGREEMENT</small><h1>Know what<br />you've agreed to.</h1>
        <p>Bring contracts, obligations and portfolio risks into one clear, accountable workspace.</p>
        <div className="proof"><span><ShieldCheck /> Evidence-led insights</span><span><Check /> Human-governed actions</span></div>
      </div>
      <small className="copyright">PACTELLE · Secure agreement intelligence</small>
    </section>
    <section className="auth-right"><form className="auth-form" onSubmit={submit}>
      <div className="eyebrow">{mode === 'login' ? 'WELCOME BACK' : 'GET STARTED'}</div>
      <h2>{mode === 'login' ? 'Sign in to your workspace' : 'Create your workspace'}</h2>
      <p>{mode === 'login' ? 'Pick up where your team left off.' : 'Set up your organization and start bringing agreements together.'}</p>
      {mode === 'register' && <>
        <label>Full name<input value={fullName} onChange={e => setFullName(e.target.value)} minLength={2} required /></label>
        <label>Organization name<input value={organization} onChange={e => setOrganization(e.target.value)} minLength={2} required /></label>
      </>}
      <label>Email address<input type="email" value={email} onChange={e => setEmail(e.target.value)} required placeholder="you@company.com" /></label>
      <label>Password<input type="password" value={password} onChange={e => setPassword(e.target.value)} required minLength={mode === 'register' ? 12 : 1} placeholder={mode === 'register' ? 'At least 12 characters' : 'Your password'} /></label>
      {error && <div className="error">{error}</div>}
      <button className="btn primary full" disabled={busy}>{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'} <ChevronRight size={16} /></button>
      <div className="switch">{mode === 'login' ? 'New to PACTELLE?' : 'Already have an account?'} <Link to={mode === 'login' ? '/register' : '/login'}>{mode === 'login' ? 'Create an account' : 'Sign in'}</Link></div>
    </form></section>
  </div>;
}

function Shell({ children, session, logout }: { children: ReactNode; session: Session; logout: () => void }) {
  const [mobile, setMobile] = useState(false);
  const navigation = [
    ['/', 'Overview', Gauge], ['/contracts', 'Contracts', FileText],
    ['/findings', 'Portfolio intelligence', CircleAlert], ['/obligations', 'Obligations', BookOpenCheck],
    ['/actions', 'Actions', Activity], ['/team', 'Team', Users],
  ] as const;
  return <div className="shell">
    <aside className={`sidebar ${mobile ? 'open' : ''}`}>
      <div className="brand"><b className="mark">P</b><span>PACTELLE<small>AGREEMENT INTELLIGENCE</small></span><button className="close" onClick={() => setMobile(false)} aria-label="Close navigation"><X /></button></div>
      <div className="workspace"><b>{session.organization.name.slice(0, 1).toUpperCase()}</b><span>{session.organization.name}<small>Business workspace</small></span><ChevronDown size={15} /></div>
      <div className="nav-label">WORKSPACE</div>
      <nav>{navigation.map(([to, label, Icon]) => <NavLink key={to} to={to} end={to === '/'} onClick={() => setMobile(false)} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}><Icon size={18} />{label}</NavLink>)}</nav>
      <div className="side-bottom">
        <div className="help"><b>Agreement workspace</b><p>Keep evidence, obligations and decisions connected.</p><span>Human review stays in control.</span></div>
        <button className="nav-item" onClick={logout}><LogOut size={17} />Sign out</button>
        <div className="user"><b>{session.user.full_name.split(' ').map(part => part[0]).slice(0, 2).join('').toUpperCase()}</b><span>{session.user.full_name}<small>{session.user.email}</small></span></div>
      </div>
    </aside>
    {mobile && <button className="scrim" onClick={() => setMobile(false)} aria-label="Close menu" />}
    <main><header className="topbar"><button className="hamb" onClick={() => setMobile(true)} aria-label="Open menu"><Menu /></button>
      <span>Workspace <i>/</i> <b>{navigation.find(item => item[0] === location.pathname)?.[1] || 'Overview'}</b></span>
      <div><span className="topbar-note">Agreement intelligence · Workspace</span><span className="top-avatar">{session.user.full_name.slice(0, 1).toUpperCase()}</span></div>
    </header><div className="content">{children}</div><footer>PACTELLE · Intelligence behind every agreement <span>Secure workspace</span></footer></main>
  </div>;
}

function Heading({ eyebrow, title, desc, action }: { eyebrow: string; title: string; desc: string; action?: ReactNode }) {
  return <div className="heading"><div><small>{eyebrow}</small><h1>{title}</h1><p>{desc}</p></div>{action}</div>;
}
function Panel({ children, className = '' }: { children: ReactNode; className?: string }) { return <section className={`panel ${className}`}>{children}</section>; }
function Notice({ children, tone = 'success' }: { children: ReactNode; tone?: 'success' | 'error' | 'info' }) { return <div className={`notice ${tone}`}>{children}</div>; }
function Loading() { return <div className="loading"><span className="loader" />Loading workspace data…</div>; }
function Failure({ error, retry }: { error: string; retry: () => void }) { return <div className="empty"><AlertTriangle /><h3>Couldn't load this view</h3><p>{error}</p><button className="btn secondary" onClick={retry}>Try again</button></div>; }

function useData<T>(loader: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(true);
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick(value => value + 1), []);
  useEffect(() => {
    let live = true; setBusy(true); setError('');
    loader().then(value => { if (live) setData(value); })
      .catch(err => { if (live) setError(message(err)); })
      .finally(() => { if (live) setBusy(false); });
    return () => { live = false; };
    // loader is intentionally driven by the explicit dependency list and reload counter.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, ...deps]);
  return { data, error, busy, reload, setData };
}

const fmt = (value?: string | null) => value ? new Date(`${value}${value.length === 10 ? 'T00:00:00' : ''}`).toLocaleDateString() : '—';
const label = (value?: string | null) => value ? value.replaceAll('_', ' ') : '—';
const initials = (name?: string) => (name || '?').split(/\s+/).map(part => part[0]).slice(0, 2).join('').toUpperCase();
const isDatePast = (value?: string | null) => Boolean(value && new Date(`${value}T23:59:59`) < new Date());
function Empty({ icon: Icon, title, desc, action }: { icon: typeof FileText; title: string; desc: string; action?: ReactNode }) {
  return <div className="empty"><Icon /><h3>{title}</h3><p>{desc}</p>{action}</div>;
}
function Field({ label: title, children }: { label: string; children: ReactNode }) { return <label className="field">{title}{children}</label>; }
function MemberSelect({ members, value, onChange, allowUnassigned = true }: { members: Member[]; value: string; onChange: (value: string) => void; allowUnassigned?: boolean }) {
  return <select value={value} onChange={event => onChange(event.target.value)}><option value="">{allowUnassigned ? 'Unassigned' : 'Choose a team member'}</option>{members.map(member => <option key={member.user_id} value={member.user_id}>{member.full_name} · {member.role}</option>)}</select>;
}

function Dashboard({ org }: { org: string }) {
  const { data, error, busy, reload } = useData<any>(() => apiCall.dashboard(org), [org]);
  return <>
    <Heading eyebrow="YOUR WORKSPACE" title="Good to see you." desc="A current view of your agreement portfolio." action={<button className="btn secondary" onClick={reload}><RefreshCw size={15} /> Refresh</button>} />
    {busy ? <Loading /> : error ? <Failure error={error} retry={reload} /> : data && <>
      <div className="stats">
        {[
          { title: 'Contracts in portfolio', value: data.contracts?.total ?? 0, note: `${data.contracts?.by_status?.active ?? 0} active`, Icon: FileText },
          { title: 'Open risk findings', value: data.risks?.total_open ?? 0, note: 'Across your agreements', Icon: CircleAlert },
          { title: 'Documents', value: data.documents?.total ?? 0, note: `${data.documents?.by_processing_status?.completed ?? 0} processed`, Icon: ShieldCheck },
          { title: 'Renewals to watch', value: data.monitoring?.upcoming_renewals_next_90_days ?? 0, note: 'Next 90 days', Icon: CalendarClock },
        ].map(item => <Panel className="stat" key={item.title}><div>{item.title}<item.Icon size={18} /></div><strong>{item.value}</strong><small>{item.note}</small></Panel>)}
      </div>
      <Panel className="welcome"><div><small>AGREEMENT INTELLIGENCE</small><h2>Every agreement.<br />One clear picture.</h2><p>Understand obligations, surface portfolio-level risks and turn findings into accountable action.</p><Link to="/contracts" className="btn light">Explore contracts <ChevronRight size={15} /></Link></div><div className="seal"><ShieldCheck size={42} /></div></Panel>
      <div className="two">
        <Panel className="pad"><small>MONITORING</small><h3>Dates that matter</h3>
          <div className="metric-row"><span>Upcoming renewals · 90 days</span><b>{data.monitoring?.upcoming_renewals_next_90_days ?? 0}</b></div>
          <div className="metric-row"><span>Expiring contracts · 30 days</span><b>{data.monitoring?.contracts_expiring_next_30_days ?? 0}</b></div>
        </Panel>
        <Panel className="pad"><small>PORTFOLIO HEALTH</small><h3>Open findings by severity</h3>
          {Object.entries(data.risks?.by_severity || {}).length ? Object.entries(data.risks.by_severity).map(([key, value]) => <div className="metric-row" key={key}><span>{label(key)}</span><b>{String(value)}</b></div>) : <p className="muted">No open findings currently returned by the API.</p>}
        </Panel>
      </div>
      <p className="data-footnote">Metrics reflect the latest dashboard response from your workspace.</p>
    </>}
  </>;
}

function Contracts({ org }: { org: string }) {
  const { data, error, busy, reload } = useData<any[]>(() => apiCall.contracts(org), [org]);
  const [editing, setEditing] = useState<any | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [kind, setKind] = useState('');
  const [status, setStatus] = useState('draft');
  const [effective, setEffective] = useState('');
  const [expiration, setExpiration] = useState('');
  const [notice, setNotice] = useState('');
  const [noticeTone, setNoticeTone] = useState<'success' | 'error'>('success');
  const [saving, setSaving] = useState(false);
  const [selected, setSelected] = useState<any | null>(null);
  const [docs, setDocs] = useState<any[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [processing, setProcessing] = useState<string[]>([]);
  const [docError, setDocError] = useState('');

  const clearForm = () => { setTitle(''); setKind(''); setStatus('draft'); setEffective(''); setExpiration(''); };
  const openCreate = () => { clearForm(); setEditing(null); setCreateOpen(true); setNotice(''); };
  const openEdit = (contract: any) => {
    setEditing(contract); setTitle(contract.title || ''); setKind(contract.contract_type || '');
    setStatus(contract.status || 'draft'); setEffective(contract.effective_date || '');
    setExpiration(contract.expiration_date || ''); setCreateOpen(true); setNotice('');
  };
  const saveContract = async (event: FormEvent) => {
    event.preventDefault(); setSaving(true); setNotice('');
    const payload = { title: title.trim(), contract_type: kind.trim() || null, status, effective_date: effective || null, expiration_date: expiration || null };
    try {
      if (editing) await apiCall.updateContract(editing.id, payload);
      else await apiCall.createContract(org, payload);
      setNotice(editing ? 'Contract updated.' : 'Contract record created.');
      setCreateOpen(false); clearForm(); reload();
    } catch (err) { setNotice(message(err)); setNoticeTone('error'); }
    finally { setSaving(false); }
  };
  const openDocuments = async (contract: any) => {
    setSelected(contract); setDocs([]); setDocError(''); setFile(null);
    try { setDocs(await apiCall.contractDocuments(contract.id)); }
    catch (err) { setDocError(message(err)); }
  };
  const upload = async () => {
    if (!file || !selected) return;
    setUploading(true); setDocError('');
    try {
      await apiCall.upload(selected.id, file);
      setDocs(await apiCall.contractDocuments(selected.id)); setFile(null);
    } catch (err) { setDocError(message(err)); }
    finally { setUploading(false); }
  };
  const processDocument = async (documentId: string) => {
    setProcessing(current => [...current, documentId]); setDocError('');
    try { await apiCall.process(documentId); setDocError('Processing request submitted. Status will refresh shortly.'); }
    catch (err) { setDocError(message(err)); }
    finally { setProcessing(current => current.filter(id => id !== documentId)); }
  };
  useEffect(() => {
    if (!selected || !docs.some(doc => doc.processing_status === 'processing')) return;
    let live = true;
    const timer = window.setInterval(async () => {
      try {
        const refreshed = await Promise.all(docs.map(async doc => doc.processing_status === 'processing'
          ? { ...doc, ...await apiCall.processingStatus(doc.id) } : doc));
        if (live) setDocs(refreshed);
      } catch (err) { if (live) setDocError(message(err)); }
    }, 2500);
    return () => { live = false; window.clearInterval(timer); };
  }, [selected, docs]);

  return <>
    <Heading eyebrow="AGREEMENT REGISTER" title="Contracts" desc="Create, maintain and review the agreements your business relies on."
      action={<button className="btn primary" onClick={openCreate}><Plus size={16} /> New contract</button>} />
    {notice && <Notice tone={noticeTone}>{notice}</Notice>}
    {createOpen && <Panel className="pad form-panel"><div className="section-title"><div><small>{editing ? 'UPDATE RECORD' : 'NEW AGREEMENT'}</small><h3>{editing ? 'Edit contract details' : 'Create a contract record'}</h3></div><button className="icon-button" onClick={() => setCreateOpen(false)}><X /></button></div>
      <form className="form-grid" onSubmit={saveContract}>
        <Field label="Contract title"><input required minLength={1} maxLength={255} value={title} onChange={e => setTitle(e.target.value)} /></Field>
        <Field label="Contract type"><input maxLength={100} value={kind} onChange={e => setKind(e.target.value)} placeholder="Vendor, SaaS, employment…" /></Field>
        <Field label="Status"><select value={status} onChange={e => setStatus(e.target.value)}><option value="draft">Draft</option><option value="active">Active</option><option value="expired">Expired</option><option value="terminated">Terminated</option></select></Field>
        <Field label="Effective date"><input type="date" value={effective} onChange={e => setEffective(e.target.value)} /></Field>
        <Field label="Expiration date"><input type="date" value={expiration} onChange={e => setExpiration(e.target.value)} min={effective || undefined} /></Field>
        <div className="form-actions"><button className="btn primary" disabled={saving}>{saving ? 'Saving…' : editing ? 'Save changes' : 'Create contract'}</button><button type="button" className="btn secondary" onClick={() => setCreateOpen(false)}>Cancel</button></div>
      </form>
    </Panel>}
    {busy ? <Loading /> : error ? <Failure error={error} retry={reload} /> : !data?.length
      ? <Empty icon={FileText} title="Your contract register is empty" desc="Create your first contract record, then upload its source document." action={<button className="btn primary" onClick={openCreate}>Create first contract</button>} />
      : <Panel><div className="table-wrap"><table><thead><tr><th>Contract</th><th>Type</th><th>Status</th><th>Effective</th><th>Expiration</th><th>Manage</th></tr></thead><tbody>
        {data.map(contract => <tr key={contract.id}><td><b>{contract.title}</b><small>{contract.id.slice(0, 8)}</small></td><td>{contract.contract_type || '—'}</td><td><span className={`pill ${contract.status}`}>{label(contract.status)}</span></td><td>{fmt(contract.effective_date)}</td><td>{fmt(contract.expiration_date)}</td><td><div className="table-actions"><button className="btn secondary small" onClick={() => openEdit(contract)}><Pencil size={13} /> Edit</button><button className="btn secondary small" onClick={() => void openDocuments(contract)}><FileText size={13} /> Documents</button></div></td></tr>)}
      </tbody></table></div></Panel>}
    {selected && <div className="modal-backdrop" onClick={() => setSelected(null)}><section className="modal wide" onClick={e => e.stopPropagation()}>
      <div className="modal-head"><div><small>DOCUMENT MANAGEMENT</small><h2>{selected.title}</h2><p>Upload source files and process them for evidence extraction.</p></div><button className="icon-button" onClick={() => setSelected(null)}><X /></button></div>
      <div className="upload-box"><FileText size={22} /><div><b>Add a contract document</b><small>PDF, DOC, DOCX or TXT</small></div><input type="file" accept=".pdf,.doc,.docx,.txt" onChange={e => setFile(e.target.files?.[0] || null)} /><button className="btn primary" disabled={!file || uploading} onClick={() => void upload()}>{uploading ? 'Uploading…' : 'Upload file'}</button></div>
      {docError && <Notice tone={docError.toLowerCase().includes('error') ? 'error' : 'info'}>{docError}</Notice>}
      {docs.length ? <div className="document-list">{docs.map(doc => {
        const state = doc.processing_status || 'uploaded';
        const active = state === 'processing' || processing.includes(doc.id);
        const complete = state === 'completed';
        const failed = state === 'failed' || state === 'error';
        return <div className="document-row" key={doc.id}><div className="document-icon"><FileText /></div><div className="document-meta"><b>{doc.original_filename || doc.filename || 'Contract document'}</b><small>Added {fmt(doc.created_at || doc.uploaded_at)}</small></div><span className={`pill ${failed ? 'critical' : complete ? 'completed' : active ? 'processing' : ''}`}>{label(state)}</span><button className="btn secondary small" disabled={active || complete} onClick={() => void processDocument(doc.id)}>{active ? 'Processing…' : complete ? 'Processed' : failed ? 'Retry' : 'Process'}</button></div>;
      })}</div> : <p className="muted empty-inline">No documents uploaded to this contract yet.</p>}
    </section></div>}
  </>;
}
function formatAssessmentLabel(key: string) {
  return key.replaceAll('_', ' ').replace(/\b\w/g, char => char.toUpperCase());
}

function AssessmentValue({ value }: { value: any }): ReactNode {
  if (value === null || value === undefined || value === '') {
    return <span className="muted">Not available</span>;
  }
  if (typeof value === 'boolean') {
    return <span className={`assessment-bool ${value ? 'yes' : 'no'}`}>{value ? 'Yes' : 'No'}</span>;
  }
  if (typeof value !== 'object') return <>{String(value)}</>;
  if (Array.isArray(value)) {
    if (!value.length) return <span className="muted">None recorded</span>;
    return <ul className="assessment-list">{value.map((item, index) =>
      <li key={index}><AssessmentValue value={item} /></li>
    )}</ul>;
  }
  return <div className="assessment-nested">
    {Object.entries(value).map(([key, child]) => <div className="assessment-field" key={key}>
      <small>{formatAssessmentLabel(key)}</small>
      <div><AssessmentValue value={child} /></div>
    </div>)}
  </div>;
}

function AssessmentMetric({ title, value, note }: { title: string; value: ReactNode; note?: ReactNode }) {
  return <div className="assessment-metric">
    <small>{title}</small>
    <strong>{value}</strong>
    {note && <span>{note}</span>}
  </div>;
}

function AssessmentDetails({ value }: { value: any }) {
  const details = value && typeof value === 'object' ? value : {};
  const impact = details.impact_assessment || {};
  const comparison = details.comparison || impact.comparison || {};
  const liability = details.liability_comparison || details.liabilityComparison || {};
  const legalConflictEstablished =
    liability.legal_conflict_established ??
    details.legal_conflict_established ??
    impact.legal_conflict_established ??
    impact.legal_conflict?.established ??
    null;
  const first = liability.first || details.first || {};
  const second = liability.second || details.second || {};
  const unknowns = impact.unknowns || details.unknowns || [];
  const observedFacts = details.observed_facts || details.observedFacts || [];
  const assumptions = details.assumptions || [];
  const evidenceBasis = impact.evidence_basis || details.evidence_basis || [];
  const hasStructuredData = Object.keys(details).length > 0;
  const renderedAssessmentKeys = new Set([
    'classification', 'comparison_type', 'obligation_type', 'generator_version',
    'comparison', 'observed_facts', 'observedFacts', 'unknowns', 'assumptions',
    'liability_comparison', 'liabilityComparison', 'impact_assessment', 'evidence_basis',
    'legal_conflict_established', 'legal_conflict', 'impact_level',
    'impact_level_rationale', 'business_impact', 'potential_consequences',
    'recommended_action', 'financial_exposure', 'missing_inputs',
    'human_review_required', 'assessment_type', 'differing_attributes',
    'requires_human_review', 'scope_matches', 'comparable_scope'
  ]);
  const technicalEntries = Object.entries(details).filter(([key]) => !renderedAssessmentKeys.has(key));

  if (!hasStructuredData) return <p className="muted">No additional assessment available.</p>;

  return <><style>{`
.assessment-report{display:grid;gap:18px;color:#40575b}
.assessment-summary-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
.assessment-metric{display:grid;gap:7px;padding:14px;background:#f6f9f8;border:1px solid #e5eeeb;border-radius:10px;min-width:0}
.assessment-metric>small,.assessment-compare-card>small{font-size:9px;font-weight:750;letter-spacing:.09em;text-transform:uppercase;color:#829592}
.assessment-metric>strong{font-size:14px;line-height:1.4;overflow-wrap:anywhere;color:#29484b}
.assessment-metric>span{font-size:11px;color:#718582}
.assessment-report-section{padding:17px;border:1px solid #e5eeeb;border-radius:12px;background:#fff}
.assessment-section-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:13px}
.assessment-section-heading small{font-size:9px;font-weight:750;letter-spacing:.1em;color:#76918c}
.assessment-section-heading h4{margin:4px 0 0;font-size:15px;color:#29484b}
.assessment-compare-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.assessment-compare-card{padding:14px;background:#f7faf9;border:1px solid #e5eeeb;border-radius:9px;min-width:0}
.assessment-compare-card>strong{display:block;margin:8px 0 3px;font-size:22px;color:#245e59}
.assessment-compare-card>span{font-size:11px;color:#81918e}
.assessment-compare-card .assessment-field{margin-top:12px;padding-top:10px;border-top:1px solid #e5eeeb}
.assessment-list{padding-left:19px;margin:8px 0 0;display:grid;gap:9px;line-height:1.65;font-size:12px}
.assessment-unknowns{background:#fffdf8;border-color:#eee7d8}
.assessment-unknowns .assessment-section-heading h4{color:#79633c}
.assessment-nested{display:grid;gap:9px}
.assessment-field{min-width:0}
.assessment-field>small{display:block;margin-bottom:4px;font-size:9px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#8a9b98}
.assessment-field>div,.assessment-field{font-size:12px;overflow-wrap:anywhere}
.assessment-bool{font-weight:700}
.assessment-bool.yes{color:#43816c}
.assessment-bool.no{color:#ad6258}
.assessment-facts-strip{display:flex;flex-wrap:wrap;gap:8px;margin-top:13px}
.assessment-facts-strip>span{padding:7px 9px;background:#f5f8f7;border-radius:7px;font-size:10px;color:#718582}
.assessment-facts-strip b{display:block;margin-top:4px;color:#3d5c5a}
.assessment-difference,.assessment-rationale{padding:11px 13px;background:#f1f7f5;border-radius:8px;font-size:12px;line-height:1.6}
.assessment-evidence{padding:13px 0;border-top:1px solid #e9efed}
.assessment-evidence:first-of-type{border-top:0}
.assessment-evidence>b{font-size:12px}
.assessment-evidence p,.assessment-evidence blockquote{font-size:11px;line-height:1.65}
.assessment-evidence blockquote{margin:8px 0;padding:10px 12px;background:#f6f9f8;border-left:3px solid #8bb7ad}
.assessment-evidence>small{font-size:9px;color:#81918e;overflow-wrap:anywhere}
.assessment-technical-details{padding:12px 14px;border:1px solid #e5eeeb;border-radius:9px;background:#fafcfb}
.assessment-technical-details summary{cursor:pointer;font-size:11px;font-weight:700;color:#607875}
.assessment-technical-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;padding-top:14px}
@media(max-width:760px){.assessment-summary-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:520px){.assessment-summary-grid,.assessment-compare-grid,.assessment-technical-grid{grid-template-columns:1fr}.assessment-report-section{padding:13px}}
`}</style><div className="assessment-report">
    <div className="assessment-summary-grid">
      <AssessmentMetric title="Classification" value={formatAssessmentLabel(details.classification || 'Not specified')} />
      <AssessmentMetric title="Comparison type" value={formatAssessmentLabel(details.comparison_type || 'Not specified')} />
      <AssessmentMetric title="Obligation type" value={formatAssessmentLabel(details.obligation_type || 'Not specified')} />
      <AssessmentMetric title="Generator version" value={details.generator_version || 'Not specified'} />
    </div>

    {(comparison.first_contract_period || comparison.second_contract_period) && <section className="assessment-report-section">
      <div className="assessment-section-heading"><div><small>CONTRACT COMPARISON</small><h4>Reference period difference</h4></div>
        {comparison.shorter_period && <span className="pill">Shorter: {formatAssessmentLabel(comparison.shorter_period)}</span>}
      </div>
      <div className="assessment-compare-grid">
        <div className="assessment-compare-card"><small>Contract A · First</small>
          <strong>{comparison.first_contract_period?.value ?? '—'} {comparison.first_contract_period?.unit || ''}</strong>
          <span>Reference period</span>
        </div>
        <div className="assessment-compare-card"><small>Contract B · Second</small>
          <strong>{comparison.second_contract_period?.value ?? '—'} {comparison.second_contract_period?.unit || ''}</strong>
          <span>Reference period</span>
        </div>
      </div>
    </section>}

    {observedFacts.length > 0 && <section className="assessment-report-section">
      <div className="assessment-section-heading"><div><small>WHAT THE EVIDENCE SHOWS</small><h4>Observed facts</h4></div></div>
      <ul className="assessment-list">{observedFacts.map((fact: any, index: number) =>
        <li key={index}><AssessmentValue value={fact} /></li>
      )}</ul>
    </section>}

    {unknowns.length > 0 && <section className="assessment-report-section assessment-unknowns">
      <div className="assessment-section-heading"><div><small>INFORMATION GAPS</small><h4>What still needs verification</h4></div></div>
      <ul className="assessment-list">{unknowns.map((item: any, index: number) =>
        <li key={index}><AssessmentValue value={item} /></li>
      )}</ul>
    </section>}

    {assumptions.length > 0 && <section className="assessment-report-section">
      <div className="assessment-section-heading"><div><small>ANALYSIS BASIS</small><h4>Assumptions</h4></div></div>
      <AssessmentValue value={assumptions} />
    </section>}

    {(first && Object.keys(first).length > 0 || second && Object.keys(second).length > 0) && <section className="assessment-report-section">
      <div className="assessment-section-heading"><div><small>LIABILITY TERMS</small><h4>Side-by-side clause attributes</h4></div></div>
      <div className="assessment-compare-grid">
        {[['Contract A', first], ['Contract B', second]].map(([title, item]: any) =>
          <div className="assessment-compare-card" key={title}>
            <small>{title}</small>
            <div className="assessment-field"><small>Scope</small><AssessmentValue value={item.scope} /></div>
            <div className="assessment-field"><small>Cap basis</small><AssessmentValue value={item.cap_basis} /></div>
            <div className="assessment-field"><small>Cap multiplier</small><AssessmentValue value={item.cap_multiplier} /></div>
            <div className="assessment-field"><small>Reference period</small><AssessmentValue value={item.reference_period} /></div>
            <div className="assessment-field"><small>Source supported</small><AssessmentValue value={item.source_supported} /></div>
          </div>
        )}
      </div>
      <div className="assessment-facts-strip">
        <span>Scope matches <b><AssessmentValue value={liability.scope_matches} /></b></span>
        <span>Comparable scope <b><AssessmentValue value={liability.comparable_scope} /></b></span>
        <span>Legal conflict established <b>{legalConflictEstablished === true ? 'Yes' : legalConflictEstablished === false ? 'No' : 'Not established'}</b></span>
        <span>Human review required <b><AssessmentValue value={liability.requires_human_review ?? impact.human_review_required} /></b></span>
      </div>
      {liability.differing_attributes?.length > 0 && <p className="assessment-difference">Differing attributes: {liability.differing_attributes.map(formatAssessmentLabel).join(', ')}</p>}
    </section>}

    {evidenceBasis.length > 0 && <section className="assessment-report-section">
      <div className="assessment-section-heading"><div><small>SUPPORTING MATERIAL</small><h4>Impact evidence basis</h4></div></div>
      {evidenceBasis.map((item: any, index: number) => <article className="assessment-evidence" key={item.evidence_id || index}>
        <b>{item.contract_title || `Evidence ${index + 1}`}</b>
        {item.claim && <p>{item.claim}</p>}
        {(item.evidence_text || item.original_text || item.source_excerpt) &&
          <blockquote>{item.evidence_text || item.original_text || item.source_excerpt}</blockquote>}
        <small>
          {item.contract_id || ''}
          {item.evidence_id ? ` · Evidence ${item.evidence_id}` : ''}
          {item.page_number ? ` · Page ${item.page_number}` : ''}
          {item.clause_id ? ` · Clause ${item.clause_id}` : ''}
          {item.document_id ? ` · Document ${item.document_id}` : ''}
          {item.char_start != null && item.char_end != null ? ` · Source position ${item.char_start}–${item.char_end}` : ''}
        </small>
      </article>)}
    </section>}

    {impact && Object.keys(impact).length > 0 && <section className="assessment-report-section">
      <div className="assessment-section-heading"><div><small>ASSESSMENT CONTROLS</small><h4>Impact and review status</h4></div></div>
      <div className="assessment-summary-grid">
        <AssessmentMetric title="Impact level" value={formatAssessmentLabel(impact.impact_level || 'Undetermined')} />
        <AssessmentMetric title="Legal conclusion" value={impact.legal_conclusion || 'Not available'} />
        <AssessmentMetric title="Financial exposure" value={impact.financial_exposure?.quantified ? `${impact.financial_exposure.amount || ''} ${impact.financial_exposure.currency || ''}` : 'Not quantified'} />
        <AssessmentMetric title="Human review" value={impact.human_review_required ? 'Required' : 'Not specified'} />
      </div>
      {impact.impact_level_rationale && <p className="assessment-rationale">{impact.impact_level_rationale}</p>}
      {impact.missing_inputs?.length > 0 && <><h5>Missing inputs</h5><AssessmentValue value={impact.missing_inputs} /></>}
    </section>}

    {technicalEntries.length > 0 && <details className="assessment-technical-details">
      <summary>Additional assessment attributes</summary>
      <div className="assessment-technical-grid">
        {technicalEntries.map(([key, child]) => <div className="assessment-field" key={key}>
          <small>{formatAssessmentLabel(key)}</small><AssessmentValue value={child} />
        </div>)}
      </div>
    </details>}
  </div></>;
}

function Findings({ org }: { org: string }) {
  const { data, error, busy, reload } = useData<any>(() => apiCall.findings(org), [org]);
  const [notice, setNotice] = useState('');
  const [running, setRunning] = useState(false);
  const [selected, setSelected] = useState<any | null>(null);
  const [detail, setDetail] = useState<any | null>(null);
  const [detailBusy, setDetailBusy] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [recommending, setRecommending] = useState(false);

  const runAnalysis = async () => {
    setRunning(true); setNotice('');
    try { const result = await apiCall.analyse(org); setNotice(`Analysis completed. ${result.findings?.length ?? 0} findings returned for review.`); reload(); }
    catch (err) { setNotice(message(err)); } finally { setRunning(false); }
  };
  const openFinding = async (finding: any) => {
    setSelected(finding); setDetail(null); setDetailError(''); setDetailBusy(true);
    try { setDetail(await apiCall.finding(org, finding.id)); }
    catch (err) { setDetailError(message(err)); } finally { setDetailBusy(false); }
  };
  const acknowledge = async (id: string) => {
    try { await apiCall.findingStatus(org, id, 'acknowledged'); reload(); if (selected?.id === id) { const updated = await apiCall.finding(org, id); setDetail(updated); setSelected(updated); } }
    catch (err) { setNotice(message(err)); }
  };
  const recommend = async () => {
    if (!detail?.id) return;
    setRecommending(true); setNotice('');
    try {
      const result = await apiCall.recommendActions(org, detail.id);
      setNotice(`${result.created_count ?? 0} recommendations created · ${result.existing_count ?? 0} already existed.`);
      setDetail(await apiCall.finding(org, detail.id));
    } catch (err) { setNotice(message(err)); } finally { setRecommending(false); }
  };
  const evidenceText = (item: any) => item.evidence_text || item.original_text || item.claim || item.extracted_text || item.text || 'No original evidence text available.';
  const contracts = detail?.contracts || selected?.contracts || [];
  const evidence = detail?.evidence || selected?.evidence || [];
  const details = detail?.details || selected?.details || {};
  const impact = details?.impact_assessment;

  return <>
    <Heading eyebrow="CROSS-AGREEMENT REVIEW" title="Portfolio intelligence" desc="Investigate patterns, potential conflicts and repeated exposure across your agreements."
      action={<button className="btn primary" onClick={() => void runAnalysis()} disabled={running}><Sparkles size={16} />{running ? 'Analyzing…' : 'Run portfolio analysis'}</button>} />
    {notice && <Notice>{notice}</Notice>}
    {busy ? <Loading /> : error ? <Failure error={error} retry={reload} /> : !data?.findings?.length
      ? <Empty icon={ShieldCheck} title="No portfolio findings yet" desc="Run analysis after adding contracts and extracting evidence. Findings are generated from your organization's current agreement data." action={<button className="btn secondary" onClick={() => void runAnalysis()} disabled={running}>Run analysis</button>} />
      : <div className="cards">{data.findings.map((finding: any) => <Panel className="finding finding-clickable" key={finding.id}>
        <div className="row"><span className={`pill ${finding.severity}`}>{finding.severity}</span><span className="muted">{label(finding.finding_type)}</span><span className="muted">{label(finding.status)}</span></div>
        <h3>{finding.title}</h3><p>{finding.description}</p><div className="muted">{finding.contracts?.length || 0} linked contracts · {finding.evidence?.length || 0} evidence records · {finding.rule_id || 'Rule not specified'}</div>
        <div className="finding-actions"><button className="btn secondary small" onClick={() => void openFinding(finding)}>View investigation <ChevronRight size={14} /></button>{finding.status === 'open' && <button className="text-btn" onClick={() => void acknowledge(finding.id)}>Acknowledge</button>}</div>
      </Panel>)}</div>}
    {selected && <div className="detail-backdrop" onClick={() => setSelected(null)}><section className="finding-detail" onClick={e => e.stopPropagation()}>
      <header className="detail-header"><div><small>PORTFOLIO INVESTIGATION</small><h2>Finding details</h2></div><button className="detail-close" onClick={() => setSelected(null)}><X /></button></header>
      {detailBusy ? <Loading /> : detailError ? <Failure error={detailError} retry={() => void openFinding(selected)} /> : detail && <>
        <div className="detail-section"><div className="row"><span className={`pill ${detail.severity}`}>{detail.severity}</span><span className="pill">{label(detail.status)}</span><span className="pill">{label(detail.assessment_status || 'review')}</span></div>
          <h2>{detail.title}</h2><p>{detail.description}</p><div className="detail-meta"><span>Finding type<b>{label(detail.finding_type)}</b></span><span>Confidence<b>{detail.confidence ?? 'Not specified'}</b></span><span>Rule<b>{detail.rule_id || '—'}</b></span><span>Version<b>{detail.rule_version || '—'}</b></span></div>
        </div>
        <div className="detail-section"><div className="section-title"><h3>Investigation assessment</h3><button className="btn secondary small" onClick={() => void recommend()} disabled={recommending}><Sparkles size={14} />{recommending ? 'Generating…' : 'Generate action recommendations'}</button></div>
          <AssessmentDetails value={details} />
        </div>
        <div className="detail-section"><h3>Linked contracts</h3>{contracts.length ? contracts.map((contract: any, index: number) => <div className="detail-card" key={contract.id || index}><b>{contract.title || contract.contract_title || contract.name || `Contract ${index + 1}`}</b><small>{contract.contract_type || contract.id || ''}</small></div>) : <p className="muted">No linked contracts were returned.</p>}</div>
        <div className="detail-section"><h3>Evidence & source clauses</h3><p className="muted">Review the original extracted text before making a decision.</p>
          {evidence.length ? evidence.map((item: any, index: number) => <article className="evidence-card" key={item.evidence_id || index}>
            <div className="evidence-top"><b>{item.evidence_type || item.obligation_type || `Evidence ${index + 1}`}</b><span>{item.verification_status || 'Verification not specified'}</span></div>
            {item.claim && <p className="evidence-claim">{item.claim}</p>}<blockquote>{evidenceText(item)}</blockquote>
            <div className="evidence-meta">{item.contract_title || item.contract?.title || 'Contract not specified'}{item.page_number ? ` · Page ${item.page_number}` : ''}</div>
            <div className="evidence-provenance"><span>Evidence: {item.evidence_id || 'Unavailable'}</span><span>Clause: {item.clause_id || 'Unavailable'}</span><span>Document: {item.document_id || 'Unavailable'}</span>{item.char_start != null && item.char_end != null && <span>Source position: {item.char_start}–{item.char_end}</span>}</div>
          </article>) : <p className="muted">No evidence records were returned.</p>}
        </div>
        <div className="detail-footer"><span>Human review is required before treating this assessment as an established contractual conflict.</span>{detail.status === 'open' && <button className="btn primary" onClick={() => void acknowledge(detail.id)}><Check size={15} /> Acknowledge finding</button>}</div>
      </>}
    </section></div>}
  </>;
}

function Actions({ org }: { org: string }) {
  const { data, error, busy, reload } = useData<any>(() => apiCall.actions(org), [org]);
  const { data: members } = useData<Member[]>(() => apiCall.members(org), [org]);
  const [notice, setNotice] = useState('');
  const [editing, setEditing] = useState<any | null>(null);
  const [comment, setComment] = useState('');
  const [saving, setSaving] = useState(false);
  const [statusFilter, setStatusFilter] = useState('all');
  const [query, setQuery] = useState('');
  const actions = (data?.actions || []).filter((action: any) => (statusFilter === 'all' || action.status === statusFilter) && `${action.title} ${action.description}`.toLowerCase().includes(query.toLowerCase()));
  const updateStatus = async (action: any, status: string) => {
    setSaving(true); setNotice('');
    try { await apiCall.actionStatus(org, action.id, status, comment.trim() || undefined); setComment(''); setEditing(null); setNotice(`Action marked ${label(status)}.`); reload(); }
    catch (err) { setNotice(message(err)); } finally { setSaving(false); }
  };
  const assign = async (action: any, userId: string) => {
    try { await apiCall.assignAction(org, action.id, userId || null); setNotice('Action assignment updated.'); reload(); }
    catch (err) { setNotice(message(err)); }
  };
  return <>
    <Heading eyebrow="ACCOUNTABLE EXECUTION" title="Actions" desc="Review recommendations, assign owners and track approved work." />
    {notice && <Notice>{notice}</Notice>}
    <div className="toolbar"><div className="search-field"><Search size={15} /><input placeholder="Search actions…" value={query} onChange={e => setQuery(e.target.value)} /></div><select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}><option value="all">All statuses</option>{['proposed', 'approved', 'rejected', 'in_progress', 'completed'].map(status => <option key={status} value={status}>{label(status)}</option>)}</select></div>
    {busy ? <Loading /> : error ? <Failure error={error} retry={reload} /> : !actions.length ? <Empty icon={ClipboardCheck} title="No matching actions" desc="Generate recommendations from a portfolio finding, then manage ownership and progress here." /> :
      <div className="action-grid">{actions.map((action: any) => <Panel className="action-card" key={action.id}>
        <div className="action-top"><span className={`pill ${action.priority}`}>{action.priority} priority</span><span className={`pill status-${action.status}`}>{label(action.status)}</span></div>
        <h3>{action.title}</h3><p>{action.description}</p>{action.rationale && <div className="rationale"><small>WHY THIS ACTION</small><p>{action.rationale}</p></div>}
        {action.finding?.title && <div className="linked-finding"><small>LINKED FINDING</small><b>{action.finding.title}</b></div>}
        <div className="action-fields"><Field label="Assigned owner"><MemberSelect members={members || []} value={action.assigned_to_user_id || ''} onChange={value => void assign(action, value)} /></Field><div><small>Due date</small><b>{fmt(action.due_date)}</b></div></div>
        <div className="action-bottom"><span className="muted">Updated {fmt(action.updated_at)}</span><button className="btn secondary small" onClick={() => { setEditing(action); setComment(''); }}>Update status</button></div>
        {action.audit_entries?.length > 0 && <details className="audit-details"><summary>Activity history · {action.audit_entries.length}</summary>{action.audit_entries.map((entry: any) => <div className="audit-row" key={entry.id}><b>{label(entry.event_type)}</b><span>{entry.previous_status ? `${label(entry.previous_status)} → ` : ''}{label(entry.new_status)}</span><small>{fmt(entry.created_at)}{entry.comment ? ` · ${entry.comment}` : ''}</small></div>)}</details>}
      </Panel>)}</div>}
    {editing && <div className="modal-backdrop" onClick={() => setEditing(null)}><section className="modal" onClick={e => e.stopPropagation()}><div className="modal-head"><div><small>ACTION GOVERNANCE</small><h2>Update action</h2><p>{editing.title}</p></div><button className="icon-button" onClick={() => setEditing(null)}><X /></button></div>
      <Field label="New status"><select id="action-next-status" defaultValue={editing.status}><option value="proposed">Proposed</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="in_progress">In progress</option><option value="completed">Completed</option></select></Field>
      <Field label="Decision / progress note"><textarea value={comment} onChange={e => setComment(e.target.value)} maxLength={4000} placeholder="Add context to the audit trail (optional)" /></Field>
      <div className="form-actions"><button className="btn primary" disabled={saving} onClick={() => void updateStatus(editing, (document.getElementById('action-next-status') as HTMLSelectElement).value)}>{saving ? 'Saving…' : 'Save status'}</button><button className="btn secondary" onClick={() => setEditing(null)}>Cancel</button></div>
    </section></div>}
  </>;
}

function Obligations({ org }: { org: string }) {
  const { data, error, busy, reload } = useData<any>(() => apiCall.obligations(org), [org]);
  const { data: members } = useData<Member[]>(() => apiCall.members(org), [org]);
  const [notice, setNotice] = useState('');
  const [syncing, setSyncing] = useState(false);
  const [selected, setSelected] = useState<any | null>(null);
  const [dueDate, setDueDate] = useState('');
  const [owner, setOwner] = useState('');
  const [status, setStatus] = useState('open');
  const [completionNote, setCompletionNote] = useState('');
  const [waivedReason, setWaivedReason] = useState('');
  const [auditComment, setAuditComment] = useState('');
  const [saving, setSaving] = useState(false);
  const [filter, setFilter] = useState('all');
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [query, setQuery] = useState('');
  const sync = async () => {
    setSyncing(true); setNotice('');
    try { const result = await apiCall.syncObligations(org); setNotice(`${result.created_count} created · ${result.updated_count} updated · ${result.unchanged_count} unchanged · ${result.skipped_rejected_count} skipped as rejected.`); reload(); }
    catch (err) { setNotice(message(err)); } finally { setSyncing(false); }
  };
  const openEditor = (obligation: any) => {
    setSelected(obligation); setDueDate(obligation.due_date || ''); setOwner(obligation.assigned_to_user_id || '');
    setStatus(obligation.status || 'open'); setCompletionNote(obligation.completion_note || '');
    setWaivedReason(obligation.waived_reason || ''); setAuditComment('');
  };
  const saveObligation = async (event: FormEvent) => {
    event.preventDefault(); if (!selected) return;
    setSaving(true); setNotice('');
    const payload: Record<string, unknown> = { due_date: dueDate || null, assigned_to_user_id: owner || null, status, comment: auditComment.trim() || null };
    if (status === 'completed') payload.completion_note = completionNote.trim();
    if (status === 'waived') payload.waived_reason = waivedReason.trim();
    try { await apiCall.obligationStatus(org, selected.id, payload); setSelected(null); setNotice('Obligation updated and audit history recorded.'); reload(); }
    catch (err) { setNotice(message(err)); } finally { setSaving(false); }
  };
  const obligations = (data?.obligations || []).filter((item: any) => (filter === 'all' || item.status === filter) && (!overdueOnly || item.overdue) && `${item.description} ${item.claim} ${item.obligation_family}`.toLowerCase().includes(query.toLowerCase()));
  return <>
    <Heading eyebrow="COMMITMENTS & DEADLINES" title="Obligations" desc="Assign, monitor and close out commitments extracted from agreement evidence."
      action={<button className="btn primary" onClick={() => void sync()} disabled={syncing}><RefreshCw size={15} />{syncing ? 'Syncing…' : 'Sync obligations'}</button>} />
    {notice && <Notice>{notice}</Notice>}
    <div className="toolbar"><div className="search-field"><Search size={15} /><input placeholder="Search obligations…" value={query} onChange={e => setQuery(e.target.value)} /></div>
      <select value={filter} onChange={e => setFilter(e.target.value)}><option value="all">All statuses</option>{['open', 'in_progress', 'completed', 'waived'].map(value => <option key={value} value={value}>{label(value)}</option>)}</select>
      <label className="check-filter"><input type="checkbox" checked={overdueOnly} onChange={e => setOverdueOnly(e.target.checked)} /> Overdue only</label>
    </div>
    {busy ? <Loading /> : error ? <Failure error={error} retry={reload} /> : !obligations.length
      ? <Empty icon={BookOpenCheck} title="No matching obligations" desc="Process contract documents and synchronize extracted commitments to create a trackable obligation register." />
      : <Panel><div className="table-wrap"><table><thead><tr><th>Obligation</th><th>Family</th><th>Verification</th><th>Due date</th><th>Owner</th><th>Status</th><th /></tr></thead><tbody>
        {obligations.map((item: any) => <tr key={item.id}><td><b>{item.description}</b><small>{item.claim}</small></td><td>{label(item.obligation_family)}</td><td><span className="pill">{label(item.verification_status)}</span></td><td>{fmt(item.due_date)} {item.overdue && <em>Overdue</em>}</td><td>{members?.find(member => member.user_id === item.assigned_to_user_id)?.full_name || 'Unassigned'}</td><td><span className={`pill status-${item.status}`}>{label(item.status)}</span></td><td><button className="btn secondary small" onClick={() => openEditor(item)}><Pencil size={13} /> Manage</button></td></tr>)}
      </tbody></table></div></Panel>}
    {selected && <div className="modal-backdrop" onClick={() => setSelected(null)}><section className="modal" onClick={e => e.stopPropagation()}><div className="modal-head"><div><small>OBLIGATION CONTROL</small><h2>Manage obligation</h2><p>{selected.description}</p></div><button className="icon-button" onClick={() => setSelected(null)}><X /></button></div>
      <form className="stack-form" onSubmit={saveObligation}>
        <Field label="Due date"><input type="date" value={dueDate} onChange={e => setDueDate(e.target.value)} /></Field>
        <Field label="Assigned owner"><MemberSelect members={members || []} value={owner} onChange={setOwner} /></Field>
        <Field label="Status"><select value={status} onChange={e => setStatus(e.target.value)}><option value="open">Open</option><option value="in_progress">In progress</option><option value="completed">Completed</option><option value="waived">Waived</option></select></Field>
        {status === 'completed' && <Field label="Completion note"><textarea value={completionNote} onChange={e => setCompletionNote(e.target.value)} maxLength={5000} required placeholder="Describe how this obligation was fulfilled." /></Field>}
        {status === 'waived' && <Field label="Reason for waiver"><textarea value={waivedReason} onChange={e => setWaivedReason(e.target.value)} maxLength={5000} required placeholder="Record why this obligation is being waived." /></Field>}
        <Field label="Audit comment (optional)"><textarea value={auditComment} onChange={e => setAuditComment(e.target.value)} maxLength={4000} placeholder="Context for this change." /></Field>
        <div className="form-actions"><button className="btn primary" disabled={saving}>{saving ? 'Saving…' : 'Save obligation'}</button><button type="button" className="btn secondary" onClick={() => setSelected(null)}>Cancel</button></div>
      </form>
      {selected.audit_entries?.length > 0 && <div className="audit-details expanded"><b>Audit history</b>{selected.audit_entries.map((entry: any) => <div className="audit-row" key={entry.id}><b>{label(entry.event_type)}</b><span>{label(entry.previous_status)} → {label(entry.new_status)}</span><small>{fmt(entry.created_at)}{entry.comment ? ` · ${entry.comment}` : ''}</small></div>)}</div>}
      <details className="source-text"><summary>View extracted source text</summary><blockquote>{selected.original_text || selected.claim || 'No source text returned.'}</blockquote><small>Verification: {label(selected.verification_status)} · Confidence: {selected.confidence ?? 'Not specified'}</small></details>
    </section></div>}
  </>;
}

function Team({ org, currentUserId }: { org: string; currentUserId: string }) {
  const { data, error, busy, reload } = useData<Member[]>(() => apiCall.members(org), [org]);
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('member');
  const [notice, setNotice] = useState('');
  const [saving, setSaving] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const members = data || [];
  const current = members.find(member => member.user_id === currentUserId);
  const canManage = current?.role === 'owner' || current?.role === 'admin';
  const isOwner = current?.role === 'owner';
  const invite = async (event: FormEvent) => {
    event.preventDefault(); setSaving(true); setNotice('');
    try {
      await apiCall.inviteMember(org, { email: email.trim(), role });
      setEmail(''); setRole('member'); setNotice('Member added. They must already have a registered PACTELLE account.'); reload();
    } catch (err) { setNotice(message(err)); } finally { setSaving(false); }
  };
  const changeRole = async (member: Member, nextRole: string) => {
    try { await apiCall.updateMemberRole(org, member.user_id, nextRole); setNotice(`${member.full_name}'s role updated.`); reload(); }
    catch (err) { setNotice(message(err)); }
  };
  const remove = async (member: Member) => {
    if (!window.confirm(`Remove ${member.full_name} from this workspace?`)) return;
    setRemoving(member.user_id); setNotice('');
    try { await apiCall.removeMember(org, member.user_id); setNotice(`${member.full_name} removed from the workspace.`); reload(); }
    catch (err) { setNotice(message(err)); } finally { setRemoving(null); }
  };
  return <>
    <Heading eyebrow="PEOPLE & PERMISSIONS" title="Team" desc="Manage who can access this organization workspace and what they can do." />
    {notice && <Notice>{notice}</Notice>}
    {canManage && <Panel className="pad invite-panel"><div><small>WORKSPACE ACCESS</small><h3>Invite an existing PACTELLE user</h3><p className="muted">The person must already have a registered account. This endpoint adds them directly; it does not send an email invitation.</p></div>
      <form className="invite-form" onSubmit={invite}><Field label="Account email"><input type="email" required value={email} onChange={e => setEmail(e.target.value)} placeholder="teammate@company.com" /></Field><Field label="Workspace role"><select value={role} onChange={e => setRole(e.target.value)}><option value="member">Member</option><option value="admin">Admin</option></select></Field><button className="btn primary" disabled={saving}><UserPlus size={15} />{saving ? 'Adding…' : 'Add member'}</button></form>
    </Panel>}
    {busy ? <Loading /> : error ? <Failure error={error} retry={reload} /> : <Panel className="pad"><div className="section-title"><div><small>WORKSPACE MEMBERS</small><h3>{members.length} people with access</h3></div><Users size={20} /></div>
      {members.map(member => <div className="member-row" key={member.user_id}><b className="member-avatar">{initials(member.full_name)}</b><div className="member-info"><b>{member.full_name}{member.user_id === currentUserId && <span className="you-tag">YOU</span>}</b><small>{member.email}</small></div>
        {isOwner && member.role !== 'owner' ? <select value={member.role} onChange={e => void changeRole(member, e.target.value)}><option value="member">Member</option><option value="admin">Admin</option></select> : <span className={`pill role-${member.role}`}>{member.role}</span>}
        {canManage && member.user_id !== currentUserId && member.role !== 'owner' && <button className="icon-button danger-icon" disabled={removing === member.user_id} onClick={() => void remove(member)} title="Remove member"><X size={16} /></button>}
        {member.role === 'owner' && <span className="muted owner-note">Workspace owner</span>}
      </div>)}
    </Panel>}
    <div className="permission-note"><ShieldCheck size={17} /><span>Role controls are enforced by the API. Owners manage admin roles; admins can manage members and invite users.</span></div>
  </>;
}

function Protected({ session, children }: { session: Session | null; children: ReactNode }) { return session ? children : <Navigate to="/login" replace />; }

export default function App() {
  const { session, save, logout } = useSession();
  return <Routes>
    <Route path="/login" element={session ? <Navigate to="/" /> : <Auth mode="login" save={save} />} />
    <Route path="/register" element={session ? <Navigate to="/" /> : <Auth mode="register" save={save} />} />
    <Route path="*" element={<Protected session={session}>{session ? <Shell session={session} logout={logout}><Routes>
      <Route path="/" element={<Dashboard org={session.organization.id} />} />
      <Route path="/contracts" element={<Contracts org={session.organization.id} />} />
      <Route path="/findings" element={<Findings org={session.organization.id} />} />
      <Route path="/actions" element={<Actions org={session.organization.id} />} />
      <Route path="/obligations" element={<Obligations org={session.organization.id} />} />
      <Route path="/team" element={<Team org={session.organization.id} currentUserId={session.user.id} />} />
      <Route path="*" element={<Navigate to="/" />} />
    </Routes></Shell> : null}</Protected>} />
  </Routes>;
}