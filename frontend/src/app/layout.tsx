import type { Metadata } from "next";

import { SiteFooter } from "@/components/layout/SiteFooter";
import { SiteHeader } from "@/components/layout/SiteHeader";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "ResearchLanka — Sri Lanka national research analytics",
    template: "%s · ResearchLanka",
  },
  description:
    "Public read-only analytics over the consolidated Sri Lankan research publication corpus: national dashboards, publication search, researcher and institution profiles.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-page text-ink antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2 focus:text-sm"
        >
          Skip to content
        </a>
        <SiteHeader />
        <main id="main" className="mx-auto max-w-7xl px-4 py-6">
          {children}
        </main>
        <SiteFooter />
      </body>
    </html>
  );
}
