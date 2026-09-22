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
  NetworkIcon,
  InstitutionsIcon,
  MenuIcon,
  PublicationsIcon,
  ResearchersIcon,
  SearchIcon,
  TopicsIcon,
} from "@/components/layout/NavIcons";
import { SearchBox } from "@/components/search/SearchBox";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import type { Viewer } from "@/types/auth";

interface NavLink {
  href: string;
  label: string;
  Icon: ComponentType<{ className?: string }>;
  /** Present only for administrators; the public sections have no requirement. */
  adminOnly?: boolean;
}

const NAV_LINKS: NavLink[] = [
  { href: "/", label: "Overview", Icon: DashboardIcon },
  { href: "/publications", label: "AI publications", Icon: PublicationsIcon },
  { href: "/researchers", label: "Researchers", Icon: ResearchersIcon },
  { href: "/institutions", label: "Institutions", Icon: InstitutionsIcon },
  { href: "/topics", label: "Topics & fields", Icon: TopicsIcon },
  { href: "/collaboration", label: "Collaboration", Icon: NetworkIcon },
  { href: "/data-quality", label: "Data quality", Icon: DataQualityIcon },
  { href: "/admin", label: "Administration", Icon: AdminIcon, adminOnly: true },
];

/**
 * The rail only lists what the viewer can actually open.
 *
 * Hiding the admin entry is presentation, not protection — `middleware.ts` and
 * the admin layout are what stop a visitor typing the URL.
 */
function visibleLinks(viewer: Viewer): NavLink[] {
  return NAV_LINKS.filter((link) => !link.adminOnly || viewer.role === "admin");
}

/** "/" only matches itself; every other entry also owns its detail routes. */
function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
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
  const { href, label, Icon } = link;
  return (
    <Link
      href={href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className="nav-item"
    >
      <Icon />
      <span>{label}</span>
    </Link>
  );
}

function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/" className="brand" aria-label="ResearchLanka overview">
      <span className="brand-mark"><NetworkIcon /></span>
      <span><span className="brand-name">Research<span className="text-primary">Lanka</span></span>
      {!compact ? <span className="brand-tagline">AI RESEARCH, CONNECTED.</span> : null}</span>
    </Link>
  );
}

function NavList({
  viewer,
  onNavigate,
}: {
  viewer: Viewer;
  onNavigate?: () => void;
}) {
  const pathname = usePathname() ?? "/";
  return (
    <ul className="flex flex-col gap-1">
      {visibleLinks(viewer).map((link) => (
        <li key={link.href}>
          <NavItem
            link={link}
            active={isActive(pathname, link.href)}
            onNavigate={onNavigate}
          />
        </li>
      ))}
    </ul>
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
export function SiteNav({ viewer }: { viewer: Viewer }) {
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
        <div className="flex-1 overflow-y-auto">
          <p className="page-eyebrow mb-4 px-7">Workspace</p>
          <NavList viewer={viewer} />
        </div>
        <div className="mx-5 mb-5 rounded-xl border border-rule bg-wash p-4">
          <p className="text-body-sm font-semibold">Research with perspective.</p>
          <p className="my-2 text-xs text-muted">Understand the data behind every discovery.</p>
          <Link href="/data-quality" className="text-xs font-semibold text-primary">Explore data quality →</Link>
        </div>
        <div className="mt-auto flex flex-col gap-2 border-t border-rule px-5 pt-5">
          <RoleBadge role={viewer.role} className="self-start" />
          <p className="text-body-sm text-muted">
            {viewer.user
              ? "Signed in. Public figures are unchanged by your account — it adds a library and flagging."
              : "Explore accepted AI-related publications from Sri Lanka."}
          </p>
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
          className="rounded p-2 text-primary hover:bg-wash"
        >
          <MenuIcon />
          <span className="sr-only">Open navigation</span>
        </button>
        <Wordmark compact />
        {/* Search stays one tap away on mobile rather than only inside the drawer. */}
        <Link
          href="/publications"
          className="rounded p-2 text-primary hover:bg-wash"
        >
          <SearchIcon />
          <span className="sr-only">Search publications</span>
        </Link>
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
                className="rounded p-1 text-ink-secondary hover:bg-wash hover:text-ink"
              >
                <CloseIcon />
                <span className="sr-only">Close navigation</span>
              </button>
            </div>
            <div className="mb-6 px-4">
              <SearchBox />
            </div>
            <div className="flex-1 overflow-y-auto">
              <NavList viewer={viewer} onNavigate={() => setOpen(false)} />
            </div>
            <div className="mt-4 border-t border-rule px-4 pt-4">
              <div className="mb-3 flex items-center justify-between text-xs text-muted"><span>Theme</span><ThemeToggle /></div>
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
export function SiteSearchBar({ viewer }: { viewer: Viewer }) {
  const pathname = usePathname() ?? "/";
  const label = NAV_LINKS.find(link => isActive(pathname, link.href))?.label
    ?? (pathname.startsWith("/account") ? "My workspace" : "Account");
  return (
    <div className="app-topbar sticky top-0 z-30 hidden items-center justify-between gap-5 border-b border-rule bg-surface md:flex">
      <div className="flex items-center gap-3 whitespace-nowrap text-xs text-muted"><span className="hidden xl:inline">Workspace /</span><span className="font-medium text-ink">{label}</span></div>
      <div className="flex min-w-0 items-center justify-end gap-4">
        <div className="w-full max-w-sm"><SearchBox placeholder="Search AI publications…" /></div>
        <ThemeToggle />
        <div className="shrink-0"><AccountMenu viewer={viewer} /></div>
      </div>
    </div>
  );
}

export function AIScopeNote() {
  const pathname = usePathname() ?? "/";
  if (["/admin", "/account", "/login", "/register", "/forbidden"].some(path => pathname.startsWith(path))) return null;
  return <div className="ai-scope"><span className="ai-scope-dot" /><span><strong>AI-related publications only.</strong> Charts, rankings, profiles, and exports describe the accepted AI collection.</span><Link href="/data-quality" className="ml-auto shrink-0 text-primary hover:underline">About the data ↗</Link></div>;
}
