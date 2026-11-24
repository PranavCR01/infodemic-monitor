import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost";

const VARIANT: Record<Variant, string> = {
  primary: "bg-primary text-ink-on-primary hover:bg-primary-hover border-transparent",
  secondary: "bg-surface text-ink border-line-input hover:bg-surface-sunken",
  ghost: "bg-transparent text-primary border-transparent hover:bg-primary-subtle",
};

export function buttonClass(variant: Variant = "primary", size: "md" | "sm" = "md", extra = "") {
  return `inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md border font-semibold disabled:cursor-not-allowed disabled:opacity-50 ${
    size === "sm" ? "min-h-8 px-2.5 text-small" : "min-h-10 px-4 text-body"
  } ${VARIANT[variant]} ${extra}`;
}

type Props = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "md" | "sm"; children: ReactNode };

export function Button({ variant = "primary", size = "md", className = "", type = "button", ...rest }: Props) {
  return <button type={type} className={buttonClass(variant, size, className)} {...rest} />;
}
