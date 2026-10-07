"use client";

import { useEffect, useId, useState, type ReactNode } from "react";

export type ProfileTabId =
  | "overview"
  | "publications"
  | "network"
  | "topics"
  | "researchers"
  | "collaboration"
  | "method";

const TAB_LABELS: Record<ProfileTabId, string> = {
  overview: "Overview",
  publications: "Publications",
  network: "Network",
  topics: "Topics",
  researchers: "Researchers",
  collaboration: "Collaboration",
  method: "Method",
};

/**
 * Sticky profile chrome: title, optional subtitle, metric strip, actions,
 * then in-page tabs that show/hide section panels without a full navigation.
 */
export function ProfileHeader({
  title,
  subtitle,
  breadcrumbs,
  metrics,
  actions,
  notice,
}: {
  title: string;
  subtitle?: string;
  breadcrumbs?: ReactNode;
  metrics?: ReactNode;
  actions?: ReactNode;
  notice?: ReactNode;
}) {
  return (
    <header className="profile-header mb-2 space-y-3 border-b border-rule px-1 py-3">
      {breadcrumbs}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="font-display text-profile-title text-ink">{title}</h1>
          {subtitle ? (
            <p className="mt-1 text-body-sm text-ink-secondary">{subtitle}</p>
          ) : null}
        </div>
        {actions ? <div className="flex shrink-0 flex-wrap gap-2">{actions}</div> : null}
      </div>
      {notice}
      {metrics}
    </header>
  );
}

export function ProfileTabs({
  tabs,
  defaultTab = "overview",
}: {
  tabs: { id: ProfileTabId; content: ReactNode; hidden?: boolean }[];
  defaultTab?: ProfileTabId;
}) {
  const visible = tabs.filter((tab) => !tab.hidden);
  const visibleIds = visible.map((tab) => tab.id).join("|");
  const initial =
    visible.find((tab) => tab.id === defaultTab)?.id ?? visible[0]?.id ?? "overview";
  const [active, setActive] = useState<ProfileTabId>(initial);
  const baseId = useId();

  useEffect(() => {
    const ids = visibleIds.split("|").filter(Boolean) as ProfileTabId[];
    if (ids.length && !ids.includes(active)) {
      setActive(ids[0]);
    }
  }, [active, visibleIds]);

  return (
    <div>
      <div
        className="profile-tabs sticky top-14 z-10 mb-4 flex flex-wrap gap-1 border-b border-rule bg-page/95 py-1 backdrop-blur-sm"
        role="tablist"
        aria-label="Profile sections"
      >
        {visible.map((tab) => {
          const selected = tab.id === active;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`${baseId}-${tab.id}`}
              aria-selected={selected}
              aria-controls={`${baseId}-panel-${tab.id}`}
              className={`interactive -mb-px border-b-2 px-3 py-2 text-body-sm ${selected
                  ? "border-primary font-medium text-primary"
                  : "border-transparent text-ink-secondary hover:text-ink"
                }`}
              onClick={() => setActive(tab.id)}
            >
              {TAB_LABELS[tab.id]}
            </button>
          );
        })}
      </div>
      {visible.map((tab) => (
        <div
          key={tab.id}
          role="tabpanel"
          id={`${baseId}-panel-${tab.id}`}
          aria-labelledby={`${baseId}-${tab.id}`}
          hidden={tab.id !== active}
          className="flex flex-col gap-5"
        >
          {tab.content}
        </div>
      ))}
    </div>
  );
}
