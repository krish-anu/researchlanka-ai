import Link from "next/link";

import { CORPUS_SOURCES, SourceDot, sourceColor } from "@/components/ui/Provenance";

/**
 * The provenance stripe closes every page, per the design system.
 *
 * The segments are equal width and stand for *which* sources feed the corpus,
 * not their share of it — the footer is static and has no snapshot to measure,
 * and a proportional-looking bar with invented widths would read as a
 * measurement. Per-record proportions belong to `ProvenanceStripe`.
 */
export function SiteFooter() {
  return (
    <footer className="mt-12 border-t border-rule bg-surface">
      <div className="flex h-2 w-full" aria-hidden>
        {CORPUS_SOURCES.map((source) => (
          <div
            key={source}
            className="h-full flex-1"
            style={{ backgroundColor: sourceColor(source) }}
          />
        ))}
      </div>

      <div className="mx-auto max-w-[1140px] px-4 py-6 md:px-8 lg:px-16">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div className="max-w-prose">
            <span className="label-caps block text-muted">Data provenance</span>
            <p className="mt-2 text-body-sm text-ink-secondary">
              ResearchLanka is a read-only public view of the consolidated Sri
              Lankan research corpus. Counts describe records observed in the
              dataset and are not official national totals.
            </p>
          </div>

          <ul className="flex flex-wrap gap-x-4 gap-y-2 text-body-sm text-ink-secondary">
            {CORPUS_SOURCES.map((source) => (
              <li key={source} className="flex items-center gap-2">
                <SourceDot source={source} />
                <SourceName source={source} />
              </li>
            ))}
          </ul>
        </div>

        <p className="mt-4 border-t border-rule pt-4 text-body-sm text-muted">
          Entity resolution and topic classification are automated and
          imperfect;{" "}
          <Link
            href="/data-quality"
            className="text-primary underline hover:text-primary-hover"
          >
            see the data quality notes
          </Link>{" "}
          before citing these figures.
        </p>
      </div>
    </footer>
  );
}

function SourceName({ source }: { source: string }) {
  const names: Record<string, string> = {
    openalex: "OpenAlex",
    crossref: "Crossref",
    sljol: "SLJOL",
    repositories: "Institutional repositories",
  };
  return <span>{names[source] ?? source}</span>;
}
