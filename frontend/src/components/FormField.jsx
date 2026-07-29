import { useDispatch } from 'react-redux';
import { setFieldValue } from '../store/complaintSlice';

/**
 * Renders one field from the agent-supplied schema.
 *
 * Read-only by default: the assignment requires the form be filled through the
 * copilot, not by hand. `unlocked` is the deliberate escape hatch a QA officer
 * would need in reality, and is off unless the user turns it on.
 */
export default function FormField({ field, changed, unlocked }) {
  const dispatch = useDispatch();
  const { key, label, type, value, placeholder, options, inferred, fullWidth } = field;

  const filled = Boolean(value && String(value).trim());
  const readOnly = !unlocked;

  const onChange = (event) =>
    dispatch(setFieldValue({ key, value: event.target.value }));

  const classes = [
    'field',
    fullWidth ? 'field--full' : '',
    changed ? 'field--changed' : '',
  ]
    .filter(Boolean)
    .join(' ');

  const inputClass = (suffix) =>
    `field__${suffix} ${filled ? `field__${suffix}--filled` : ''}`.trim();

  return (
    <div className={classes}>
      <label className="field__label" htmlFor={`field-${key}`}>
        {label}
        {inferred && filled && (
          <span
            className="field__badge"
            title="Inferred by the copilot from pharmaceutical context — not stated verbatim in the source. Confirm before committing."
          >
            AI inferred
          </span>
        )}
      </label>

      {type === 'textarea' ? (
        <textarea
          id={`field-${key}`}
          className={inputClass('textarea')}
          value={value || ''}
          placeholder={placeholder}
          readOnly={readOnly}
          onChange={onChange}
          rows={3}
        />
      ) : type === 'select' ? (
        <select
          id={`field-${key}`}
          className={inputClass('select')}
          value={value || ''}
          disabled={readOnly}
          onChange={onChange}
        >
          <option value="">{placeholder || 'Select...'}</option>
          {(options || []).map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
          {/* keep an agent-supplied value that is not in the option list */}
          {value && !(options || []).includes(value) && (
            <option value={value}>{value}</option>
          )}
        </select>
      ) : (
        <input
          id={`field-${key}`}
          className={inputClass('input')}
          type="text"
          value={value || ''}
          placeholder={placeholder}
          readOnly={readOnly}
          onChange={onChange}
        />
      )}
    </div>
  );
}
