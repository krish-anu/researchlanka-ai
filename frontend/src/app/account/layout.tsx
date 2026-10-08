import { TabBar, TabLink } from "@/components/layout/TabNav";
import { requireCapability } from "@/services/auth/server";

/**
 * Personal workspace shell — saved library, flags and author profile.
 * Middleware also gates these routes; this check runs with the page render.
 */
const TABS = [
  { href: "/account", label: "Profile", exact: true },
  { href: "/account/saved", label: "Saved library" },
  { href: "/account/flags", label: "Your flags" },
  { href: "/account/author", label: "Author profile" },
] as const;

export const metadata = {
  title: {
    default: "My workspace",
    template: "%s · My workspace · ResearchLanka",
  },
};

export default async function AccountLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  await requireCapability("account.manage", "/account");

  return (
    <div className="workspace-shell flex flex-col gap-5">
      <header className="workspace-shell-strip">
        <p className="page-eyebrow">My workspace</p>
        <p className="mt-1 max-w-prose text-body-sm text-ink-secondary">
          Your library, flags and author profile. Public charts and rankings
          stay the same for everyone.
        </p>
      </header>

      <TabBar label="My workspace">
        {TABS.map((tab) => (
          <li key={tab.href}>
            <TabLink href={tab.href} exact={"exact" in tab ? tab.exact : false}>
              {tab.label}
            </TabLink>
          </li>
        ))}
      </TabBar>

      {children}
    </div>
  );
}
