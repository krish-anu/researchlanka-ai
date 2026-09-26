import Link from "next/link";
import React from "react";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md";

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  href?: string;
  children: React.ReactNode;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary:
    "bg-[var(--primary)] text-[var(--on-primary)] border border-[var(--primary)] hover:bg-[var(--primary-hover)] focus-visible:ring-[var(--primary)]/30",

  secondary:
    "bg-[var(--surface)] text-[var(--ink-secondary)] border border-[var(--rule)] hover:bg-[var(--sunk)] hover:border-[var(--primary)] hover:text-[var(--primary)] focus-visible:ring-[var(--primary)]/30",

  ghost:
    "bg-transparent text-[var(--ink-secondary)] border border-transparent hover:bg-[var(--wash)] focus-visible:ring-[var(--primary)]/30",

  danger:
    "bg-[var(--danger)] text-[var(--on-danger)] border border-[var(--danger)] hover:bg-[var(--danger-hover)] focus-visible:ring-[var(--danger)]/30",
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: "h-9 px-3 text-xs",
  md: "h-10 px-3.5 text-sm",
};

const baseStyles =
  "inline-flex items-center justify-center gap-2 rounded-md font-medium whitespace-nowrap transition-[color,background-color,border-color,box-shadow,opacity] duration-[var(--motion-fast)] ease-[var(--motion-ease)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--page)]";

/** In-app pages use Link; API downloads and absolute URLs stay as plain anchors. */
function isAppNavigationHref(href: string): boolean {
  if (!href.startsWith("/") || href.startsWith("//")) return false;
  if (href.startsWith("/api/")) return false;
  return true;
}

function Spinner() {
  return (
    <span
      aria-hidden="true"
      className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent"
    />
  );
}

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  href,
  children,
  type = "button",
  className = "",
  ...props
}: ButtonProps) {
  const isDisabled = Boolean(disabled || loading);

  const classes = [
    baseStyles,
    sizeStyles[size],
    variantStyles[variant],
    isDisabled ? "pointer-events-none cursor-not-allowed opacity-50" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  if (href) {
    const content = (
      <>
        {loading ? <Spinner /> : null}
        {children}
      </>
    );

    if (isDisabled) {
      return (
        <span
          role="link"
          aria-disabled="true"
          aria-busy={loading || undefined}
          className={classes}
        >
          {content}
        </span>
      );
    }

    if (isAppNavigationHref(href)) {
      return (
        <Link
          href={href}
          aria-busy={loading || undefined}
          className={classes}
        >
          {content}
        </Link>
      );
    }

    return (
      <a href={href} aria-busy={loading || undefined} className={classes}>
        {content}
      </a>
    );
  }

  return (
    <button
      type={type}
      disabled={isDisabled}
      aria-busy={loading || undefined}
      className={classes}
      {...props}
    >
      {loading ? <Spinner /> : null}
      {children}
    </button>
  );
}

export default Button;
