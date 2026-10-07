import type { Metadata } from "next";
import { GoogleAnalytics } from "@next/third-parties/google";

import { SiteFooter } from "@/components/layout/SiteFooter";
import { SiteNav, SiteSearchBar, AIScopeNote } from "@/components/layout/SiteNav";
import { RouteFocus } from "@/components/layout/RouteFocus";
import { FilterNavigationProvider } from "@/components/navigation/FilterNavigation";
import { getViewer } from "@/services/auth/server";
import { loadAdminNavBadges } from "@/services/admin/navBadges";
import { SITE_COPY } from "@/config/site";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: SITE_COPY.metadataTitle,
    template: SITE_COPY.metadataTemplate,
  },
  description: SITE_COPY.metadataDescription,
};

/**
 * The viewer is resolved once here and handed down, so the nav and the account
 * control agree on who is signed in without each re-reading the cookie. Reading
 * cookies opts every route into dynamic rendering; that is the right trade for
 * a shell whose contents differ per role, and the API data below it is still
 * cached by the `revalidate` settings in `services/api.ts`.
 */
export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const viewer = await getViewer();
  const adminBadges = await loadAdminNavBadges(viewer.role);

  return (
    <html lang="en">
      {/*
        The shell is one flex column that is at least as tall as the viewport,
        so the footer sits on the bottom edge even when a page renders almost
        nothing. `main` is the only element allowed to grow, which keeps that
        slack inside the content area instead of below the footer.
      */}
      <body className="flex min-h-dvh flex-col bg-page text-ink antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:border focus:border-rule focus:bg-surface focus:px-3 focus:py-2 focus:text-body-sm"
        >
          Skip to content
        </a>

        <RouteFocus />
        <SiteNav viewer={viewer} adminBadges={adminBadges} />

        {/* Responsive content canvas, offset by the desktop navigation rail. */}
        <div className="app-canvas grow">
          <SiteSearchBar viewer={viewer} adminBadges={adminBadges} />
          <main
            id="main"
            tabIndex={-1}
            className="app-main"
          >
            <AIScopeNote />
            <FilterNavigationProvider>{children}</FilterNavigationProvider>
          </main>
          <SiteFooter />
        </div>
      </body>
      <GoogleAnalytics gaId="G-GGBWEZFK02" />
    </html>
  );
}
