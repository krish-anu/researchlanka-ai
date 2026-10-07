import Link from "next/link";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { RankingBarChart } from "@/components/charts/RankingBarChart";
import { TrendLineChart } from "@/components/charts/TrendLineChart";
import { DepartmentPublicationList } from "@/components/departments/DepartmentPublicationList";
import { ProfileHeader, ProfileTabs, type ProfileTabId } from "@/components/layout/ProfileHeader";
import { ChartPanel, DownloadLink } from "@/components/ui/ChartPanel";
import { DataTable, TableDisclosure } from "@/components/ui/DataTable";
import { ApiErrorPanel, EmptyState, SectionHeading } from "@/components/ui/Feedback";
import { Pagination } from "@/components/ui/Pagination";
import { PrintMeta } from "@/components/ui/PrintMeta";
import { SnapshotNote } from "@/components/ui/Provenance";
import { StatTile, StatTileGrid } from "@/components/ui/StatTile";
import {
  departmentExportUrl,
  getDepartment,
  getDepartmentPublications,
  getDepartmentResearchers,
  isNotFound,
  type QueryParams,
} from "@/services/api";
import { extractPage, type SearchParams } from "@/services/filters";
import {
  formatCompact,
  formatDateTime,
  formatNumber,
  formatRatioAsPercent,
  formatYearRange,
} from "@/services/format";
import { departmentHref, institutionHref, researcherHref } from "@/services/links";
import type { CountEntry, DepartmentMatch, DepartmentResearcher } from "@/types/api";

interface PageProps {
  params: Promise<{ key: string }>;
  searchParams: Promise<SearchParams>;
}

const PUBLICATION_PAGE_SIZE = 20;
const RESEARCHER_PAGE_SIZE = 25;
const DEPARTMENT_TABS = ["overview", "researchers", "publications", "collaboration", "method"] as const;
type DepartmentTab = (typeof DEPARTMENT_TABS)[number] & ProfileTabId;

const PUBLICATION_SORTS = { year_desc: "Newest", citations_desc: "Most cited" } as const;
const RESEARCHER_SORTS = {
  publications_desc: "Most publications",
  recent_desc: "Most recent",
  name_asc: "Name",
} as const;
const MATCH_FILTERS: Record<DepartmentMatch, string> = {
  explicit: "Named in affiliation",
  inferred: "Inferred from author history",
};

const REGION_NAMES = new Intl.DisplayNames(["en"], { type: "region" });

function countryName(code: string): string {
  try {
    return REGION_NAMES.of(code) ?? code;
  } catch {
    return code;
  }
}

function firstValue(value: string | string[] | undefined): string | undefined {
  const raw = Array.isArray(value) ? value[0] : value;
  return raw?.trim() || undefined;
}

function oneOf<T extends string>(value: string | undefined, allowed: readonly T[]): T | undefined {
  return allowed.find((item) => item === value);
}

function yearValue(value: string | undefined): number | undefined {
  const parsed = value ? Number.parseInt(value, 10) : Number.NaN;
  return Number.isFinite(parsed) ? parsed : undefined;
}

/** Same page with some query parameters replaced; `undefined` removes one. */
function hrefWith(
  basePath: string,
  query: SearchParams,
  overrides: Record<string, string | number | undefined>,
): string {
  const search = new URLSearchParams();
  for (const [key, raw] of Object.entries(query)) {
    if (key in overrides || raw === undefined) continue;
    for (const item of Array.isArray(raw) ? raw : [raw]) search.append(key, item);
  }
  for (const [key, value] of Object.entries(overrides)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `${basePath}?${qs}` : basePath;
}

function countTable(rows: CountEntry[], header: string, render?: (label: string) => ReactNode) {
  return (
    <DataTable
      fit
      columns={[
        { key: "label", header, render: (row) => (render ? render(row.label) : row.label) },
        {
          key: "count",
          header: "Publications",
          numeric: true,
          render: (row) => formatNumber(row.publication_count),
        },
      ]}
      rows={rows}
      rowKey={(row) => row.label}
    />
  );
}

export async function generateMetadata({ params }: PageProps) {
  const { key } = await params;
  const profile = await getDepartment(decodeURIComponent(key));
  const name = profile.ok
    ? `${profile.value.data.name}, ${profile.value.data.institution_name}`
    : "Department";
  return {
    title: `${name} — AI research portfolio`,
    description: `AI publications, researchers, research areas and collaborations of the ${name}.`,
  };
}

export default async function DepartmentPortfolioPage({ params, searchParams }: PageProps) {
  const { key } = await params;
  const departmentKey = decodeURIComponent(key);
  const query = await searchParams;

  const yearMin = yearValue(firstValue(query.year_min));
  const yearMax = yearValue(firstValue(query.year_max));
  const period: QueryParams = { year_min: yearMin, year_max: yearMax };
  const periodActive = yearMin !== undefined || yearMax !== undefined;
  const match = oneOf(firstValue(query.match), ["explicit", "inferred"] as const);
  const researcher = firstValue(query.researcher);
  const publicationSort =
    oneOf(firstValue(query.sort), Object.keys(PUBLICATION_SORTS) as (keyof typeof PUBLICATION_SORTS)[]) ??
    "year_desc";
  const researcherSort =
    oneOf(firstValue(query.rsort), Object.keys(RESEARCHER_SORTS) as (keyof typeof RESEARCHER_SORTS)[]) ??
    "publications_desc";
  const researcherSearch = firstValue(query.rq);
  const initialTab: DepartmentTab = oneOf(firstValue(query.tab), DEPARTMENT_TABS) ?? "overview";

  const profile = await getDepartment(departmentKey, period);
  if (isNotFound(profile)) notFound();
  if (!profile.ok) {
    return <ApiErrorPanel error={profile.error} what="this department portfolio" />;
  }
  const data = profile.value.data;
  const basePath = departmentHref(data.department_id);

  const [publications, researchers] = await Promise.all([
    getDepartmentPublications(departmentKey, {
      ...period,
      page: extractPage(query),
      page_size: PUBLICATION_PAGE_SIZE,
      match,
      researcher,
      sort: publicationSort,
    }),
    getDepartmentResearchers(departmentKey, {
      ...period,
      page: extractPage(query, "rpage"),
      page_size: RESEARCHER_PAGE_SIZE,
      q: researcherSearch,
      sort: researcherSort,
    }),
  ]);

  const coverage = data.method.coverage;
  const currentYear = new Date().getFullYear();
  const periods = [
    { label: "All years", year_min: undefined },
    { label: "Last 5 years", year_min: currentYear - 4 },
    { label: "Last 3 years", year_min: currentYear - 2 },
  ];
  const hasCitations = data.citation_total !== null;
  const researcherHasCitations =
    researchers.ok && researchers.value.data.some((row) => row.citation_total !== null);

  const departmentPublicationsHref = (name: string) =>
    hrefWith(basePath, query, { researcher: name, page: undefined, tab: "publications" });

  const breadcrumbs = (
    <nav className="text-body-sm text-muted">
      <Link href="/departments" className="hover:text-ink hover:underline">
        Departments
      </Link>
      <span aria-hidden> / </span>
      <Link href={institutionHref(data.institution_name)} className="hover:text-ink hover:underline">
        {data.institution_name}
      </Link>
      <span aria-hidden> / </span>
      <span>{data.short_name}</span>
    </nav>
  );

  const actions = (
    <>
      <nav aria-label="Period" className="flex flex-wrap gap-1.5">
        {periods.map((option) => {
          const active = option.year_min === yearMin && yearMax === undefined;
          return (
            <Link
              key={option.label}
              href={hrefWith(basePath, query, {
                year_min: option.year_min,
                year_max: undefined,
                page: undefined,
                rpage: undefined,
              })}
              aria-current={active ? "page" : undefined}
              className={`chip ${active ? "chip-filter text-primary" : ""}`}
            >
              {option.label}
            </Link>
          );
        })}
      </nav>
      {data.url ? (
        <a
          href={data.url}
          target="_blank"
          rel="noopener noreferrer"
          className="interactive shrink-0 rounded-md border border-rule px-3 py-1.5 text-body-sm text-ink-secondary hover:bg-wash hover:text-ink"
        >
          Department website ↗
        </a>
      ) : null}
    </>
  );

  const metrics = (
    <StatTileGrid>
      <StatTile
        label="AI publications"
        value={formatNumber(data.publication_count)}
        caption={`${formatNumber(data.explicit_count)} named in affiliation · ${formatNumber(data.inferred_count)} inferred`}
      />
      <StatTile
        label="Researchers"
        value={formatNumber(data.researcher_count)}
        caption="authors with a department affiliation on these papers"
      />
      {!periodActive && coverage.institution_publications ? (
        <StatTile
          label={`Share of ${data.institution_name}`}
          value={formatRatioAsPercent(
            (coverage.department_publications ?? 0) / coverage.institution_publications,
            0,
          )}
          caption={`of ${formatNumber(coverage.institution_publications)} AI publications with a ${data.institution_name} author`}
        />
      ) : null}
      {hasCitations ? (
        <StatTile
          label="Citations"
          value={formatCompact(data.citation_total)}
          caption={data.h_index !== null ? `h-index ${data.h_index}` : undefined}
        />
      ) : null}
      <StatTile
        label="International co-authorship"
        value={formatRatioAsPercent(data.international_share, 0)}
        caption="publications with a co-author outside Sri Lanka"
      />
      <StatTile
        label="Open access"
        value={formatRatioAsPercent(data.open_access_share, 0)}
        caption="publications with an open-access version"
      />
    </StatTileGrid>
  );

  const notice = (
    <p className="text-body-sm text-ink-secondary">
      AI research by the {data.name}
      {data.faculty ? `, ${data.faculty}` : ""}, {formatYearRange(data.year_min, data.year_max)}. Built from
      author affiliations in the accepted AI collection —{" "}
      <Link
        href={hrefWith(basePath, query, { tab: "method" })}
        className="text-primary hover:underline"
      >
        how publications are attributed
      </Link>
      .
    </p>
  );

  const researcherTable = (rows: DepartmentResearcher[], compact: boolean) => (
    <DataTable
      fit={compact}
      columns={[
        {
          key: "name",
          header: "Researcher",
          render: (row) => (
            <Link href={researcherHref(row.label)} className="hover:underline">
              {row.label}
            </Link>
          ),
        },
        {
          key: "publications",
          header: "AI publications",
          numeric: true,
          render: (row) => (
            <Link href={departmentPublicationsHref(row.label)} className="hover:underline">
              {formatNumber(row.publication_count)}
            </Link>
          ),
        },
        ...(compact
          ? []
          : [
              {
                key: "inferred",
                header: "Of which inferred",
                numeric: true,
                render: (row: DepartmentResearcher) => formatNumber(row.inferred_count),
              },
              {
                key: "department_works",
                header: "Department works, all fields",
                numeric: true,
                render: (row: DepartmentResearcher) => formatNumber(row.department_works),
              },
            ]),
        ...(researcherHasCitations && !compact
          ? [
              {
                key: "citations",
                header: "Citations",
                numeric: true,
                render: (row: DepartmentResearcher) =>
                  row.citation_total === null ? "—" : formatNumber(row.citation_total),
              },
            ]
          : []),
        {
          key: "active",
          header: "Active",
          render: (row) => formatYearRange(row.first_year, row.last_year),
        },
        {
          key: "areas",
          header: "Main areas",
          render: (row) => (row.top_areas.length ? row.top_areas.join(" · ") : "—"),
        },
      ]}
      rows={rows}
      rowKey={(row) => row.label}
    />
  );

  const overviewTab = (
    <>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <ChartPanel
          title="AI publications per year"
          description="All department publications, and those whose affiliation names the department."
          table={
            data.yearly.length > 0 ? (
              <TableDisclosure>
                <DataTable
                  columns={[
                    { key: "year", header: "Year", render: (row) => String(row.year) },
                    {
                      key: "total",
                      header: "Publications",
                      numeric: true,
                      render: (row) => formatNumber(row.publication_count),
                    },
                    {
                      key: "explicit",
                      header: "Named in affiliation",
                      numeric: true,
                      render: (row) => formatNumber(row.explicit_count),
                    },
                    {
                      key: "inferred",
                      header: "Inferred",
                      numeric: true,
                      render: (row) => formatNumber(row.inferred_count),
                    },
                  ]}
                  rows={data.yearly}
                  rowKey={(row) => String(row.year)}
                />
              </TableDisclosure>
            ) : null
          }
        >
          {data.yearly.length > 0 ? (
            <TrendLineChart
              points={data.yearly.map((bucket) => ({ key: bucket.year, value: bucket.publication_count }))}
              secondary={{
                label: "Named in affiliation",
                points: data.yearly.map((bucket) => ({ key: bucket.year, value: bucket.explicit_count })),
              }}
              valueLabel="Publications"
              ariaLabel={`AI publications per year for the ${data.name}`}
              height={260}
            />
          ) : (
            <EmptyState bare title="No publications in this period" />
          )}
        </ChartPanel>

        <ChartPanel
          title="Research areas"
          description="OpenAlex primary topic of each publication."
          table={
            data.research_areas.length > 0 ? (
              <TableDisclosure>{countTable(data.research_areas, "Research area")}</TableDisclosure>
            ) : null
          }
        >
          <RankingBarChart
            entries={data.research_areas.map((row) => ({ label: row.label, value: row.publication_count }))}
            valueLabel="Publications"
            ariaLabel={`Research areas of the ${data.name}`}
            height={320}
          />
        </ChartPanel>
      </div>

      {data.subfields.length > 0 ? (
        <section className="panel p-4">
          <SectionHeading
            title="Fields"
            description="OpenAlex subfields, including the application domains the AI work is applied in."
          />
          <ul className="flex flex-wrap gap-2">
            {data.subfields.map((row) => (
              <li key={row.label} className="chip">
                {row.label}
                <span className="data-mono text-muted">{row.publication_count}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="panel p-4">
        <SectionHeading
          title="Most active researchers"
          description="By AI publications with a department affiliation. The full list is under Researchers."
        />
        {data.top_researchers.length > 0 ? (
          researcherTable(data.top_researchers, true)
        ) : (
          <EmptyState bare title="No researchers in this period" />
        )}
      </section>

      {data.top_cited.length > 0 ? (
        <section>
          <SectionHeading title="Most cited publications" />
          <DepartmentPublicationList publications={data.top_cited} />
        </section>
      ) : null}
    </>
  );

  const researchersTab = (
    <section>
      <SectionHeading
        title="Researchers"
        description="Everyone who published AI research with a department affiliation — academic staff, research staff and students. “Department works” counts their publications in any field that name the department."
      />
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <form method="get" action={basePath} className="flex flex-wrap items-center gap-2">
          {Object.entries({ ...period, tab: "researchers", rsort: researcherSort }).map(([name, value]) =>
            value === undefined ? null : <input key={name} type="hidden" name={name} value={String(value)} />,
          )}
          <label htmlFor="researcher-search" className="sr-only">
            Find a researcher
          </label>
          <input
            id="researcher-search"
            name="rq"
            defaultValue={researcherSearch}
            placeholder="Find a researcher"
            className="rounded-md border border-rule bg-surface px-3 py-1.5 text-body-sm text-ink"
          />
          <button
            type="submit"
            className="interactive rounded-md border border-rule px-3 py-1.5 text-body-sm text-ink-secondary hover:bg-wash hover:text-ink"
          >
            Search
          </button>
        </form>
        <nav aria-label="Sort researchers" className="flex flex-wrap gap-1.5">
          {Object.entries(RESEARCHER_SORTS).map(([value, label]) => (
            <Link
              key={value}
              href={hrefWith(basePath, query, { rsort: value, rpage: undefined, tab: "researchers" })}
              aria-current={value === researcherSort ? "true" : undefined}
              className={`chip ${value === researcherSort ? "chip-filter text-primary" : ""}`}
            >
              {label}
            </Link>
          ))}
        </nav>
      </div>
      {!researchers.ok ? (
        <ApiErrorPanel error={researchers.error} what="researchers" />
      ) : researchers.value.data.length === 0 ? (
        <EmptyState title="No researchers match" />
      ) : (
        <div className="flex flex-col gap-4">
          {researcherTable(researchers.value.data, false)}
          <Pagination
            pagination={researchers.value.pagination}
            basePath={basePath}
            searchParams={{ ...query, tab: "researchers" }}
            pageParam="rpage"
          />
        </div>
      )}
    </section>
  );

  const publicationsTab = (
    <section>
      <SectionHeading
        title="Publications"
        description="AI publications with at least one department author, newest first."
        action={
          <DownloadLink href={departmentExportUrl(data.department_id, { ...period, match, researcher })}>
            Export list (CSV)
          </DownloadLink>
        }
      />
      <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2">
        <nav aria-label="Attribution" className="flex flex-wrap gap-1.5">
          {[{ value: undefined, label: "All" }, ...Object.entries(MATCH_FILTERS).map(([value, label]) => ({ value, label }))].map(
            (option) => (
              <Link
                key={option.label}
                href={hrefWith(basePath, query, { match: option.value, page: undefined, tab: "publications" })}
                aria-current={option.value === match ? "true" : undefined}
                className={`chip ${option.value === match ? "chip-filter text-primary" : ""}`}
              >
                {option.label}
              </Link>
            ),
          )}
        </nav>
        <nav aria-label="Sort publications" className="flex flex-wrap gap-1.5">
          {Object.entries(PUBLICATION_SORTS).map(([value, label]) => (
            <Link
              key={value}
              href={hrefWith(basePath, query, { sort: value, page: undefined, tab: "publications" })}
              aria-current={value === publicationSort ? "true" : undefined}
              className={`chip ${value === publicationSort ? "chip-filter text-primary" : ""}`}
            >
              {label}
            </Link>
          ))}
        </nav>
        {researcher ? (
          <Link
            href={hrefWith(basePath, query, { researcher: undefined, page: undefined, tab: "publications" })}
            className="chip chip-filter text-primary"
            aria-label={`Remove researcher filter ${researcher}`}
          >
            Researcher: {researcher} <span aria-hidden>✕</span>
          </Link>
        ) : null}
      </div>
      {!publications.ok ? (
        <ApiErrorPanel error={publications.error} what="publications" />
      ) : publications.value.data.length === 0 ? (
        <EmptyState title="No publications match these filters" />
      ) : (
        <div className="flex flex-col gap-4">
          <DepartmentPublicationList publications={publications.value.data} />
          <Pagination
            pagination={publications.value.pagination}
            basePath={basePath}
            searchParams={{ ...query, tab: "publications" }}
          />
        </div>
      )}
    </section>
  );

  const collaborationTab = (
    <>
      <ChartPanel
        title="Partner institutions"
        description={`Institutions other than ${data.institution_name} on department publications.`}
        table={
          data.partner_institutions.length > 0 ? (
            <TableDisclosure>
              {countTable(data.partner_institutions, "Institution", (label) => (
                <Link href={institutionHref(label)} className="hover:underline">
                  {label}
                </Link>
              ))}
            </TableDisclosure>
          ) : null
        }
      >
        <RankingBarChart
          entries={data.partner_institutions.map((row) => ({
            label: row.label,
            value: row.publication_count,
            href: institutionHref(row.label),
          }))}
          valueLabel="Shared publications"
          ariaLabel={`Partner institutions of the ${data.name}`}
          clickHint="Open institution profile"
          height={380}
        />
      </ChartPanel>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <section className="panel p-4">
          <SectionHeading title="Partner countries" description="Co-author countries other than Sri Lanka." />
          {data.partner_countries.length > 0 ? (
            countTable(data.partner_countries, "Country", countryName)
          ) : (
            <EmptyState bare title="No international co-authors in this period" />
          )}
        </section>
        <section className="panel p-4">
          <SectionHeading title="Publication venues" description="Journals and proceedings published in most." />
          {data.venues.length > 0 ? (
            countTable(data.venues, "Venue")
          ) : (
            <EmptyState bare title="No venues recorded" />
          )}
        </section>
      </div>
    </>
  );

  const coverageRows = [
    { label: `AI publications with a ${data.institution_name} author`, value: coverage.institution_publications },
    { label: "Name the department in an author affiliation", value: coverage.explicit_publications },
    { label: "Inferred from author history", value: coverage.inferred_publications },
    { label: "Name another department or faculty", value: coverage.other_unit_publications },
    { label: "Name only the university (department unknown)", value: coverage.institution_only_publications },
  ].filter((row) => row.value !== undefined);

  const methodTab = (
    <section className="panel detail-measure p-4">
      <SectionHeading title="How publications are attributed" />
      <div className="flex flex-col gap-3 text-body-sm text-ink-secondary">
        <p>
          The consolidated dataset records institutions, not departments. Publishers and OpenAlex do keep each
          author&apos;s affiliation as written on the paper — for example{" "}
          <q>Dept. of Computer Science &amp; Engineering, University of Moratuwa</q> — and those strings are
          matched against the department&apos;s name and its spelling variants.
        </p>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            <strong className="text-ink">Named in affiliation</strong>: an author&apos;s affiliation on the
            publication names the department at {data.institution_name}.
          </li>
          <li>
            <strong className="text-ink">Inferred from author history</strong>: an author lists only the
            university on the publication, but named the department on at least{" "}
            {data.method.rules.min_history ?? 2} of their other works, and at least{" "}
            {data.method.rules.dominance ?? 2}× as often as any other unit of the university.
          </li>
        </ul>
        {coverageRows.length > 0 ? (
          <DataTable
            fit
            caption="Attribution coverage across the whole collection"
            columns={[
              { key: "label", header: "Publications", render: (row) => row.label },
              {
                key: "value",
                header: "Count",
                numeric: true,
                render: (row) => formatNumber(row.value ?? 0),
              },
            ]}
            rows={coverageRows}
            rowKey={(row) => row.label}
          />
        ) : null}
        <p>
          Limits: researchers include students and visiting staff who used a department affiliation; authors are
          grouped by name, so a person who publishes under two spellings appears twice; and only publications in
          the accepted AI collection are counted.
          {data.method.generated_at ? ` Attribution last built ${formatDateTime(data.method.generated_at)}.` : ""}
        </p>
      </div>
    </section>
  );

  return (
    <div className="flex flex-col gap-4">
      <PrintMeta
        title={`${data.name}, ${data.institution_name}`}
        snapshotDate={profile.value.meta.snapshot_date}
        searchParams={query}
      />
      <ProfileHeader
        title={data.name}
        subtitle={`${data.institution_name} · AI research portfolio`}
        breadcrumbs={breadcrumbs}
        actions={actions}
        notice={notice}
        metrics={metrics}
      />
      <ProfileTabs
        key={initialTab}
        defaultTab={initialTab}
        tabs={[
          { id: "overview", content: overviewTab },
          { id: "researchers", content: researchersTab },
          { id: "publications", content: publicationsTab },
          { id: "collaboration", content: collaborationTab },
          { id: "method", content: methodTab },
        ]}
      />
      <SnapshotNote snapshotDate={profile.value.meta.snapshot_date} datasetStage={profile.value.meta.dataset_stage} />
    </div>
  );
}
