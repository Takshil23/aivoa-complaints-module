import { useDispatch, useSelector } from 'react-redux';
import { closeAiFeature, selectAiFeature } from '../store/chatSlice';

const TITLES = {
  completeness: 'Complaint Completeness Checker',
  'root-cause': 'Root Cause Recommendation',
  capa: 'CAPA Recommendation',
  duplicates: 'Duplicate Complaint Detection',
  summary: 'Complaint Summary',
};

function Block({ title, children }) {
  if (!children) return null;
  return (
    <div className="ai-block">
      <h4 className="ai-block__title">{title}</h4>
      {children}
    </div>
  );
}

function List({ items }) {
  if (!items?.length) return null;
  return (
    <ul className="ai-list">
      {items.map((item, index) => (
        <li key={index}>{typeof item === 'string' ? item : JSON.stringify(item)}</li>
      ))}
    </ul>
  );
}

function tagClass(value) {
  return `tag tag--${String(value || '').toLowerCase()}`;
}

function Completeness({ result }) {
  return (
    <>
      <div className="ai-score">
        <span className="ai-score__value">{result.score}</span>
        <span>
          / 100 · <span className={tagClass(result.verdict)}>{result.verdict}</span>
        </span>
      </div>
      <p style={{ marginTop: 0 }}>{result.summary}</p>

      {result.missing?.length > 0 && (
        <Block title="Missing or weak fields">
          <table className="ai-table">
            <thead>
              <tr>
                <th>Field</th>
                <th>Why a reviewer needs it</th>
              </tr>
            </thead>
            <tbody>
              {result.missing.map((row, index) => (
                <tr key={index}>
                  <td>{row.field}</td>
                  <td>{row.why}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Block>
      )}

      {result.blocking?.length > 0 && (
        <Block title="Blocking before commit">
          <List items={result.blocking} />
        </Block>
      )}
    </>
  );
}

function RootCause({ result }) {
  return (
    <>
      {result.most_likely && (
        <div className="banner">
          <strong>Most likely:</strong> {result.most_likely}
        </div>
      )}
      <table className="ai-table">
        <thead>
          <tr>
            <th>Probable cause</th>
            <th>Category</th>
            <th>Likelihood</th>
            <th>Confirming test</th>
          </tr>
        </thead>
        <tbody>
          {(result.hypotheses || []).map((h, index) => (
            <tr key={index}>
              <td>
                {h.cause}
                {h.evidence && (
                  <div style={{ color: 'var(--slate-500)', fontSize: 13, marginTop: 4 }}>
                    {h.evidence}
                  </div>
                )}
              </td>
              <td>{h.category}</td>
              <td>
                <span className={tagClass(h.likelihood)}>{h.likelihood}</span>
              </td>
              <td>{h.test}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function Capa({ result }) {
  return (
    <>
      <div className="banner">
        <strong>CAPA {result.capa_required ? 'required' : 'not required'}</strong>
        {result.target_closure_days
          ? ` · target closure ${result.target_closure_days} days`
          : ''}
        {result.justification ? ` — ${result.justification}` : ''}
      </div>
      <Block title="Immediate containment">
        <List items={result.immediate_actions} />
      </Block>
      <Block title="Investigation plan">
        <List items={result.investigation_plan} />
      </Block>
      <Block title="Corrective actions">
        <List items={result.corrective_actions} />
      </Block>
      <Block title="Preventive actions">
        <List items={result.preventive_actions} />
      </Block>
    </>
  );
}

function Duplicates({ result }) {
  return (
    <>
      <div className="banner">{result.summary}</div>
      {result.matches?.length > 0 && (
        <table className="ai-table">
          <thead>
            <tr>
              <th>Complaint</th>
              <th>Customer</th>
              <th>Product</th>
              <th>Severity</th>
            </tr>
          </thead>
          <tbody>
            {result.matches.map((m) => (
              <tr key={m.id}>
                <td>{m.complaintNumber}</td>
                <td>{m.customerName}</td>
                <td>{m.productName}</td>
                <td>
                  <span className={tagClass(m.severity)}>{m.severity}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

function Summary({ result }) {
  return (
    <>
      <h3 style={{ marginTop: 0 }}>{result.headline}</h3>
      <p>{result.summary}</p>
      <div className="banner" style={{ marginTop: 18, marginBottom: 0 }}>
        <strong>
          {result.regulatory_reportable
            ? 'Potentially reportable to a health authority'
            : 'Not currently reportable'}
        </strong>
        {result.regulatory_note ? ` — ${result.regulatory_note}` : ''}
      </div>
    </>
  );
}

const RENDERERS = {
  completeness: Completeness,
  'root-cause': RootCause,
  capa: Capa,
  duplicates: Duplicates,
  summary: Summary,
};

export default function AiFeatureModal() {
  const dispatch = useDispatch();
  const { name, loading, result, error } = useSelector(selectAiFeature);

  if (!name) return null;

  const Renderer = RENDERERS[name];
  const close = () => dispatch(closeAiFeature());

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div className="modal">
        <header className="modal__head">
          <h3 className="modal__title">{TITLES[name] || name}</h3>
          <button type="button" className="modal__close" onClick={close}>
            ×<span className="sr-only">Close</span>
          </button>
        </header>
        <div className="modal__body">
          {loading && (
            <div className="center-pad">
              <div className="spinner" />
              <span>Reasoning over the complaint record...</span>
            </div>
          )}
          {error && <div className="form-error">{error}</div>}
          {!loading && !error && result && Renderer && <Renderer result={result} />}
          {!loading && !error && result && !Renderer && (
            <pre style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>
              {JSON.stringify(result, null, 2)}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
