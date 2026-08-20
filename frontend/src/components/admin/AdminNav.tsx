"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ComponentType } from "react";

import {
  AdminIcon,
  FlagIcon,
  PipelineIcon,
  QueueIcon,
  UsersIcon,
} from "@/components/layout/NavIcons";

interface AdminTab {
  href: string;
  label: string;
  Icon: ComponentType<{ className?: string }>;
  /** Rendered as a count chip when non-zero; omitted entirely when undefined. */
  badgeKey?: "flags" | "review";
}

const TABS: AdminTab[] = [
  { href: "/admin", label: "Overview", Icon: AdminIcon },
  { href: "/admin/pipeline", label: "Pipeline", Icon: PipelineIcon },
  { href: "/admin/review", label: "Resolution queue", Icon: QueueIcon, badgeKey: "review" },
  { href: "/admin/flags", label: "Flag triage", Icon: FlagIcon, badgeKey: "flags" },
  { href: "/admin/users", label: "Accounts", Icon: UsersIcon },
];

export interface AdminBadges {
  flags: number;
  review: number;
}

/**
 * Sub-navigation for the console.
 *
 * Horizontal rather than a second rail: the app already spends 288px on the
 * primary nav, and a nested vertical rail inside the content column would leave
 * the tables it sits above too narrow to read.
 */
export function AdminNav({ badges }: { badges: AdminBadges }) {
  const pathname = usePathname() ?? "/admin";

  return (
    <nav aria-label="Administration" className="border-b border-rule">
      <ul className="scroll-x flex gap-1">
        {TABS.map((tab) => {
          const active =
            tab.href === "/admin"
              ? pathname === "/admin"
              : pathname.startsWith(tab.href);
          const count = tab.badgeKey ? badges[tab.badgeKey] : 0;

          return (
            <li key={tab.href}>
              <Link
                href={tab.href}
                aria-current={active ? "page" : undefined}
                className={`-mb-px flex items-center gap-2 whitespace-nowrap border-b-2 px-3 py-2.5 text-body-sm transition-colors ${
                  active
                    ? "border-primary font-semibold text-primary"
                    : "border-transparent text-ink-secondary hover:text-primary"
                }`}
              >
                <tab.Icon />
                {tab.label}
                {count > 0 ? (
                  <span className="label-caps rounded border border-rule bg-wash px-1.5 py-0.5 text-ink-secondary">
                    {count}
                  </span>
                ) : null}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
