import { ShieldCheckIcon } from './icons';

const SEVERITIES = ['Critical', 'Major', 'Minor'];

/**
 * "AI copilot risk assessment" — the panel the agent reasons into.
 *
 * The demo clips these values inside single-line inputs; here the long fields are
 * textareas so a QA officer can actually read the assessment. Deliberate
 * divergence, noted in the README.
 */
export default function RiskPanel({ risk, changed = [] }) {
  const severity = risk?.severity || '';
  const severityClass = SEVERITIES.includes(severity)
    ? `severity severity--${severity.toLowerCase()}`
    : 'severity';

  const flag = (key) => (changed.includes(key) ? 'field field--changed' : 'field');

  return (
    <section className="risk" aria-label="AI copilot risk assessment">
      <header className="risk__head">
        <span style={{ color: 'var(--indigo-500)', display: 'grid' }}>
          <ShieldCheckIcon />
        </span>
        <h2 className="risk__title">AI copilot risk assessment</h2>
      </header>

      <div className="risk__grid">
        <div className={flag('severity')}>
          <label className="field__label" htmlFor="risk-severity">
            Severity (Suggested)
          </label>
          {severity ? (
            <div className="field__input field__input--filled">
              <span className={severityClass}>
                <span className="severity__dot" />
                {severity}
              </span>
            </div>
          ) : (
            <input
              id="risk-severity"
              className="field__input"
              readOnly
              value=""
              placeholder="Awaiting AI reasoning..."
            />
          )}
        </div>

        <div className={flag('suggested_next_action')}>
          <label className="field__label" htmlFor="risk-action">
            Suggested Next Action
          </label>
          <textarea
            id="risk-action"
            className={`field__textarea ${
              risk?.suggested_next_action ? 'field__textarea--filled' : ''
            }`}
            style={{ minHeight: 48 }}
            rows={2}
            readOnly
            value={risk?.suggested_next_action || ''}
            placeholder="Awaiting AI reasoning..."
          />
        </div>

        <div className={`${flag('initial_risk_assessment')} field--full`}>
          <label className="field__label" htmlFor="risk-assessment">
            Initial Risk Assessment
          </label>
          <textarea
            id="risk-assessment"
            className={`field__textarea ${
              risk?.initial_risk_assessment ? 'field__textarea--filled' : ''
            }`}
            rows={3}
            readOnly
            value={risk?.initial_risk_assessment || ''}
            placeholder="The copilot will assess probable root cause and impact..."
          />
        </div>
      </div>
    </section>
  );
}
