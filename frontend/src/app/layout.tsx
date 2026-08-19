import type { Metadata } from "next";
import { Archivo, IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";

import { SiteFooter } from "@/components/layout/SiteFooter";
import { SiteNav, SiteSearchBar } from "@/components/layout/SiteNav";
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
    default: "ResearchLanka — Sri Lanka national research analytics",
    template: "%s · ResearchLanka",
  },
  description:
    "Public read-only analytics over the consolidated Sri Lankan research publication corpus: national dashboards, publication search, researcher and institution profiles.",
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
      <body className="min-h-screen bg-page text-ink antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:border focus:border-rule focus:bg-surface focus:px-3 focus:py-2 focus:text-body-sm"
        >
          Skip to content
        </a>

        <SiteNav viewer={viewer} />

        {/* Content canvas offset by the fixed rail; 1140px fixed grid inside. */}
        <div className="flex min-h-screen flex-col md:ml-72">
          <SiteSearchBar viewer={viewer} />
          <main id="main" className="mx-auto w-full max-w-[1140px] px-4 py-6 md:px-8 md:py-12 lg:px-16">
            {children}
          </main>
          <SiteFooter />
        </div>
      </body>
    </html>
  );
}
