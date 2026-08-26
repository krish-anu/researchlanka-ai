"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

/**
 * Horizontal sub-navigation, shared by the console and the account area.
 *
 * Horizontal rather than a second rail: the app already spends 288px on the
 * primary nav, and a nested vertical rail inside the content column would leave
 * the tables it sits above too narrow to read.
 */
export function TabBar({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <nav aria-label={label} className="border-b border-rule">
      <ul className="scroll-x flex gap-1">{children}</ul>
    </nav>
  );
}

/**
 * One tab, which resolves its own active state.
 *
 * `exact` is for section roots — `/account` would otherwise light up while the
 * reader is on `/account/saved`, marking two tabs as current at once.
 */
export function TabLink({
  href,
  exact = false,
  children,
}: {
  href: string;
  exact?: boolean;
  children: ReactNode;
}) {
  const pathname = usePathname() ?? "/";
  const active = exact ? pathname === href : pathname.startsWith(href);

  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={`-mb-px flex items-center gap-2 whitespace-nowrap border-b-2 px-3 py-2.5 text-body-sm transition-colors ${
        active
          ? "border-primary font-semibold text-primary"
          : "border-transparent text-ink-secondary hover:text-primary"
      }`}
    >
      {children}
    </Link>
  );
}
