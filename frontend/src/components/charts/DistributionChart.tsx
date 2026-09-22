"use client";

import { useCallback, useState } from "react";
import { RankingBarChart } from "./RankingBarChart";
import { PlotlyChart } from "./PlotlyChart";
import { baseLayout, type ChartTheme } from "./theme";

const swatches = ["var(--seq-450)", "var(--series-2)", "var(--series-1)", "var(--series-3)", "var(--muted)", "var(--baseline)"];

export function DistributionChart({ entries, ariaLabel, initialView = "donut" }: {
  entries: { label: string; value: number }[];
  ariaLabel: string;
  initialView?: "donut" | "mosaic";
}) {
  const [view, setView] = useState<"donut" | "mosaic" | "bar">(initialView);
  const total = entries.reduce((sum, entry) => sum + entry.value, 0);
  const build = useCallback((theme: ChartTheme) => {
    const palette = [theme.sequential, theme.series[1], theme.series[0], theme.series[2], theme.muted, theme.baseline];
    const labels = entries.map(entry => entry.label);
    const values = entries.map(entry => entry.value);
    const marker = {
      colors: entries.map((_, index) => palette[index % palette.length]),
      line: { color: theme.surface, width: 3 },
    };
    return {
      data: [view === "donut" ? {
        type: "pie", labels, values, hole: .7, sort: false, direction: "clockwise",
        textinfo: "none", marker,
        hovertemplate: "%{label}<br>%{value:,} publications · %{percent}<extra></extra>",
      } : {
        type: "treemap", ids: labels, labels, parents: entries.map(() => ""), values,
        textinfo: "label+value+percent root", marker, tiling: { packing: "squarify" },
        hovertemplate: "%{label}<br>%{value:,} publications<extra></extra>",
      }],
      layout: {
        ...baseLayout(theme), margin: { l: 0, r: 0, t: 8, b: 8 }, showlegend: false,
        annotations: view === "donut" ? [{
          x: .5, y: .5, xref: "paper", yref: "paper", text: `<b>${entries.length}</b><br>categories`,
          showarrow: false, font: { size: 15, color: theme.ink },
        }] : [],
      },
    };
  }, [entries, view]);

  return <div>
    <div className="mb-3 flex justify-end">
      <div className="chart-segments" aria-label="Distribution chart style">
        {(["donut", "mosaic", "bar"] as const).map(style => <button key={style} type="button" aria-pressed={view === style} onClick={() => setView(style)}>{style[0].toUpperCase() + style.slice(1)}</button>)}
      </div>
    </div>
    {view === "bar" ? <RankingBarChart entries={entries} valueLabel="AI publications" ariaLabel={ariaLabel} /> :
      <div className={view === "donut" ? "distribution-body" : ""}>
        <div className="min-w-0"><PlotlyChart build={build} height={270} ariaLabel={ariaLabel} /></div>
        {view === "donut" ? <ul className="flex flex-col justify-center gap-3 text-xs text-ink-secondary">
          {entries.map((entry, index) => <li key={entry.label} className="flex items-start justify-between gap-3">
            <span className="flex items-start gap-2"><i aria-hidden="true" className="mt-1 h-2 w-2 shrink-0 rounded-sm" style={{ background: swatches[index % swatches.length] }} />{entry.label}</span>
            <span className="shrink-0 text-right tabular"><strong className="font-medium">{total ? (entry.value / total * 100).toFixed(1) : "0"}%</strong><span className="mt-0.5 block text-[10px] text-muted">{entry.value.toLocaleString()}</span></span>
          </li>)}
        </ul> : null}
      </div>}
  </div>;
}
