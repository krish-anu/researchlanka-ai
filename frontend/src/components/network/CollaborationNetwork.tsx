"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { readChartTheme } from "@/components/charts/theme";
import { institutionHref, researcherHref } from "@/services/links";
import type {
  CollaborationNetwork as NetworkData,
  NetworkNode,
} from "@/types/api";

interface CollaborationNetworkProps {
  network: NetworkData;
  scope: "institution" | "country" | "researcher";
  height?: number;
}

/** What node area encodes. All four ship in the payload, so switching is free. */
type SizeMetric =
  | "publication_count"
  | "degree_centrality"
  | "betweenness_centrality"
  | "closeness_centrality";

const SIZE_METRICS: { value: SizeMetric; label: string; hint: string }[] = [
  {
    value: "publication_count",
    label: "Publications",
    hint: "How much each node published. The volume view.",
  },
  {
    value: "degree_centrality",
    label: "Partners",
    hint: "Share of other nodes each one collaborates with directly.",
  },
  {
    value: "betweenness_centrality",
    label: "Brokerage",
    hint: "Share of shortest paths through each node. Large = bridges otherwise separate groups.",
  },
  {
    value: "closeness_centrality",
    label: "Reach",
    hint: "How near each node sits to everything it can reach.",
  },
];

/**
 * The design system contrast-checks exactly three categorical slots, so only
 * the three largest communities are coloured and the rest stay neutral.
 * Cycling the three would make unrelated communities share a colour, which
 * reads as a claim they are the same group.
 */
const COLOURED_COMMUNITIES = 3;

function metricValue(node: NetworkNode, metric: SizeMetric): number {
  const value = node[metric];
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

/**
 * Cytoscape.js collaboration graph.
 *
 * Loaded lazily on the client — layout is the expensive part and cannot be
 * server-rendered. Node area encodes a selectable structural measure, edge
 * width encodes collaboration weight, and colour marks the three largest
 * detected communities. Size and width carry the magnitudes so nothing
 * essential rests on colour alone; colour only groups.
 *
 * Clicking a node navigates to that entity's profile.
 */
export function CollaborationNetwork({
  network,
  scope,
  height = 460,
}: CollaborationNetworkProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false);
  const [metric, setMetric] = useState<SizeMetric>("publication_count");
  const selectId = useId();

  useEffect(() => {
    let cancelled = false;
    const element = containerRef.current;
    if (!element || network.nodes.length === 0) return;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let instance: any = null;

    (async () => {
      try {
        const cytoscape = (await import("cytoscape")).default;
        if (cancelled) return;

        const theme = readChartTheme();
        // Scale against the largest value actually present, so the spread fills
        // the size range whichever measure is selected. Betweenness is often
        // zero for most nodes, which would otherwise collapse every circle.
        const values = network.nodes.map((node) => metricValue(node, metric));
        const maxValue = Math.max(...values, 0) || 1;
        const maxWeight = Math.max(1, ...network.edges.map((edge) => edge.weight));
        const communityColour = (community: number) =>
          community >= 0 && community < COLOURED_COMMUNITIES
            ? theme.series[community]
            : theme.muted;

        instance = cytoscape({
          container: element,
          elements: [
            ...network.nodes.map((node) => ({
              data: {
                id: node.id,
                label: node.label,
                size: 14 + (metricValue(node, metric) / maxValue) * 34,
                colour: communityColour(node.community),
                count: node.publication_count,
              },
            })),
            ...network.edges.map((edge, index) => ({
              data: {
                id: `e${index}`,
                source: edge.source,
                target: edge.target,
                width: 1 + (edge.weight / maxWeight) * 5,
                weight: edge.weight,
              },
            })),
          ],
          style: [
            {
              selector: "node",
              style: {
                "background-color": "data(colour)",
                "border-color": theme.surface,
                "border-width": 2,
                width: "data(size)",
                height: "data(size)",
                label: "data(label)",
                "font-size": 10,
                color: theme.inkSecondary,
                "text-valign": "bottom",
                "text-margin-y": 4,
                "text-max-width": "110px",
                "text-wrap": "ellipsis",
                "min-zoomed-font-size": 8,
              },
            },
            {
              selector: "edge",
              style: {
                "line-color": theme.baseline,
                width: "data(width)",
                "curve-style": "haystack",
                opacity: 0.65,
              },
            },
            {
              // Fill now carries community, so selection is marked with the
              // border instead — overriding the fill would misreport the group.
              selector: "node:selected",
              style: {
                "border-color": theme.ink,
                "border-width": 4,
              },
            },
          ],
          layout: {
            name: "cose",
            animate: false,
            nodeDimensionsIncludeLabels: true,
            padding: 24,
          },
          minZoom: 0.2,
          maxZoom: 3,
          wheelSensitivity: 0.2,
        });

        // Node click -> profile page, per the "click a node to open a profile"
        // requirement. Country scope has no profile route, so it stays inert.
        instance.on("tap", "node", (event: { target: { data: (k: string) => string } }) => {
          const label = event.target.data("label");
          if (scope === "institution") router.push(institutionHref(label));
          else if (scope === "researcher") router.push(researcherHref(label));
        });

        if (!cancelled) setReady(true);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();

    return () => {
      cancelled = true;
      instance?.destroy();
    };
  }, [network, scope, router, metric]);

  if (network.nodes.length === 0) {
    return (
      <p className="p-4 text-body-sm text-muted">
        No collaboration edges met the current filters and minimum weight. Try
        widening the year range or lowering the minimum weight.
      </p>
    );
  }

  if (failed) {
    return (
      <p className="p-4 text-body-sm text-muted">
        The network graph could not be loaded. Collaboration pairs are listed in
        the table below.
      </p>
    );
  }

  const selected = SIZE_METRICS.find((entry) => entry.value === metric);
  const communityCount = network.summary?.community_count ?? 0;
  const uncoloured = Math.max(0, communityCount - COLOURED_COMMUNITIES);

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <label htmlFor={selectId} className="label-caps text-muted">
          Size nodes by
        </label>
        <select
          id={selectId}
          value={metric}
          onChange={(event) => setMetric(event.target.value as SizeMetric)}
          className="rounded border border-rule bg-surface px-2 py-1 text-body-sm text-ink"
        >
          {SIZE_METRICS.map((entry) => (
            <option key={entry.value} value={entry.value}>
              {entry.label}
            </option>
          ))}
        </select>
        {selected ? (
          <span className="text-body-sm text-ink-secondary">{selected.hint}</span>
        ) : null}
      </div>

      <div className="relative">
        <div
          ref={containerRef}
          style={{ height }}
          className="w-full rounded border border-rule bg-surface"
        />
        {!ready ? (
          <p className="absolute inset-0 flex items-center justify-center text-body-sm text-muted">
            Laying out network…
          </p>
        ) : null}
      </div>

      {communityCount > 0 ? (
        <ul className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
          {Array.from(
            { length: Math.min(communityCount, COLOURED_COMMUNITIES) },
            (_, index) => (
              <li
                key={index}
                className="flex items-center gap-2 text-body-sm text-ink-secondary"
              >
                <span
                  aria-hidden
                  className="inline-block h-3 w-3 rounded-full"
                  style={{ backgroundColor: `var(--series-${index + 1})` }}
                />
                Community #{index}
                {index === 0 ? " (largest)" : ""}
              </li>
            ),
          )}
          {uncoloured > 0 ? (
            <li className="flex items-center gap-2 text-body-sm text-ink-secondary">
              <span
                aria-hidden
                className="inline-block h-3 w-3 rounded-full"
                style={{ backgroundColor: "var(--muted)" }}
              />
              {uncoloured} smaller {uncoloured === 1 ? "community" : "communities"}
            </li>
          ) : null}
        </ul>
      ) : null}

      <p className="mt-2 text-body-sm text-muted">
        Node size is {selected?.label.toLowerCase() ?? "publication count"}; edge
        thickness is the number of shared publications; colour marks the
        {communityCount > COLOURED_COMMUNITIES ? " three largest" : ""} detected
        communities. Scroll to zoom, drag to pan
        {scope === "country" ? "." : ", and click a node to open its profile."}
      </p>
    </div>
  );
}
