import { useRef, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { PaperclipIcon, SendCheckIcon } from './icons';
import {
  clearChatError,
  selectChatError,
  selectIsStreaming,
  sendMessage,
  uploadDocument,
} from '../store/chatSlice';

const ACCEPT = '.pdf,.txt,.eml,.md';

export default function Composer() {
  const dispatch = useDispatch();
  const isStreaming = useSelector(selectIsStreaming);
  const error = useSelector(selectChatError);
  const [text, setText] = useState('');
  const [focused, setFocused] = useState(false);
  const fileRef = useRef(null);
  const areaRef = useRef(null);

  const canSend = text.trim().length > 0 && !isStreaming;

  const submit = () => {
    if (!canSend) return;
    dispatch(sendMessage(text.trim()));
    setText('');
    if (areaRef.current) areaRef.current.style.height = 'auto';
  };

  const onKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  const onInput = (event) => {
    setText(event.target.value);
    const el = event.target;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 128)}px`;
  };

  const onFile = (event) => {
    const file = event.target.files?.[0];
    if (file) dispatch(uploadDocument(file));
    event.target.value = '';
  };

  return (
    <>
      {error && (
        <div className="chat-error" role="alert" style={{ marginBottom: 12 }}>
          <span>{error}</span>
          <button
            type="button"
            className="link-button"
            onClick={() => dispatch(clearChatError())}
          >
            Dismiss
          </button>
        </div>
      )}

      <div className={`composer ${focused || text ? '' : 'composer--idle'}`}>
        <button
          type="button"
          className="composer__attach"
          title="Attach a complaint PDF, email or text file"
          disabled={isStreaming}
          onClick={() => fileRef.current?.click()}
        >
          <PaperclipIcon />
          <span className="sr-only">Attach a file</span>
        </button>
        <input
          ref={fileRef}
          type="file"
          accept={ACCEPT}
          hidden
          onChange={onFile}
        />

        <textarea
          ref={areaRef}
          className="composer__input"
          rows={1}
          placeholder="Type a message or paste a complaint..."
          value={text}
          disabled={isStreaming}
          onChange={onInput}
          onKeyDown={onKeyDown}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
        />

        <button
          type="button"
          className="composer__send"
          disabled={!canSend}
          onClick={submit}
          title="Send"
        >
          <SendCheckIcon />
          <span className="sr-only">Send</span>
        </button>
      </div>

      <div className="composer__hint">
        <span>Enter to send · Shift+Enter for a new line</span>
        <span>PDF · TXT · EML</span>
      </div>
    </>
  );
}
