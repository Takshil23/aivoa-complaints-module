/** Inline SVG icons — no icon dependency, and no external requests. */

const base = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
};

export function FlaskIcon({ size = 22 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...base} aria-hidden="true">
      <path d="M9 3h6M10 3v5.5L4.8 17A2 2 0 0 0 6.5 20h11a2 2 0 0 0 1.7-3L14 8.5V3" />
      <path d="M7 14h10" />
    </svg>
  );
}

export function PlusIcon({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...base} aria-hidden="true">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export function ShieldCheckIcon({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...base} aria-hidden="true">
      <path d="M12 3l7 3v5c0 4.5-3 8.2-7 10-4-1.8-7-5.5-7-10V6l7-3z" />
      <path d="M9 12l2 2 4-4" />
    </svg>
  );
}

export function SparkIcon({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...base} aria-hidden="true">
      <path d="M13 2L5 14h6l-1 8 8-12h-6l1-8z" />
    </svg>
  );
}

export function CheckIcon({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...base} aria-hidden="true">
      <path d="M4 12.5l5 5L20 6.5" />
    </svg>
  );
}

export function DocCheckIcon({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...base} aria-hidden="true">
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5z" />
      <path d="M8.5 13.5l2 2 4-4" />
    </svg>
  );
}

export function WarnIcon({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...base} aria-hidden="true">
      <path d="M12 4l9 16H3l9-16z" />
      <path d="M12 10v4M12 17.5h.01" />
    </svg>
  );
}

export function UserIcon({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...base} aria-hidden="true">
      <circle cx="12" cy="8.5" r="3.5" />
      <path d="M5 20c0-3.3 3.1-5.5 7-5.5s7 2.2 7 5.5" />
    </svg>
  );
}

export function PdfIcon({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...base} aria-hidden="true">
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5z" />
      <path d="M14 3v5h5" />
    </svg>
  );
}

export function PaperclipIcon({ size = 19 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...base} aria-hidden="true">
      <path d="M21 11.5l-8.6 8.6a5 5 0 0 1-7.1-7.1l8.9-8.8a3.4 3.4 0 0 1 4.8 4.8l-8.9 8.8a1.8 1.8 0 0 1-2.5-2.5l7.9-7.8" />
    </svg>
  );
}

export function SendCheckIcon({ size = 17 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...base} strokeWidth={2.2} aria-hidden="true">
      <path d="M4 12.5l5 5L20 6.5" />
    </svg>
  );
}

export const ICONS = {
  spark: SparkIcon,
  check: CheckIcon,
  'doc-check': DocCheckIcon,
  warn: WarnIcon,
};
