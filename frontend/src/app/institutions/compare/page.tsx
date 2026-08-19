import Link from "next/link";

import { CompareBarChart } from "@/components/charts/CompareBarChart";
import { ChartPanel } from "@/components/ui/ChartPanel";
import { DataTable, TableDisclosure } from "@/components/ui/DataTable";
import { ApiErrorPanel, SectionHeading } from "@/components/ui/Feedback";
import { compareInstitutions, listInstitutions } from "@/services/api";
import type { SearchParams } from "@/services/filters";
import {
  formatDecimal,
  formatNumber,
  formatYearRange,
} from "@/services/format";
import { institutionHref } from "@/services/links";

export const metadata = {
  title: "Compare institutions",
  description:
    "Compare publication output, citations and active years across two or three Sri Lankan research institutions.",
};

function selected(params: SearchParams): string[] {
  const raw = params.institution;
  if (raw === undefined) return [];
  return (Array.isArray(raw) ? raw : [raw]).filter((value) => value !== "");
}

export default async function CompareInstitutionsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const chosen = selected(params);

  // The API rejects anything outside 2–3, so the form is shown until the
  // selection is valid rather than issuing a request that will 400.
  const isValidSelection = chosen.length >= 2 && chosen.length <= 3;

  const [directory, comparison] = await Promise.all([
    listInstitutions({ limit: 60 }),
    isValidSelection ? compareInstitutions(chosen) : Promise.resolve(null),
  ]);

  const inputClass =
    "w-full rounded border border-rule bg-page px-2 py-1.5 text-body-sm text-ink";

  return (
    <div className="flex flex-col gap-10 md:gap-12">
      <div>
        <h1 className="title-page text-ink">Compare institutions</h1>
        <p className="mt-1 max-w-prose text-body-sm text-ink-secondary">
          Benchmark two or three institutions against each other on recorded
          output and citations.
        </p>
      </div>

      <form
        method="get"
        action="/institutions/compare"
        className="panel flex flex-col gap-3 p-4"
      >
        <p className="text-body-sm text-ink-secondary">
          Choose two or three institutions. Names are matched against recorded
          affiliations, so partial names work.
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {[0, 1, 2].map((index) => (
            <label key={index} className="flex flex-col gap-1 text-body-sm text-muted">
              Institution {index + 1}
              {index === 2 ? " (optional)" : ""}
              <input
                className={inputClass}
                name="institution"
                list="institution-options"
                defaultValue={chosen[index] ?? ""}
                placeholder="e.g. University of Colombo"
              />
            </label>
          ))}
        </div>

        {directory.ok ? (
          <datalist id="institution-options">
            {directory.value.data.map((entry) => (
              <option key={entry.key} value={entry.label} />
            ))}
          </datalist>
        ) : null}

        <div className="flex gap-2">
          <button
            type="submit"
            className="rounded border border-rule bg-wash px-4 py-1.5 text-body-sm font-medium text-ink hover:bg-page"
          >
            Compare
          </button>
          <Link
            href="/institutions"
            className="rounded border border-rule px-4 py-1.5 text-body-sm text-ink-secondary hover:bg-wash"
          >
            Back to directory
          </Link>
        </div>

        {chosen.length > 0 && !isValidSelection ? (
          <p className="flex gap-2 text-body-sm text-ink-secondary">
            <span aria-hidden className="text-warning">
              ▲
            </span>
            Select at least two institutions (and at most three) to compare.
          </p>
        ) : null}
      </form>

      {comparison && !comparison.ok ? (
        <ApiErrorPanel error={comparison.error} what="the comparison" />
      ) : null}

      {comparison?.ok && comparison.value.data.length > 0 ? (
        <>
          {comparison.value.data.length < chosen.length ? (
            <p className="panel border-warning/40 p-3 text-body-sm text-ink-secondary">
              <span aria-hidden className="mr-2 text-warning">
                ▲
              </span>
              Only {comparison.value.data.length} of {chosen.length} names matched
              a recorded affiliation. Unmatched names are omitted below.
            </p>
          ) : null}

          {/* Two measures of very different magnitude get two charts with one
              axis each, never a single plot with a second y-scale. */}
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <ChartPanel
              title="Publications"
              description="Total records with an affiliation to each institution."
            >
              <CompareBarChart
                entries={comparison.value.data.map((profile) => ({
                  label: profile.label,
                  value: profile.publication_count,
                }))}
                valueLabel="Publications"
                ariaLabel="Bar chart comparing publication counts across institutions"
              />
            </ChartPanel>

            <ChartPanel
              title="Citations"
              description="Total citations accruing to those records."
            >
              <CompareBarChart
                entries={comparison.value.data.map((profile) => ({
                  label: profile.label,
                  value: profile.citation_total,
                }))}
                valueLabel="Citations"
                ariaLabel="Bar chart comparing citation totals across institutions"
              />
            </ChartPanel>
          </div>

          <section className="panel p-4">
            <SectionHeading
              title="Side by side"
              description="The same figures as a table."
            />
            <DataTable
              columns={[
                {
                  key: "label",
                  header: "Institution",
                  render: (row) => (
                    <Link
                      href={institutionHref(row.label)}
                      className="hover:underline"
                    >
                      {row.label}
                    </Link>
                  ),
                },
                {
                  key: "publications",
                  header: "Publications",
                  numeric: true,
                  render: (row) => formatNumber(row.publication_count),
                },
                {
                  key: "citations",
                  header: "Citations",
                  numeric: true,
                  render: (row) => formatNumber(row.citation_total),
                },
                {
                  key: "average",
                  header: "Citations / publication",
                  numeric: true,
                  render: (row) => formatDecimal(row.average_citations),
                },
                {
                  key: "years",
                  header: "Active years",
                  render: (row) => formatYearRange(row.year_min, row.year_max),
                },
              ]}
              rows={comparison.value.data}
              rowKey={(row) => row.key}
            />
          </section>
        </>
      ) : null}

      {comparison?.ok && comparison.value.data.length === 0 ? (
        <p className="panel p-4 text-body-sm text-ink-secondary">
          None of those names matched a recorded affiliation. Try a shorter or
          differently spelled name — matching is against the affiliation text
          stored on each publication.
        </p>
      ) : null}
    </div>
  );
}
