import Link from "next/link";
import { ActivityHeatmap } from "@/components/charts/ActivityHeatmap";
import { DistributionChart } from "@/components/charts/DistributionChart";
import { InstitutionScatterChart } from "@/components/charts/InstitutionScatterChart";
import { ScopedAccessibilityChart } from "@/components/institutions/CompareTray";
import { TrendLineChart } from "@/components/charts/TrendLineChart";
import { CollaborationNetwork } from "@/components/network/CollaborationNetwork";
import { NetworkBrokersTable, NetworkSummaryPanel } from "@/components/network/NetworkMetrics";
import { ChartExportMenu } from "@/components/ui/ChartExportMenu";
import { ChartPanel } from "@/components/ui/ChartPanel";
import { DataTable, TableDisclosure } from "@/components/ui/DataTable";
import { ApiErrorPanel, EmptyState } from "@/components/ui/Feedback";
import {
  getAnalyticsTrends,
  getCollaborationNetwork,
  analyticsExportUrl,
  buildQuery,
  type QueryParams,
} from "@/services/api";
import {
  filtersNarrowSelection,
  withSelectionScope,
} from "@/services/copy";
import {
  fieldShareInsight,
  networkInsight,
  trendInsight,
} from "@/services/derive";
import { formatNumber, formatRatioAsPercent } from "@/services/format";
import { institutionHref } from "@/services/links";
import type { RankingEntry, TrendPoint } from "@/types/api";

/** An open-access subset of an explicitly non-open selection is empty. */
function openAccessTrends(filters: QueryParams & { group_by?: "year" | "institution" }) {
  if (filters.is_oa === false || filters.is_oa === "false") {
    return Promise.resolve({ ok: true as const, value: { data: [] as TrendPoint[] } });
  }
  return getAnalyticsTrends({ ...filters, is_oa: true });
}

export async function TrendPanel({ filters }: { filters: QueryParams }) {
  const params = { ...filters, group_by: "year" as const };
  const scoped = filtersNarrowSelection(filters);
  const [result, openAccess] = await Promise.all([
    getAnalyticsTrends(params),
    openAccessTrends(params),
  ]);
  if (!result.ok) return <ApiErrorPanel error={result.error} what="AI publication trends" />;
  const points = [...result.value.data].sort((a, b) => Number(a.key) - Number(b.key));
  const oa = new Map(
    openAccess.ok
      ? openAccess.value.data.map((p) => [String(p.key), p.publication_count])
      : [],
  );
  const insight = trendInsight(points, openAccess.ok ? oa : undefined);

  return (
    <ChartPanel
      title="AI research output over time"
      description={withSelectionScope(
        "Annual publication count by year",
        scoped,
      )}
      insight={insight}
      action={<ChartExportMenu csvHref={analyticsExportUrl("trends", params)} />}
      table={
        <TableDisclosure>
          <DataTable
            rows={points}
            rowKey={(p) => String(p.key)}
            columns={[
              { key: "year", header: "Year", render: (p) => String(p.key) },
              {
                key: "count",
                header: "AI publications",
                numeric: true,
                render: (p) => formatNumber(p.publication_count),
              },
              {
                key: "oa",
                header: "Open access",
                numeric: true,
                render: (p) =>
                  openAccess.ok
                    ? formatNumber(oa.get(String(p.key)) ?? 0)
                    : "Unavailable",
              },
            ]}
          />
        </TableDisclosure>
      }
    >
      {points.length ? (
        <TrendLineChart
          points={points.map((p) => ({ key: p.key, value: p.publication_count }))}
          valueLabel="AI publications"
          ariaLabel="AI publication output by year"
          secondary={
            openAccess.ok
              ? {
                label: "Open access",
                points: points.map((p) => ({
                  key: p.key,
                  value: oa.get(String(p.key)) ?? 0,
                })),
              }
              : undefined
          }
          clearHref={scoped ? "/" : undefined}
        />
      ) : (
        <EmptyState
          bare
          title="No annual data in this selection"
          description={scoped ? "Try removing a year or field filter to widen the results." : undefined}
          recovery={scoped ? { kind: "clear-filters", href: "/" } : undefined}
        />
      )}
    </ChartPanel>
  );
}

export async function FieldDistributionPanel({
  entries,
  filters,
  total,
}: {
  entries: RankingEntry[];
  filters: QueryParams;
  total?: number;
}) {
  const scoped = filtersNarrowSelection(filters);
  const leading = entries.slice(0, 5).map((e) => ({
    label: e.label,
    value: e.publication_count,
  }));
  const represented = entries.reduce((sum, e) => sum + e.publication_count, 0);
  const remaining = Math.max(
    0,
    (total ?? represented) - leading.reduce((sum, e) => sum + e.value, 0),
  );
  const tableRows = [
    ...entries.map((e) => ({ label: e.label, value: e.publication_count })),
    ...(total !== undefined && total > represented
      ? [{ label: "Other / unclassified", value: total - represented }]
      : []),
  ];
  const slices = [
    ...leading,
    ...(remaining
      ? [
        {
          label:
            total === undefined
              ? "Other displayed fields"
              : "Other / unclassified",
          value: remaining,
        },
      ]
      : []),
  ];
  const insight = fieldShareInsight(leading);

  return (
    <ChartPanel
      title="The AI research landscape"
      description={withSelectionScope(
        "Publications by primary field (top 5)",
        scoped,
      )}
      insight={insight}
      action={<ChartExportMenu csvHref={analyticsExportUrl("fields", filters)} />}
      table={
        <TableDisclosure>
          <DataTable
            rows={tableRows}
            rowKey={(e) => e.label}
            columns={[
              {
                key: "field",
                header: "Field",
                render: (e) =>
                  e.label === "Other / unclassified" ? (
                    e.label
                  ) : (
                    <Link
                      href={`/publications${buildQuery({ ...filters, field: [e.label] })}`}
                      className="hover:underline"
                    >
                      {e.label}
                    </Link>
                  ),
              },
              {
                key: "count",
                header: "AI publications",
                numeric: true,
                render: (e) => formatNumber(e.value),
              },
            ]}
          />
        </TableDisclosure>
      }
    >
      {slices.length ? (
        <DistributionChart
          entries={slices}
          initialView="mosaic"
          ariaLabel="AI publications by primary research field"
        />
      ) : (
        <EmptyState bare title="No field data in this selection" />
      )}
    </ChartPanel>
  );
}

export async function ActivityPanel({
  filters,
  fields,
}: {
  filters: QueryParams;
  fields: string[];
}) {
  const scoped = filtersNarrowSelection(filters);
  const lastYear = Number(filters.year_max) || new Date().getFullYear();
  const firstYear = Math.max(
    Number(filters.year_min) || lastYear - 4,
    lastYear - 4,
  );
  const years = Array.from(
    { length: Math.max(0, Math.min(5, lastYear - firstYear + 1)) },
    (_, i) => firstYear + i,
  );
  const selected = fields.slice(0, 5);
  if (!selected.length || !years.length) {
    return <EmptyState title="No field activity in this selection" />;
  }
  const results = await Promise.all(
    selected.map((field) =>
      getAnalyticsTrends({
        ...filters,
        field: [field],
        year_min: firstYear,
        year_max: lastYear,
        group_by: "year",
      }),
    ),
  );
  const failure = results.find((result) => !result.ok);
  if (failure && !failure.ok) {
    return <ApiErrorPanel error={failure.error} what="field activity" />;
  }
  const rows = results.map((result, i) => ({
    label: selected[i],
    values: years.map((year) =>
      result.ok
        ? (result.value.data.find((p) => Number(p.key) === year)
          ?.publication_count ?? 0)
        : 0,
    ),
  }));
  const ranked = [...rows].sort(
    (a, b) =>
      b.values.reduce((sum, n) => sum + n, 0) -
      a.values.reduce((sum, n) => sum + n, 0),
  );
  const hottest = ranked[0];
  const insight = hottest
    ? `${hottest.label} has the highest total across ${firstYear}–${lastYear} in this heatmap.`
    : undefined;

  return (
    <ChartPanel
      title="Where AI research is growing"
      description={withSelectionScope(
        `Annual publication counts for leading fields, ${firstYear}–${lastYear}`,
        scoped,
      )}
      insight={insight}
      action={
        <ChartExportMenu
          csv={{
            filename: "ai-field-activity.csv",
            headers: ["Field", ...years.map(String)],
            rows: rows.map((r) => [r.label, ...r.values]),
          }}
        />
      }
      table={
        <TableDisclosure>
          <DataTable
            rows={rows}
            rowKey={(r) => r.label}
            columns={[
              { key: "field", header: "Field", render: (r) => r.label },
              ...years.map((year, i) => ({
                key: String(year),
                header: String(year),
                numeric: true,
                render: (r: (typeof rows)[number]) => formatNumber(r.values[i]),
              })),
            ]}
          />
        </TableDisclosure>
      }
    >
      <ActivityHeatmap years={years} rows={rows} />
    </ChartPanel>
  );
}

export async function InstitutionAccessibilityPanel({
  filters,
  entries,
  scopeToCompare = false,
}: {
  filters: QueryParams;
  entries: RankingEntry[];
  scopeToCompare?: boolean;
}) {
  const scoped = filtersNarrowSelection(filters);
  const openAccess = await openAccessTrends({
    ...filters,
    group_by: "institution",
  });
  if (!openAccess.ok) {
    return (
      <ApiErrorPanel error={openAccess.error} what="institution open access data" />
    );
  }
  const counts = new Map(
    openAccess.value.data.map((row) => [String(row.key), row.publication_count]),
  );
  const points = entries
    .slice(0, 15)
    .filter((e) => e.publication_count > 0)
    .map((e) => ({
      label: e.label,
      publications: e.publication_count,
      openAccessShare: (counts.get(e.label) ?? 0) / e.publication_count,
    }));
  const volumeLead = [...points].sort(
    (a, b) => b.publications - a.publications,
  )[0];
  const insight = volumeLead
    ? `${volumeLead.label} leads volume here (${formatNumber(volumeLead.publications)} publications; ${formatRatioAsPercent(volumeLead.openAccessShare)} open access).`
    : undefined;

  return (
    <ChartPanel
      title="Output & accessibility"
      description={withSelectionScope(
        "Publication volume versus open-access share by institution",
        scoped,
      )}
      insight={insight}
      action={
        <ChartExportMenu
          csv={{
            filename: "ai-institution-accessibility.csv",
            headers: ["Institution", "AI publications", "Open access share"],
            rows: points.map((p) => [
              p.label,
              p.publications,
              p.openAccessShare,
            ]),
          }}
        />
      }
      table={
        <TableDisclosure>
          <DataTable
            rows={points}
            rowKey={(p) => p.label}
            columns={[
              {
                key: "name",
                header: "Institution",
                render: (p) => (
                  <Link
                    href={institutionHref(p.label)}
                    className="hover:underline"
                  >
                    {p.label}
                  </Link>
                ),
              },
              {
                key: "count",
                header: "AI publications",
                numeric: true,
                render: (p) => formatNumber(p.publications),
              },
              {
                key: "oa",
                header: "Open access",
                numeric: true,
                render: (p) => formatRatioAsPercent(p.openAccessShare),
              },
            ]}
          />
        </TableDisclosure>
      }
    >
      {scopeToCompare ? (
        <ScopedAccessibilityChart points={points} />
      ) : (
        <InstitutionScatterChart
          points={points}
          clearHref={scoped ? "/institutions" : undefined}
        />
      )}
    </ChartPanel>
  );
}

export async function NetworkPanel({
  filters,
  scope = "institution",
  limit,
  minWeight = 1,
  compact = false,
}: {
  filters: QueryParams;
  scope?: "institution" | "country" | "researcher";
  limit?: number;
  minWeight?: number;
  /** Overview teaser: fewer nodes, shorter canvas, no brokers table. */
  compact?: boolean;
}) {
  const nodeLimit = limit ?? (compact ? 40 : 120);
  const scoped = filtersNarrowSelection(filters);
  const network = await getCollaborationNetwork({
    ...filters,
    scope,
    limit: nodeLimit,
    min_weight: minWeight,
  });
  if (!network.ok) {
    return <ApiErrorPanel error={network.error} what="the collaboration network" />;
  }
  const edgeCount = network.value.data.edges.length;
  const nodeCount = network.value.data.nodes.length;
  const insight = networkInsight(nodeCount, edgeCount, scope);
  const collabHref = `/collaboration${buildQuery({ ...filters, scope })}`;

  return (
    <ChartPanel
      title="AI research is a shared endeavour"
      description={withSelectionScope(
        compact
          ? "Preview of collaboration links — open the full map to explore"
          : "Collaboration links counted by shared publications",
        scoped,
      )}
      insight={insight}
      action={
        <div className="flex flex-wrap items-center gap-3">
          <Link
            href={collabHref}
            className="text-body-sm font-medium text-primary hover:underline"
          >
            Explore collaborations →
          </Link>
          <ChartExportMenu
            csv={{
              filename: "ai-collaboration-pairs.csv",
              headers: ["Entity", "Collaborator", "Shared AI publications"],
              rows: network.value.data.edges.map((e) => [
                e.source_label ?? e.source,
                e.target_label ?? e.target,
                e.weight,
              ]),
            }}
          />
        </div>
      }
      table={
        <TableDisclosure label="View collaboration pairs as table">
          <DataTable
            rows={network.value.data.edges}
            rowKey={(r, i) => `${r.source}-${r.target}-${i}`}
            columns={[
              {
                key: "source",
                header: "Entity",
                render: (r) => r.source_label ?? r.source,
              },
              {
                key: "target",
                header: "Collaborator",
                render: (r) => r.target_label ?? r.target,
              },
              {
                key: "weight",
                header: "Shared AI publications",
                numeric: true,
                render: (r) => formatNumber(r.weight),
              },
            ]}
          />
        </TableDisclosure>
      }
    >
      <div className="flex flex-col gap-5">
        <CollaborationNetwork
          network={network.value.data}
          scope={scope}
          compact={compact}
          height={compact ? 340 : 380}
        />
        {!compact ? (
          <>
            <NetworkSummaryPanel summary={network.value.data.summary} />
            <div>
              <h3 className="mb-2 text-h3">
                Bridging{" "}
                {scope === "institution"
                  ? "institutions"
                  : scope === "researcher"
                    ? "researchers"
                    : "countries"}
              </h3>
              <p className="mb-3 text-body-sm text-muted">
                Ranked by their role connecting otherwise separate groups, rather
                than publication volume.
              </p>
              <NetworkBrokersTable nodes={network.value.data.nodes} />
            </div>
          </>
        ) : (
          <p className="text-body-sm text-ink-secondary">
            Showing up to {formatNumber(nodeLimit)} nodes.{" "}
            <Link href={collabHref} className="font-medium text-primary hover:underline">
              Open the full collaboration map
            </Link>{" "}
            for brokers, communities, and denser filters.
          </p>
        )}
      </div>
    </ChartPanel>
  );
}
