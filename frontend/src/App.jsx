import { useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import ComplaintForm from './components/ComplaintForm';
import CopilotPanel from './components/CopilotPanel';
import {
  bootstrapSession,
  clearRecentlyChanged,
  selectRecentlyChanged,
  selectSessionId,
} from './store/complaintSlice';

export default function App() {
  const dispatch = useDispatch();
  const sessionId = useSelector(selectSessionId);
  const changed = useSelector(selectRecentlyChanged);
  const error = useSelector((s) => s.complaint.error);

  useEffect(() => {
    dispatch(bootstrapSession());
  }, [dispatch]);

  // Clear the flash highlight after the animation finishes.
  useEffect(() => {
    if (!changed.length) return undefined;
    const timer = setTimeout(() => dispatch(clearRecentlyChanged()), 1800);
    return () => clearTimeout(timer);
  }, [changed, dispatch]);

  if (!sessionId) {
    return (
      <div className="center-pad" style={{ height: '100vh' }}>
        {error ? (
          <>
            <strong style={{ color: '#991b1b' }}>Cannot reach the backend</strong>
            <p style={{ maxWidth: 420, textAlign: 'center' }}>{error}</p>
            <p style={{ fontSize: 13 }}>
              Start it with{' '}
              <code>uvicorn app.main:app --reload</code> in <code>backend/</code>.
            </p>
          </>
        ) : (
          <>
            <div className="spinner" />
            <span>Starting the complaint session...</span>
          </>
        )}
      </div>
    );
  }

  return (
    <div className="app">
      <main className="app__left">
        <ComplaintForm />
      </main>
      <aside className="app__right">
        <CopilotPanel />
      </aside>
    </div>
  );
}
