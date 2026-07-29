import { ICONS, PdfIcon, UserIcon, CheckIcon } from './icons';

function formatBytes(bytes) {
  if (!bytes) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const TOOL_LABELS = {
  log_complaint: 'log_complaint',
  edit_complaint: 'edit_complaint',
  extract_document: 'extract_document',
  answer_question: 'answer_question',
};

export default function Message({ message }) {
  const isUser = message.role === 'user';

  // File attachment card
  if (message.kind === 'file') {
    const { filename, sizeBytes, fileType } = message.meta || {};
    return (
      <div className="msg msg--user">
        <div className="msg__avatar">
          <UserIcon />
        </div>
        <div className="attach">
          <div className="attach__icon">
            <PdfIcon />
          </div>
          <div style={{ minWidth: 0 }}>
            <div className="attach__name" title={filename || message.content}>
              {filename || message.content}
            </div>
            <div className="attach__meta">
              {fileType || 'Document'}
              {sizeBytes ? ` · ${formatBytes(sizeBytes)}` : ''}
            </div>
          </div>
        </div>
      </div>
    );
  }

  const Icon = isUser ? UserIcon : ICONS[message.meta?.icon] || CheckIcon;
  const tool = message.meta?.toolUsed;

  return (
    <div className={`msg msg--${isUser ? 'user' : 'assistant'}`}>
      <div className="msg__avatar">
        <Icon />
      </div>
      <div className="msg__bubble">
        {message.content}
        {!isUser && tool && TOOL_LABELS[tool] && (
          <span className="msg__tool">tool · {TOOL_LABELS[tool]}</span>
        )}
      </div>
    </div>
  );
}
