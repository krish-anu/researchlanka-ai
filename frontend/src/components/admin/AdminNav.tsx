import type { ComponentType } from "react";

import {
  AdminIcon,
  FlagIcon,
  PipelineIcon,
  QueueIcon,
  UsersIcon,
} from "@/components/layout/NavIcons";
import { TabBar, TabLink } from "@/components/layout/TabNav";
import type { Role } from "@/types/auth";

interface AdminTab {
  href: string;
  label: string;
  Icon: ComponentType<{ className?: string }>;
  /** Rendered as a count chip when non-zero; omitted entirely when undefined. */
  badgeKey?: "flags" | "review" | "aiReview";
  /** The console root; without this it stays lit on every nested tab. */
  exact?: boolean;
  roles: Role[];
}

const TABS: AdminTab[] = [
  { href: "/admin", label: "Overview", Icon: AdminIcon, exact: true, roles: ["admin"] },
  { href: "/admin/pipeline", label: "Pipeline", Icon: PipelineIcon, roles: ["admin"] },
  { href: "/admin/ai-review", label: "AI review", Icon: QueueIcon, badgeKey: "aiReview", roles: ["reviewer", "admin"] },
  { href: "/admin/review", label: "Resolution queue", Icon: QueueIcon, badgeKey: "review", roles: ["admin"] },
  { href: "/admin/flags", label: "Flag triage", Icon: FlagIcon, badgeKey: "flags", roles: ["admin"] },
  { href: "/admin/users", label: "Accounts", Icon: UsersIcon, roles: ["admin"] },
];

export interface AdminBadges {
  flags: number;
  review: number;
  aiReview: number;
}

/** Sub-navigation for the console. */
export function AdminNav({ badges, role }: { badges: AdminBadges; role: Role }) {
  return (
    <TabBar label="Administration">
      {TABS.filter((tab) => tab.roles.includes(role)).map((tab) => {
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
