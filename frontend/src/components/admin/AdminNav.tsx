import type { ComponentType } from "react";

import {
  AdminIcon,
  FlagIcon,
  PipelineIcon,
  QueueIcon,
  UsersIcon,
} from "@/components/layout/NavIcons";
import { TabBar, TabLink } from "@/components/layout/TabNav";

interface AdminTab {
  href: string;
  label: string;
  Icon: ComponentType<{ className?: string }>;
  /** Rendered as a count chip when non-zero; omitted entirely when undefined. */
  badgeKey?: "flags" | "review";
  /** The console root; without this it stays lit on every nested tab. */
  exact?: boolean;
}

const TABS: AdminTab[] = [
  { href: "/admin", label: "Overview", Icon: AdminIcon, exact: true },
  { href: "/admin/pipeline", label: "Pipeline", Icon: PipelineIcon },
  { href: "/admin/review", label: "Resolution queue", Icon: QueueIcon, badgeKey: "review" },
  { href: "/admin/flags", label: "Flag triage", Icon: FlagIcon, badgeKey: "flags" },
  { href: "/admin/users", label: "Accounts", Icon: UsersIcon },
];

export interface AdminBadges {
  flags: number;
  review: number;
}

/** Sub-navigation for the console. */
export function AdminNav({ badges }: { badges: AdminBadges }) {
  return (
    <TabBar label="Administration">
      {TABS.map((tab) => {
        const count = tab.badgeKey ? badges[tab.badgeKey] : 0;

        return (
          <li key={tab.href}>
            <TabLink href={tab.href} exact={tab.exact}>
              <tab.Icon />
              {tab.label}
              {count > 0 ? (
                <span className="label-caps rounded border border-rule bg-wash px-1.5 py-0.5 text-ink-secondary">
                  {count}
                </span>
              ) : null}
            </TabLink>
          </li>
        );
      })}
    </TabBar>
  );
}
