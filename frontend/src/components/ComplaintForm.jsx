import { useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import FormField from './FormField';
import RiskPanel from './RiskPanel';
import AiToolsBar from './AiToolsBar';
import {
  commitToLedger,
  dismissCommit,
  resetComplaint,
  selectHasComplaint,
  selectRecentlyChanged,
  selectRisk,
  selectSections,
  selectStatus,
} from '../store/complaintSlice';

function StatusPill({ status }) {
  if (status === 'ready_to_commit') {
    return (
      <span className="pill pill--ready">
        <span className="pill__dot" />
        Ready to Commit
      </span>
    );
  }
  return <span className="pill pill--pending">Pending Triage</span>;
}

export default function ComplaintForm() {
  const dispatch = useDispatch();
  const sections = useSelector(selectSections);
  const risk = useSelector(selectRisk);
  const status = useSelector(selectStatus);
  const changed = useSelector(selectRecentlyChanged);
  const hasComplaint = useSelector(selectHasComplaint);
  const { committing, lastCommitted, error } = useSelector((s) => s.complaint);

  const [unlocked, setUnlocked] = useState(false);

  return (
    <div>
      <header className="form-header">
        <div>
          <h1 className="form-header__title">Log Customer Complaint</h1>
          <p className="form-header__subtitle">API &amp; FDF Quality Assurance Module</p>
        </div>
        <StatusPill status={status} />
      </header>
      <div className="form-header__rule" />

      {lastCommitted && (
        <div className="committed" role="status">
          <div className="committed__head">
            <div>
              <div className="committed__number">{lastCommitted.complaintNumber}</div>
              <p className="committed__meta">
                Committed to the QMS ledger — {lastCommitted.productName} · batch{' '}
                {lastCommitted.batchLotNumber} · {lastCommitted.severity}
              </p>
            </div>
            <button
              type="button"
              className="link-button"
              onClick={() => dispatch(dismissCommit())}
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {sections.map((section) => (
        <section className="section" key={`${section.index}-${section.title}`}>
          <h2 className="section__title">
            {section.index}. {section.title}
          </h2>
          <div className="section__grid">
            {section.fields.map((field) => (
              <FormField
                key={field.key}
                field={field}
                changed={changed.includes(field.key)}
                unlocked={unlocked}
              />
            ))}
          </div>
        </section>
      ))}

      <RiskPanel risk={risk} changed={changed} />

      <button
        type="button"
        className="commit"
        disabled={!hasComplaint || committing || status !== 'ready_to_commit'}
        onClick={() => dispatch(commitToLedger())}
      >
        {committing ? 'Committing...' : 'Commit to QMS Ledger'}
      </button>

      {error && (
        <div className="form-error" role="alert">
          {error}
        </div>
      )}

      <AiToolsBar />

      <div className="aitools">
        <div className="aitools__row" style={{ justifyContent: 'space-between' }}>
          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              fontSize: 13,
              color: 'var(--slate-500)',
            }}
          >
            <input
              type="checkbox"
              checked={unlocked}
              onChange={(e) => setUnlocked(e.target.checked)}
            />
            Allow manual edits (off by default — the copilot drives this form)
          </label>
          <button
            type="button"
            className="link-button"
            onClick={() => dispatch(resetComplaint())}
          >
            Start a new session
          </button>
        </div>
      </div>
    </div>
  );
}
