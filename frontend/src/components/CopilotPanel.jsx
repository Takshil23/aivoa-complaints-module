import { useEffect, useRef, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import Message from './Message';
import Composer from './Composer';
import { FlaskIcon, PlusIcon, SparkIcon } from './icons';
import {
  selectIsStreaming,
  selectMessages,
  selectProgress,
  uploadDocument,
} from '../store/chatSlice';
import {
  resetComplaint,
  selectHasComplaint,
  selectStatus,
} from '../store/complaintSlice';

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

/**
 * Names the model actually answering.
 *
 * The assignment mandates `gemma2-9b-it`, which Groq decommissioned on
 * 2025-10-08. The backend still requests it first and falls through to a live
 * model, so this states the substitution on screen rather than leaving it in a
 * config file for someone to discover.
 */
function ModelLine({ llmEnabled, models }) {
  if (!llmEnabled || !models?.primary) return null;

  const requested = models.primary;
  const serving = models.activePrimary || requested;

  if (serving === requested) {
    return (
      <p className="copilot__model">
        Agent <code>{requested}</code>
      </p>
    );
  }

  return (
    <p
      className="copilot__model copilot__model--substituted"
      title={`${requested} was decommissioned by Groq; the model chain fell through to ${serving}.`}
    >
      <code>{requested}</code> retired by Groq — running <code>{serving}</code>
    </p>
  );
}

export default function CopilotPanel() {
  const dispatch = useDispatch();
  const messages = useSelector(selectMessages);
  const isStreaming = useSelector(selectIsStreaming);
  const progress = useSelector(selectProgress);
  const status = useSelector(selectStatus);
  const { llmEnabled, models } = useSelector((s) => s.complaint);
  const hasComplaint = useSelector(selectHasComplaint);

  const bodyRef = useRef(null);
  const [dragging, setDragging] = useState(false);

  const startNewChat = () => {
    // Discarding an uncommitted complaint is destructive and easy to misclick,
    // so confirm — but only when there is actually something to lose.
    const uncommitted = hasComplaint && status === 'ready_to_commit';
    if (uncommitted) {
      const ok = window.confirm(
        'Start a new chat?\n\nThe complaint currently on the form has not been ' +
          'committed to the QMS ledger and will be discarded.',
      );
      if (!ok) return;
    }
    dispatch(resetComplaint());
  };

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
          <ModelLine llmEnabled={llmEnabled} models={models} />
        </div>
        <div className="copilot__actions">
          <button
            type="button"
            className="newchat"
            onClick={startNewChat}
            disabled={isStreaming}
            title="Clear the transcript and the form, and start a fresh complaint"
          >
            <PlusIcon />
            New chat
          </button>
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
        </div>
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
