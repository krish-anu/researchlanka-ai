import Link from "next/link";

import { requireCapability } from "@/services/auth/server";

/**
 * Authoritative gate for the account area.
 *
 * `middleware.ts` redirects here too, but this is the check that counts: it
 * runs in the same request as the page render, so it cannot be skipped by a
 * route that middleware's matcher misses.
 */
const TABS = [
  { href: "/account", label: "Profile" },
  { href: "/account/saved", label: "Saved library" },
  { href: "/account/flags", label: "Your flags" },
];

export default async function AccountLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  await requireCapability("account.manage", "/account");

  return (
    <div className="flex flex-col gap-6">
      <nav aria-label="Account" className="border-b border-rule">
        <ul className="scroll-x flex gap-1">
          {TABS.map((tab) => (
            <li key={tab.href}>
              <Link
                href={tab.href}
                className="inline-block whitespace-nowrap px-3 py-2.5 text-body-sm text-ink-secondary hover:text-primary"
              >
                {tab.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      {children}
    </div>
  );
}
