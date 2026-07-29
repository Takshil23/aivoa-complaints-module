import { useEffect, useRef, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import Message from './Message';
import Composer from './Composer';
import { FlaskIcon, SparkIcon } from './icons';
import {
  selectIsStreaming,
  selectMessages,
  selectProgress,
  uploadDocument,
} from '../store/chatSlice';
import { selectStatus } from '../store/complaintSlice';

function ProgressCard({ progress }) {
  return (
    <div className="msg msg--assistant">
      <div className="msg__avatar">
        <SparkIcon />
      </div>
      <div className="progress">
        <div className="progress__label">{progress.label}</div>
        <div
          className="progress__track"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(progress.progress * 100)}
        >
          <div
            className="progress__bar"
            style={{ width: `${Math.max(6, progress.progress * 100)}%` }}
          />
        </div>
      </div>
    </div>
  );
}

function TypingCard() {
  return (
    <div className="msg msg--assistant">
      <div className="msg__avatar">
        <SparkIcon />
      </div>
      <div className="msg__bubble">
        <span className="dots">
          <span />
          <span />
          <span />
        </span>
      </div>
    </div>
  );
}

export default function CopilotPanel() {
  const dispatch = useDispatch();
  const messages = useSelector(selectMessages);
  const isStreaming = useSelector(selectIsStreaming);
  const progress = useSelector(selectProgress);
  const status = useSelector(selectStatus);
  const { llmEnabled, models } = useSelector((s) => s.complaint);

  const bodyRef = useRef(null);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.length, progress, isStreaming]);

  const onDrop = (event) => {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (file && !isStreaming) dispatch(uploadDocument(file));
  };

  const dotClass = [
    'state-dot',
    status === 'ready_to_commit' && !isStreaming ? 'state-dot--ready' : '',
    isStreaming ? 'state-dot--busy' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <>
      <header className="copilot__head">
        <div>
          <div className="copilot__brand">
            <span style={{ color: 'var(--indigo-500)', display: 'grid' }}>
              <FlaskIcon />
            </span>
            <h2 className="copilot__title">AIVOA Copilot</h2>
          </div>
          <p className="copilot__hint">Drop complaint files or paste text below.</p>
        </div>
        <span
          className={dotClass}
          title={
            isStreaming
              ? 'Working...'
              : status === 'ready_to_commit'
                ? 'Ready to commit'
                : 'Idle'
          }
        />
      </header>

      <div
        className="copilot__body"
        ref={bodyRef}
        style={{ position: 'relative' }}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        {dragging && <div className="dropzone-overlay">Drop the complaint file</div>}

        {!llmEnabled && (
          <div className="banner">
            No <code>GROQ_API_KEY</code> configured — running on the deterministic
            fallback extractor. Add a key to <code>backend/.env</code> to enable the{' '}
            {models?.primary || 'gemma2-9b-it'} agent.
          </div>
        )}

        {messages.map((message) => (
          <Message key={message.id} message={message} />
        ))}

        {progress ? (
          <ProgressCard progress={progress} />
        ) : isStreaming ? (
          <TypingCard />
        ) : null}
      </div>

      <footer className="copilot__foot">
        <Composer />
        <p className="copilot__byline">POWERED BY LANGGRAPH</p>
      </footer>
    </>
  );
}
