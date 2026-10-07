"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type ComponentType } from "react";

import { AccountMenu } from "@/components/auth/AccountMenu";
import { RoleBadge } from "@/components/auth/RoleBadge";
import {
  AdminIcon,
  CloseIcon,
  DashboardIcon,
  DataQualityIcon,
  FlagIcon,
  NetworkIcon,
  InstitutionsIcon,
  MenuIcon,
  PipelineIcon,
  PublicationsIcon,
  QueueIcon,
  ResearchersIcon,
  SearchIcon,
  TopicsIcon,
  UsersIcon,
} from "@/components/layout/NavIcons";
import { SearchBox } from "@/components/search/SearchBox";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import type { AdminNavBadges } from "@/services/admin/navBadges";
import type { Role, Viewer } from "@/types/auth";
import { IS_CSE_UOM_SITE, SITE_COPY } from "@/config/site";

/** Directory list pages own a contextual SearchBox — hide the global duplicate. */
function hasContextualPageSearch(pathname: string): boolean {
  return (
    pathname === "/publications" ||
    pathname === "/researchers" ||
    pathname === "/institutions"
  );
}

const GLOBAL_SEARCH_TYPES = [
  "publication",
  "journal",
  "researcher",
  "institution",
] as const;

interface NavLink {
  href: string;
  label: string;
  Icon: ComponentType<{ className?: string }>;
  /** Present only for administrators; the public sections have no requirement. */
  adminOnly?: boolean;
  /** Section roots must not stay lit on every nested route. */
  exact?: boolean;
  /** Pending count. Omitted from the rail when zero. */
  badge?: number;
  roles?: Role[];
}

interface NavSection {
  id: string;
  label: string;
  links: NavLink[];
}

/**
 * Grouped IA for first-time visitors: scan by job (explore content, find
 * people/places, see connections, assess trust) rather than 8 peer items.
 */
const NAV_SECTIONS: NavSection[] = [
  {
    id: "explore",
    label: "Explore",
    links: [
      { href: "/", label: "Overview", Icon: DashboardIcon },
      { href: "/publications", label: "AI publications", Icon: PublicationsIcon },
      { href: "/topics", label: "Topics & fields", Icon: TopicsIcon },
    ],
  },
  {
    id: "people",
    label: "People & places",
    links: [
      { href: "/researchers", label: "Researchers", Icon: ResearchersIcon },
      { href: "/institutions", label: "Institutions", Icon: InstitutionsIcon },
    ],
  },
  {
    id: "connections",
    label: "Connections",
    links: [{ href: "/collaboration", label: "Collaboration", Icon: NetworkIcon }],
  },
  {
    id: "trust",
    label: "Trust",
    links: [{ href: "/data-quality", label: "Data quality", Icon: DataQualityIcon }],
  },
];

const ADMIN_LINKS: NavLink[] = [
  { href: "/admin", label: "Overview", Icon: AdminIcon, exact: true, roles: ["admin"] },
  { href: "/admin/pipeline", label: "Pipeline", Icon: PipelineIcon, roles: ["admin"] },
  { href: "/admin/ai-review", label: "AI review", Icon: QueueIcon, roles: ["admin", "reviewer"] },
  { href: "/admin/review", label: "Resolution queue", Icon: QueueIcon, roles: ["admin"] },
  { href: "/admin/flags", label: "Flag triage", Icon: FlagIcon, roles: ["admin"] },
  { href: "/admin/users", label: "Accounts", Icon: UsersIcon, roles: ["admin"] },
];

const PUBLIC_SITE_LINK: NavLink = {
  href: "/",
  label: "Public site",
  Icon: DashboardIcon,
  exact: true,
};

function adminSection(role: Role, badges?: AdminNavBadges): NavSection | null {
  const counts: Record<string, number> = {
    "/admin/ai-review": badges?.aiReview ?? 0,
    "/admin/review": badges?.review ?? 0,
    "/admin/flags": badges?.flags ?? 0,
  };
  const links = ADMIN_LINKS.filter((link) => link.roles?.includes(role)).map((link) => ({
    ...link,
    badge: counts[link.href] ?? 0,
  }));
  if (links.length === 0) return null;
  return { id: "admin", label: "Admin", links: [...links, PUBLIC_SITE_LINK] };
}

/** One door into the console. The six destinations live only inside /admin. */
function adminEntry(role: Role, badges?: AdminNavBadges): NavSection | null {
  if (role === "admin") {
    const waiting = (badges?.flags ?? 0) + (badges?.review ?? 0) + (badges?.aiReview ?? 0);
    return {
      id: "admin",
      label: "Admin",
      links: [{ href: "/admin", label: "Administration", Icon: AdminIcon, exact: true, badge: waiting }],
    };
  }
  if (role === "reviewer") {
    return {
      id: "admin",
      label: "Admin",
      links: [{
        href: "/admin/ai-review",
        label: "AI review",
        Icon: QueueIcon,
        badge: badges?.aiReview ?? 0,
      }],
    };
  }
  return null;
}

function sectionsForViewer(
  viewer: Viewer,
  badges: AdminNavBadges | undefined,
  pathname: string,
): NavSection[] {
  if (pathname.startsWith("/admin")) {
    const admin = adminSection(viewer.role, badges);
    return admin ? [admin] : [];
  }

  const sections = NAV_SECTIONS.map((section) => ({
    ...section,
    links: section.links.filter((link) => !link.adminOnly || viewer.role === "admin"),
  })).filter((section) => section.links.length > 0);

  const entry = adminEntry(viewer.role, badges);
  return entry ? [...sections, entry] : sections;
}

/** "/" and exact section roots match themselves; other entries own detail routes. */
function isActive(pathname: string, link: Pick<NavLink, "href" | "exact">): boolean {
  if (link.href === "/" || link.exact) return pathname === link.href;
  return pathname.startsWith(link.href);
}

function sectionForPath(
  pathname: string,
  viewer: Viewer,
  badges?: AdminNavBadges,
): { section: string; label: string } {
  for (const section of sectionsForViewer(viewer, badges, pathname)) {
    for (const link of section.links) {
      if (isActive(pathname, link)) {
        return { section: section.label, label: link.label };
      }
    }
  }
  if (pathname.startsWith("/account")) {
    return { section: "Account", label: "My workspace" };
  }
  return { section: "Workspace", label: "Account" };
}

function NavItem({
  link,
  active,
  onNavigate,
}: {
  link: NavLink;
  active: boolean;
  onNavigate?: () => void;
}) {
  const { href, label, Icon, badge = 0 } = link;
  return (
    <Link
      href={href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className="nav-item"
    >
      <Icon />
      <span>{label}</span>
      {badge > 0 ? (
        <span className="label-caps ml-auto rounded border border-rule bg-sunk px-1.5 py-0.5 text-ink-secondary">
          {badge}
        </span>
      ) : null}
    </Link>
  );
}

function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/" className="brand" aria-label={`${SITE_COPY.fullName} overview`}>
      <span className="brand-mark"><NetworkIcon /></span>
      <span><span className="brand-name">{SITE_COPY.shortName}{IS_CSE_UOM_SITE ? " " : null}<span className="text-primary">{SITE_COPY.accentName}</span></span>
      {!compact ? <span className="brand-tagline">{SITE_COPY.tagline}</span> : null}</span>
    </Link>
  );
}

function NavList({
  viewer,
  badges,
  onNavigate,
}: {
  viewer: Viewer;
  badges?: AdminNavBadges;
  onNavigate?: () => void;
}) {
  const pathname = usePathname() ?? "/";
  const sections = sectionsForViewer(viewer, badges, pathname);

  return (
    <div className="nav-sections">
      {sections.map((section) => {
        const headingId = `nav-section-${section.id}`;
        return (
          <section key={section.id} className="nav-section" aria-labelledby={headingId}>
            <p id={headingId} className="nav-section-label">
              {section.label}
            </p>
            <ul className="nav-section-list">
              {section.links.map((link) => (
                <li key={link.href}>
                  <NavItem
                    link={link}
                    active={isActive(pathname, link)}
                    onNavigate={onNavigate}
                  />
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

/**
 * The responsive navigation drawer: a fixed 240px rail on desktop,
 * and a top app bar with a slide-over on mobile.
 *
 * The mobile drawer is real rather than decorative — all public and role-specific sections have to
 * stay reachable on a phone, so the hamburger opens a focusable panel that
 * closes on route change, on Escape, and on backdrop click.
 */
export function SiteNav({
  viewer,
  adminBadges,
}: {
  viewer: Viewer;
  adminBadges?: AdminNavBadges;
}) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => setOpen(false), [pathname]);

  useEffect(() => {
    if (!open) return;

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
      if (event.key === "Tab") {
        const nodes = document.querySelectorAll<HTMLElement>('#mobile-nav a[href], #mobile-nav button, #mobile-nav input');
        const first = nodes[0], last = nodes[nodes.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    }
    document.addEventListener("keydown", onKeyDown);

    // The drawer covers the page, so the page behind it must not scroll — on
    // touch devices that is the difference between a panel and a stuck page.
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";

    // Move focus into the panel, and hand it back to the control that opened
    // it on the way out, so keyboard and screen-reader users are not dropped
    // at the top of the document.
    closeRef.current?.focus();

    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = overflow;
      toggleRef.current?.focus();
    };
  }, [open]);

  return (
    <>
      {/* Desktop rail */}
      <nav
        aria-label="Primary"
        className="app-rail fixed inset-y-0 left-0 z-40 hidden flex-col border-r border-rule bg-surface py-8 md:flex"
      >
        <div className="mb-8 px-5">
          <Wordmark />
        </div>
        <div className="flex-1 overflow-y-auto px-0 pb-4">
          <NavList viewer={viewer} badges={adminBadges} />
        </div>
        <div className="mt-auto flex flex-col gap-2 border-t border-rule px-5 pt-5">
          <RoleBadge role={viewer.role} className="self-start" />
        </div>
      </nav>

      {/* Mobile top app bar */}
      <header className="mobile-appbar sticky top-0 z-40 flex h-16 shrink-0 items-center justify-between gap-3 border-b border-rule bg-surface px-4 md:hidden">
        <button
          ref={toggleRef}
          type="button"
          onClick={() => setOpen(true)}
          aria-expanded={open}
          aria-controls="mobile-nav"
          className="icon-control"
        >
          <MenuIcon />
          <span className="sr-only">Open navigation</span>
        </button>
        <Wordmark compact />
        <div className="flex items-center gap-1">
          <ThemeToggle />
          {/* Jump to publications search unless this page already has one. */}
          {!hasContextualPageSearch(pathname ?? "/") ? (
            <Link
              href="/publications"
              className="icon-control"
            >
              <SearchIcon />
              <span className="sr-only">Search publications</span>
            </Link>
          ) : null}
        </div>
      </header>

      {/* Mobile slide-over */}
      {open ? (
        <div className="fixed inset-0 z-50 md:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            onClick={() => setOpen(false)}
            className="absolute inset-0 bg-ink/40"
          />
          <nav
            id="mobile-nav"
            aria-label="Primary"
            className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col overflow-y-auto border-r border-rule bg-surface py-6"
          >
            <div className="mb-6 flex items-start justify-between gap-2 px-5">
              <Wordmark />
              <button
                ref={closeRef}
                type="button"
                onClick={() => setOpen(false)}
                className="icon-control text-ink-secondary hover:text-ink"
              >
                <CloseIcon />
                <span className="sr-only">Close navigation</span>
              </button>
            </div>
            {hasContextualPageSearch(pathname ?? "/") ? null : (
            <div className="mb-6 px-4">
                <SearchBox
                  label="Search publications, researchers, and institutions"
                  placeholder="Search publications, researchers, institutions…"
                  suggestionTypes={[...GLOBAL_SEARCH_TYPES]}
                />
            </div>
            )}
            <div className="flex-1 overflow-y-auto">
              <NavList viewer={viewer} badges={adminBadges} onNavigate={() => setOpen(false)} />
            </div>
            <div className="mt-4 border-t border-rule px-4 pt-4">
              <AccountMenu viewer={viewer} />
            </div>
          </nav>
        </div>
      ) : null}
    </>
  );
}

/**
 * Desktop search bar. Sits above the content column rather than in the rail,
 * keeping search and account actions available across public and protected routes.
 */
export function SiteSearchBar({
  viewer,
  adminBadges,
}: {
  viewer: Viewer;
  adminBadges?: AdminNavBadges;
}) {
  const pathname = usePathname() ?? "/";
  const { section, label } = sectionForPath(pathname, viewer, adminBadges);
  const showGlobalSearch = !hasContextualPageSearch(pathname);

  return (
    <div className="app-topbar sticky top-0 z-30 hidden items-center justify-between gap-5 border-b border-rule bg-surface md:flex">
      <div className="flex items-center gap-3 whitespace-nowrap text-label text-muted">
        <span className="hidden xl:inline">{section} /</span>
        <span className="font-medium text-ink">{label}</span>
      </div>
      <div className="flex min-w-0 items-center justify-end gap-4">
        {showGlobalSearch ? (
          <div className="w-full max-w-lg">
            <SearchBox
              label="Search publications, researchers, and institutions"
              placeholder="Search publications, researchers, institutions…"
              suggestionTypes={[...GLOBAL_SEARCH_TYPES]}
            />
          </div>
        ) : null}
        <ThemeToggle />
        <div className="shrink-0">
          <AccountMenu viewer={viewer} />
        </div>
      </div>
    </div>
  );
}

const AI_SCOPE_HIDDEN = ["/admin", "/account", "/login", "/register", "/forbidden"];

/**
 * Scope disclosure for the AI collection.
 * Overview keeps the full note. Other pages show a compact chip.
 */
export function AIScopeNote() {
  const pathname = usePathname() ?? "/";
  if (AI_SCOPE_HIDDEN.some((path) => pathname.startsWith(path))) return null;

  const isOverview = pathname === "/";

  if (isOverview) {
    return (
      <div className="ai-scope" role="note">
        <span className="ai-scope-dot" aria-hidden />
        <span>
          <strong>{SITE_COPY.scopeStrong}</strong> {SITE_COPY.scopeBody}
        </span>
        <Link
          href="/data-quality"
          className="ml-auto shrink-0 text-primary hover:underline"
        >
          About the data ↗
        </Link>
      </div>
    );
  }

  return (
    <div className="ai-scope ai-scope-chip" role="note">
      <span className="ai-scope-dot" aria-hidden />
      <span className="ai-scope-chip-label">{SITE_COPY.compactScope}</span>
      <Link
        href="/data-quality"
        className="shrink-0 text-primary hover:underline"
      >
        About the data
      </Link>
    </div>
  );
}
