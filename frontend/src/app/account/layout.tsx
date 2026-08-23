import { TabBar, TabLink } from "@/components/layout/TabNav";
import { requireCapability } from "@/services/auth/server";

/**
 * Authoritative gate for the account area.
 *
 * `middleware.ts` redirects here too, but this is the check that counts: it
 * runs in the same request as the page render, so it cannot be skipped by a
 * route that middleware's matcher misses.
 */
const TABS = [
  // The area root, so it must match exactly or it stays lit on every sub-tab.
  { href: "/account", label: "Profile", exact: true },
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
      <TabBar label="Account">
        {TABS.map((tab) => (
          <li key={tab.href}>
            <TabLink href={tab.href} exact={tab.exact}>
              {tab.label}
            </TabLink>
          </li>
        ))}
      </TabBar>
      {children}
    </div>
  );
}
