import { useDispatch, useSelector } from 'react-redux';
import { runAiFeature } from '../store/chatSlice';
import { selectHasComplaint } from '../store/complaintSlice';
import AiFeatureModal from './AiFeatureModal';

const FEATURES = [
  { id: 'completeness', label: 'Completeness Checker' },
  { id: 'root-cause', label: 'Root Cause Recommendation' },
  { id: 'capa', label: 'CAPA Recommendation' },
  { id: 'duplicates', label: 'Duplicate Detection' },
  { id: 'summary', label: 'Complaint Summary' },
];

export default function AiToolsBar() {
  const dispatch = useDispatch();
  const hasComplaint = useSelector(selectHasComplaint);
  const { loading } = useSelector((s) => s.chat.aiFeature);

  return (
    <>
      <div className="aitools">
        <div className="aitools__label">Additional AI analysis</div>
        <div className="aitools__row">
          {FEATURES.map((feature) => (
            <button
              key={feature.id}
              type="button"
              className="chip"
              disabled={!hasComplaint || loading}
              onClick={() => dispatch(runAiFeature(feature.id))}
              title={
                hasComplaint
                  ? `Run ${feature.label}`
                  : 'Log a complaint first'
              }
            >
              {feature.label}
            </button>
          ))}
        </div>
      </div>
      <AiFeatureModal />
    </>
  );
}

export { FEATURES };
