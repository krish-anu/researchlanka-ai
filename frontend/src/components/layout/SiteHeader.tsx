import Link from "next/link";

import { SearchBox } from "@/components/search/SearchBox";

const NAV_LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/publications", label: "Publications" },
  { href: "/researchers", label: "Researchers" },
  { href: "/institutions", label: "Institutions" },
  { href: "/topics", label: "Topics" },
  { href: "/data-quality", label: "Data quality" },
];

export function SiteHeader() {
  return (
    <header className="border-b border-hairline bg-surface">
      <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center justify-between gap-4">
          <Link href="/" className="flex flex-col leading-tight">
            <span className="text-base font-semibold text-ink">ResearchLanka</span>
            <span className="text-xs text-muted">
              Sri Lanka national research analytics
            </span>
          </Link>
        </div>

        <div className="w-full lg:max-w-sm">
          <SearchBox />
        </div>
      </div>

      <nav aria-label="Primary" className="border-t border-hairline">
        <div className="mx-auto max-w-7xl px-4">
          <div className="scroll-x">
            <ul className="flex gap-1 py-1">
              {NAV_LINKS.map((link) => (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    className="inline-block whitespace-nowrap rounded-md px-3 py-1.5 text-sm text-ink-secondary hover:bg-wash hover:text-ink"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </nav>
    </header>
  );
}
