import type { InputHTMLAttributes, ReactNode } from "react";

type Props = InputHTMLAttributes<HTMLInputElement> & {
  id: string;
  label: string;
  hint?: ReactNode;
  error?: string | null;
  labelAside?: ReactNode;
};

/** Labelled text input. The outline uses --input-border (>= 3:1, WCAG 1.4.11). */
export function Field({ id, label, hint, error, labelAside, className = "", ...input }: Props) {
  const describedBy = [hint ? `${id}-hint` : null, error ? `${id}-error` : null].filter(Boolean).join(" ") || undefined;
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <label htmlFor={id} className="text-small font-semibold text-ink">
          {label}
        </label>
        {labelAside}
      </div>
      <input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={`min-h-10 w-full rounded-md border bg-surface px-3 py-2 text-body text-ink ${
          error ? "border-err-fg" : "border-line-input"
        } ${className}`}
        {...input}
      />
      {hint && (
        <p id={`${id}-hint`} className="text-cap text-ink-3">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} className="text-small text-err-fg">
          {error}
        </p>
      )}
    </div>
  );
}
