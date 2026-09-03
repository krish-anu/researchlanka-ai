"use client";

import { useCallback } from "react";

import chartData from "@/data/datasetCharts.json";
import { formatNumber } from "@/services/format";

import { PlotlyChart } from "./PlotlyChart";
import { RankingBarChart } from "./RankingBarChart";
import { baseLayout, type ChartTheme } from "./theme";
import { ChartPanel } from "../ui/ChartPanel";

type CountEntry = { label: string; value: number };
type ModelEntry = {
  label: string;
  accuracy: number;
  macroF1: number;
  weightedF1: number;
};

function latestCollectionYears(entries: CountEntry[]): CountEntry[] {
  const currentYear = new Date().getFullYear();
  const recent = entries
    .filter((entry) => {
      const year = Number(entry.label);
      return Number.isInteger(year) && year >= 2016 && year <= currentYear;
    })
    .sort((a, b) => Number(a.label) - Number(b.label));
  return recent.length > 0 ? recent : entries;
}

function PublicationsByYearBarChart({
  entries,
}: {
  entries: CountEntry[];
}) {
  const build = useCallback(
    (theme: ChartTheme) => {
      const base = baseLayout(theme);
      return {
        data: [
          {
            type: "bar",
            x: entries.map((entry) => entry.label),
            y: entries.map((entry) => entry.value),
            marker: {
              color: theme.series[0],
              cornerradius: 4,
            },
            hovertemplate: "Year %{x}<br>Publications: %{y:,}<extra></extra>",
          },
        ],
        layout: {
          ...base,
          bargap: 0.28,
          margin: { l: 56, r: 16, t: 8, b: 44 },
          xaxis: {
            ...(base.xaxis as Record<string, unknown>),
            title: { text: "Publication year", font: { color: theme.muted, size: 11 } },
          },
          yaxis: {
            ...(base.yaxis as Record<string, unknown>),
            title: { text: "Publications", font: { color: theme.muted, size: 11 } },
            rangemode: "tozero",
          },
        },
      };
    },
    [entries],
  );

  return (
    <PlotlyChart
      build={build}
      height={300}
      ariaLabel="Bar chart of publications by publication year"
    />
  );
}

function ModelMetricComparisonChart({
  entries,
}: {
  entries: ModelEntry[];
}) {
  const ordered = [...entries].reverse();
  const build = useCallback(
    (theme: ChartTheme) => {
      const base = baseLayout(theme);
      return {
        data: [
          {
            type: "bar",
            orientation: "h",
            name: "Accuracy",
            x: ordered.map((entry) => entry.accuracy),
            y: ordered.map((entry) => entry.label),
            marker: { color: theme.series[0], cornerradius: 4 },
            text: ordered.map((entry) => `${entry.accuracy.toFixed(1)}%`),
            textposition: "outside",
            textfont: { color: theme.inkSecondary, size: 11 },
            cliponaxis: false,
            hovertemplate: "%{y}<br>Accuracy: %{x:.2f}%<extra></extra>",
          },
          {
            type: "bar",
            orientation: "h",
            name: "Macro F1",
            x: ordered.map((entry) => entry.macroF1),
            y: ordered.map((entry) => entry.label),
            marker: { color: theme.series[1], cornerradius: 4 },
            text: ordered.map((entry) => `${entry.macroF1.toFixed(1)}%`),
            textposition: "outside",
            textfont: { color: theme.inkSecondary, size: 11 },
            cliponaxis: false,
            hovertemplate: "%{y}<br>Macro F1: %{x:.2f}%<extra></extra>",
          },
        ],
        layout: {
          ...base,
          barmode: "group",
          bargap: 0.28,
          showlegend: true,
          legend: {
            orientation: "h",
            y: -0.18,
            font: { color: theme.inkSecondary, size: 11 },
          },
          margin: { l: 112, r: 48, t: 8, b: 48 },
          xaxis: {
            ...(base.xaxis as Record<string, unknown>),
            title: { text: "Score", font: { color: theme.muted, size: 11 } },
            range: [0, 100],
            ticksuffix: "%",
          },
          yaxis: {
            ...(base.yaxis as Record<string, unknown>),
            gridcolor: "rgba(0,0,0,0)",
            automargin: true,
          },
        },
      };
    },
    [ordered],
  );

  return (
    <PlotlyChart
      build={build}
      height={260}
      ariaLabel="Horizontal grouped bar chart comparing model accuracy and macro F1"
    />
  );
}

function ChartTable({
  entries,
  valueLabel = "Records",
}: {
  entries: CountEntry[];
  valueLabel?: string;
}) {
  return (
    <details className="mt-3 border-t border-rule pt-3">
      <summary className="cursor-pointer text-body-sm text-ink-secondary hover:text-ink">
        View values
      </summary>
      <div className="mt-2 overflow-x-auto">
        <table className="min-w-full text-body-sm">
          <thead className="text-left text-muted">
            <tr>
              <th className="py-1 pr-3 font-medium">Label</th>
              <th className="py-1 text-right font-medium">{valueLabel}</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.label} className="border-t border-rule">
                <td className="py-1 pr-3 text-ink">{entry.label}</td>
                <td className="py-1 text-right text-ink-secondary">
                  {formatNumber(entry.value)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

export function DatasetSnapshotCharts() {
  const publicationsByYear = latestCollectionYears(
    chartData.publicationsByYear as CountEntry[],
  );
  const mainSources = chartData.mainSources as CountEntry[];
  const multiSourceCombinations = chartData.multiSourceCombinations as CountEntry[];
  const deduplication = chartData.deduplication as CountEntry[];
  const modelComparison = chartData.modelComparison as ModelEntry[];

  return (
    <section className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <ChartPanel
          title="Publications by year"
          description="Final dataset records from the 2016 onward collection window."
          table={<ChartTable entries={publicationsByYear} valueLabel="Publications" />}
        >
          <PublicationsByYearBarChart entries={publicationsByYear} />
        </ChartPanel>

        <ChartPanel
          title="Collected records by source"
          description="Raw normalized records collected from the four main sources before deduplication."
          table={<ChartTable entries={mainSources} />}
        >
          <RankingBarChart
            entries={mainSources}
            valueLabel="Records"
            ariaLabel="Horizontal bar chart of records collected from the four main sources"
            height={260}
          />
        </ChartPanel>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <ChartPanel
          title="Multi-source coverage"
          description="Final dataset source combinations after merge and repository append."
          table={<ChartTable entries={multiSourceCombinations} />}
        >
          <RankingBarChart
            entries={multiSourceCombinations}
            valueLabel="Records"
            ariaLabel="Horizontal bar chart of source-combination counts"
          />
        </ChartPanel>

        <ChartPanel
          title="Deduplication review signals"
          description="Potential duplicate patterns found in the normalized all-records dataset."
          table={<ChartTable entries={deduplication} valueLabel="Groups" />}
        >
          <RankingBarChart
            entries={deduplication}
            valueLabel="Groups"
            ariaLabel="Horizontal bar chart of deduplication review signal counts"
            height={230}
          />
        </ChartPanel>
      </div>

      <ChartPanel
        title="Model comparison"
        description="Primary-domain classifier accuracy and macro F1 across the three trained models."
      >
        <ModelMetricComparisonChart entries={modelComparison} />
      </ChartPanel>
    </section>
  );
}
