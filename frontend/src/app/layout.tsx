import type { Metadata } from "next";
import { GoogleAnalytics } from "@next/third-parties/google";
import { Archivo, IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";

import { SiteFooter } from "@/components/layout/SiteFooter";
import { SiteNav, SiteSearchBar, AIScopeNote } from "@/components/layout/SiteNav";
import { getViewer } from "@/services/auth/server";

import "./globals.css";

/**
 * The design system's three faces, each doing one job: Archivo for headings,
 * IBM Plex Sans for prose, IBM Plex Mono for DOIs and other machine identifiers.
 */
const archivo = Archivo({
  subsets: ["latin"],
  weight: ["600", "700"],
  variable: "--font-archivo",
  display: "swap",
});

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex-sans",
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "ResearchLanka — Sri Lanka AI research analytics",
    template: "%s · ResearchLanka",
  },
  description:
    "Public read-only analytics over the accepted Sri Lankan AI publication collection: national dashboards, publication search, researcher and institution profiles.",
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

  return (
    <html
      lang="en"
      className={`${archivo.variable} ${plexSans.variable} ${plexMono.variable}`}
    >
      {/*
        The shell is one flex column that is at least as tall as the viewport,
        so the footer sits on the bottom edge even when a page renders almost
        nothing. `main` is the only element allowed to grow, which keeps that
        slack inside the content area instead of below the footer.
      */}
      <body className="flex min-h-screen flex-col bg-page text-ink antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:border focus:border-rule focus:bg-surface focus:px-3 focus:py-2 focus:text-body-sm"
        >
          Skip to content
        </a>

        <SiteNav viewer={viewer} />

        {/* Responsive content canvas, offset by the desktop navigation rail. */}
        <div className="app-canvas grow">
          <SiteSearchBar viewer={viewer} />
          <main
            id="main"
            className="app-main"
          >
            <AIScopeNote />
            {children}
          </main>
          <SiteFooter />
        </div>
      </body>
      <GoogleAnalytics gaId="G-GGBWEZFK02" />
    </html>
  );
}
