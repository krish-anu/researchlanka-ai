"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ComponentType } from "react";

import {
  CloseIcon,
  DashboardIcon,
  DataQualityIcon,
  InstitutionsIcon,
  MenuIcon,
  PublicationsIcon,
  ResearchersIcon,
  SearchIcon,
  TopicsIcon,
} from "@/components/layout/NavIcons";
import { SearchBox } from "@/components/search/SearchBox";

interface NavLink {
  href: string;
  label: string;
  Icon: ComponentType<{ className?: string }>;
}

const NAV_LINKS: NavLink[] = [
  { href: "/", label: "Dashboard", Icon: DashboardIcon },
  { href: "/publications", label: "Publications", Icon: PublicationsIcon },
  { href: "/researchers", label: "Researchers", Icon: ResearchersIcon },
  { href: "/institutions", label: "Institutions", Icon: InstitutionsIcon },
  { href: "/topics", label: "Topics", Icon: TopicsIcon },
  { href: "/data-quality", label: "Data quality", Icon: DataQualityIcon },
];

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
      className={`mx-2 flex items-center gap-3 rounded px-3 py-2.5 text-body-sm transition-colors ${
        active
          ? "bg-primary-container font-semibold text-on-primary"
          : "text-ink-secondary hover:bg-wash hover:text-ink"
      }`}
    >
      <Icon />
      <span>{label}</span>
    </Link>
  );
}

function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/" className="flex flex-col leading-tight">
      <span
        className={`font-display font-bold text-primary ${
          compact ? "text-h3" : "text-h3"
        }`}
      >
        ResearchLanka
      </span>
      {!compact ? (
        <span className="mt-1 text-body-sm text-ink-secondary">
          Sri Lanka research intelligence
        </span>
      ) : null}
    </Link>
  );
}

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname() ?? "/";
  return (
    <ul className="flex flex-col gap-1">
      {NAV_LINKS.map((link) => (
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
 * The navigation drawer from the Stitch screens: a fixed 288px rail on desktop,
 * and a top app bar with a slide-over on mobile.
 *
 * The mobile drawer is real rather than decorative — all six sections have to
 * stay reachable on a phone, so the hamburger opens a focusable panel that
 * closes on route change, on Escape, and on backdrop click.
 */
export function SiteNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  useEffect(() => setOpen(false), [pathname]);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  return (
    <>
      {/* Desktop rail */}
      <nav
        aria-label="Primary"
        className="fixed inset-y-0 left-0 z-40 hidden w-72 flex-col border-r border-rule bg-surface py-6 md:flex"
      >
        <div className="mb-8 px-5">
          <Wordmark />
        </div>
        <div className="flex-1 overflow-y-auto">
          <NavList />
        </div>
        <div className="mt-auto border-t border-rule px-5 pt-5">
          <p className="text-body-sm text-muted">
            Read-only public view of the consolidated national research corpus.
          </p>
        </div>
      </nav>

      {/* Mobile top app bar */}
      <header className="sticky top-0 z-40 flex h-16 items-center justify-between gap-3 border-b border-rule bg-surface px-4 md:hidden">
        <button
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
            className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r border-rule bg-surface py-6"
          >
            <div className="mb-6 flex items-start justify-between gap-2 px-5">
              <Wordmark />
              <button
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
              <NavList onNavigate={() => setOpen(false)} />
            </div>
          </nav>
        </div>
      ) : null}
    </>
  );
}

/**
 * Desktop search bar. Sits above the content column rather than in the rail,
 * matching the docked top bar on the Stitch content screens.
 */
export function SiteSearchBar() {
  return (
    <div className="sticky top-0 z-30 hidden border-b border-rule bg-surface md:block">
      <div className="mx-auto flex h-16 max-w-[1140px] items-center justify-end px-8 lg:px-16">
        <div className="w-full max-w-md">
          <SearchBox />
        </div>
      </div>
    </div>
  );
}
