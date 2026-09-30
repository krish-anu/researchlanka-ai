"use client";

import Link from "next/link";
import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";

import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/Feedback";
import { readChartTheme } from "@/components/charts/theme";
import { formatDecimal, formatNumber } from "@/services/format";
import { institutionHref, researcherHref } from "@/services/links";
import type {
  CollaborationNetwork as NetworkData,
  NetworkEdge,
  NetworkNode,
} from "@/types/api";

interface CollaborationNetworkProps {
  network: NetworkData;
  scope: "institution" | "country" | "researcher";
  height?: number;
  /** Overview teaser: shorter canvas, no brokers chrome (parent handles). */
  compact?: boolean;
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
    hint: "Node size follows publication count.",
  },
  {
    value: "degree_centrality",
    label: "Partners",
    hint: "Node size follows direct partners.",
  },
  {
    value: "betweenness_centrality",
    label: "Brokerage",
    hint: "Node size follows bridging position.",
  },
  {
    value: "closeness_centrality",
    label: "Reach",
    hint: "Node size follows closeness.",
  },
];

/**
 * The design system contrast-checks exactly three categorical slots, so only
 * the three largest communities are coloured and the rest stay neutral.
 */
const COLOURED_COMMUNITIES = 3;

const MIN_DIAMETER = 14;
const DIAMETER_RANGE = 34;
const MOBILE_MQ = "(max-width: 767px)";

function metricValue(node: NetworkNode, metric: SizeMetric): number {
  const value = node[metric];
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function diameters(nodes: NetworkNode[], metric: SizeMetric): Map<string, number> {
  let maxValue = 0;
  for (const node of nodes) {
    const value = metricValue(node, metric);
    if (value > maxValue) maxValue = value;
  }
  const divisor = maxValue || 1;
  return new Map(
    nodes.map((node) => [
      node.id,
      MIN_DIAMETER + (metricValue(node, metric) / divisor) * DIAMETER_RANGE,
    ]),
  );
}

function profileHref(
  scope: CollaborationNetworkProps["scope"],
  label: string,
): string | null {
  if (scope === "institution") return institutionHref(label);
  if (scope === "researcher") return researcherHref(label);
  return null;
}

function partnersForNode(
  nodeId: string,
  edges: NetworkEdge[],
  nodesById: Map<string, NetworkNode>,
  limit = 8,
): { label: string; weight: number; href: string | null; id: string }[] {
  const out: { label: string; weight: number; id: string }[] = [];
  for (const edge of edges) {
    if (edge.source === nodeId) {
      out.push({
        id: edge.target,
        label: edge.target_label ?? nodesById.get(edge.target)?.label ?? edge.target,
        weight: edge.weight,
      });
    } else if (edge.target === nodeId) {
      out.push({
        id: edge.source,
        label: edge.source_label ?? nodesById.get(edge.source)?.label ?? edge.source,
        weight: edge.weight,
      });
    }
  }
  return out
    .sort((a, b) => b.weight - a.weight || a.label.localeCompare(b.label))
    .slice(0, limit)
    .map((p) => ({ ...p, href: null }));
}

type CytoscapeModule = typeof import("cytoscape");

let cytoscapePromise: Promise<CytoscapeModule> | null = null;

function loadCytoscape(): Promise<CytoscapeModule> {
  cytoscapePromise ??= import("cytoscape").then((module) => module.default);
  return cytoscapePromise;
}

/**
 * Cytoscape collaboration graph with select-to-inspect.
 * Mobile defaults to adjacency table; graph is optional behind “Show map”.
 */
export function CollaborationNetwork({
  network,
  scope,
  height = 380,
  compact = false,
}: CollaborationNetworkProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const instanceRef = useRef<any>(null);
  const inspectorRef = useRef<HTMLElement | null>(null);
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false);
  const [visible, setVisible] = useState(false);
  const [focusId, setFocusId] = useState("");
  const [metric, setMetric] = useState<SizeMetric>("publication_count");
  const [isMobile, setIsMobile] = useState(false);
  const [showMap, setShowMap] = useState(false);
  const sizeSelectId = useId();
  const exploreSelectId = useId();
  const canvasId = useId();

  const metricRef = useRef(metric);
  metricRef.current = metric;
  const focusIdRef = useRef(focusId);
  focusIdRef.current = focusId;

  const hasNodes = network.nodes.length > 0;
  const graphVisible = !isMobile || showMap;
  const canvasHeight = compact ? Math.min(height, 240) : height;
  const controlsDisabled = graphVisible && !ready;

  const nodesById = useMemo(() => {
    const map = new Map<string, NetworkNode>();
    for (const node of network.nodes) map.set(node.id, node);
    return map;
  }, [network.nodes]);

  const focusedNode = focusId ? nodesById.get(focusId) : undefined;
  const focusedHref = focusedNode
    ? profileHref(scope, focusedNode.label)
    : null;

  const topPartners = useMemo(() => {
    if (!focusedNode) return [];
    return partnersForNode(focusedNode.id, network.edges, nodesById).map((p) => ({
      ...p,
      href: profileHref(scope, p.label),
    }));
  }, [focusedNode, network.edges, nodesById, scope]);

  const adjacencyRows = useMemo(
    () =>
      [...network.edges]
        .sort((a, b) => b.weight - a.weight)
        .slice(0, compact ? 12 : 40)
        .map((edge) => ({
          key: `${edge.source}-${edge.target}`,
          source: edge.source_label ?? edge.source,
          target: edge.target_label ?? edge.target,
          weight: edge.weight,
        })),
    [network.edges, compact],
  );

  const selected = useMemo(
    () => SIZE_METRICS.find((entry) => entry.value === metric),
    [metric],
  );

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia(MOBILE_MQ);
    const apply = () => setIsMobile(mq.matches);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);

  useEffect(() => {
    if (!graphVisible || !hasNodes) return;
    const element = containerRef.current;
    if (!element) return;
    if (typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [hasNodes, graphVisible]);

  useEffect(() => {
    if (!visible || !hasNodes || !graphVisible) return;
    let cancelled = false;
    const element = containerRef.current;
    if (!element) return;

    loadCytoscape()
      .then((cytoscape) => {
        if (cancelled) return;

        const theme = readChartTheme();
        const sizes = diameters(network.nodes, metricRef.current);
        let maxWeight = 1;
        for (const edge of network.edges) {
          if (edge.weight > maxWeight) maxWeight = edge.weight;
        }
        const communityColour = (community: number) =>
          community >= 0 && community < COLOURED_COMMUNITIES
            ? theme.series[community]
            : theme.muted;

        const instance = cytoscape({
          container: element,
          elements: [
            ...network.nodes.map((node) => ({
              data: {
                id: node.id,
                label: node.label,
                size: sizes.get(node.id) ?? MIN_DIAMETER,
                colour: communityColour(node.community),
                community: node.community,
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
            { selector: ".dimmed", style: { opacity: 0.12 } },
            {
              selector: "node",
              style: {
                "background-color": "data(colour)",
                "border-color": theme.surface,
                "border-width": 1.5,
                width: "data(size)",
                height: "data(size)",
                label: "data(label)",
                "font-size": 12,
                color: theme.ink,
                "text-outline-width": 2,
                "text-outline-color": theme.surface,
                "text-valign": "bottom",
                "text-margin-y": 6,
                "text-max-width": "140px",
                "text-wrap": "ellipsis",
                "min-zoomed-font-size": 10,
              },
            },
            {
              selector: "edge",
              style: {
                "line-color": theme.muted,
                width: "data(width)",
                "curve-style": "bezier",
                "control-point-step-size": 40,
                opacity: 0.35,
              },
            },
            {
              selector: "node:selected",
              style: {
                "border-color": theme.ink,
                "border-width": 4,
                "overlay-opacity": 0.08,
                "overlay-color": theme.ink,
                "overlay-padding": 6,
              },
            },
          ],
          layout: {
            name: "cose",
            animate: false,
            nodeDimensionsIncludeLabels: true,
            padding: 24,
          },
          minZoom: 0.65,
          maxZoom: 2.4,
          wheelSensitivity: 1,
        });

        // Select-to-inspect — profile opens from the inspector CTA.
        instance.on(
          "tap",
          "node",
          (event: { target: { id: () => string } }) => {
            setFocusId(event.target.id());
          },
        );
        instance.on("tap", (event: { target: unknown }) => {
          if (event.target === instance) setFocusId("");
        });

        instanceRef.current = instance;
        setReady(true);

        // Restore focus styling if a node was already selected (e.g. from select).
        const currentFocus = focusIdRef.current;
        if (currentFocus) {
          const node = instance.getElementById(currentFocus);
          if (node.nonempty()) {
            const neighborhood = node.closedNeighborhood();
            instance.elements().difference(neighborhood).addClass("dimmed");
            node.select();
          }
        }
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });

    return () => {
      cancelled = true;
      instanceRef.current?.destroy();
      instanceRef.current = null;
      setReady(false);
    };
  }, [network, visible, hasNodes, graphVisible]);

  useEffect(() => {
    if (!ready) return;
    const recolour = () => {
      const instance = instanceRef.current;
      if (!instance) return;
      const theme = readChartTheme();
      instance.batch(() => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        instance.nodes().forEach((node: any) => {
          const community = node.data("community");
          node.data(
            "colour",
            community >= 0 && community < COLOURED_COMMUNITIES
              ? theme.series[community]
              : theme.muted,
          );
        });
      });
      instance
        .style()
        .selector("node")
        .style({ "border-color": theme.surface, color: theme.inkSecondary })
        .selector("edge")
        .style({ "line-color": theme.baseline })
        .selector("node:selected")
        .style({ "border-color": theme.ink })
        .update();
    };
    window.addEventListener("researchlanka-theme-change", recolour);
    return () => window.removeEventListener("researchlanka-theme-change", recolour);
  }, [ready]);

  useEffect(() => {
    const instance = instanceRef.current;
    if (!instance || !ready) return;
    const sizes = diameters(network.nodes, metric);
    instance.batch(() => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      instance.nodes().forEach((node: any) => {
        node.data("size", sizes.get(node.id()) ?? MIN_DIAMETER);
      });
    });
  }, [metric, network, ready]);

  useEffect(() => {
    const instance = instanceRef.current;
    if (!instance || !ready) return;
    instance.elements().removeClass("dimmed");
    instance.nodes().unselect();
    if (focusId) {
      const node = instance.getElementById(focusId);
      if (node.nonempty()) {
        const neighborhood = node.closedNeighborhood();
        instance.elements().difference(neighborhood).addClass("dimmed");
        node.select();
      }
    }
  }, [focusId, ready]);

  useEffect(() => {
    if (!focusId) return;
    // Move keyboard users to the inspector after select / Explore change.
    inspectorRef.current?.focus({ preventScroll: true });
  }, [focusId]);

  const resetView = () => {
    setFocusId("");
    instanceRef.current?.fit(undefined, 24);
  };

  const savePng = () => {
    const instance = instanceRef.current;
    if (!instance) return;
    const link = document.createElement("a");
    link.download = "researchlanka-ai-collaborations.png";
    link.href = instance.png({
      bg: readChartTheme().surface,
      full: true,
      scale: 2,
    });
    link.click();
  };

  const onCanvasKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const instance = instanceRef.current;
    if (!instance || !ready) return;
    const panStep = 40;
    if (event.key === "Escape") {
      event.preventDefault();
      setFocusId("");
      return;
    }
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      instance.panBy({ x: panStep, y: 0 });
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      instance.panBy({ x: -panStep, y: 0 });
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      instance.panBy({ x: 0, y: panStep });
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      instance.panBy({ x: 0, y: -panStep });
    } else if (event.key === "+" || event.key === "=") {
      event.preventDefault();
      instance.zoom({
        level: instance.zoom() * 1.15,
        renderedPosition: {
          x: instance.width() / 2,
          y: instance.height() / 2,
        },
      });
    } else if (event.key === "-" || event.key === "_") {
      event.preventDefault();
      instance.zoom({
        level: instance.zoom() / 1.15,
        renderedPosition: {
          x: instance.width() / 2,
          y: instance.height() / 2,
        },
      });
    }
  };

  if (!hasNodes) {
    return (
      <EmptyState
        bare
        title="No collaboration edges in this selection"
        description="Try widening the year range or lowering the minimum weight."
      />
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

  const communityCount = network.summary?.community_count ?? 0;
  const uncoloured = Math.max(0, communityCount - COLOURED_COMMUNITIES);

  const inspector = focusedNode ? (
    <aside
      className="network-inspector rounded-lg border border-rule bg-wash p-4 text-body-sm"
      aria-label={`Selected: ${focusedNode.label}`}
      data-selected="true"
      tabIndex={-1}
      ref={inspectorRef}
    >
      <h3 className="font-medium text-ink">{focusedNode.label}</h3>
      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-body-sm">
        <div>
          <dt className="text-muted">Publications</dt>
          <dd className="tabular text-ink">
            {formatNumber(focusedNode.publication_count)}
          </dd>
        </div>
        <div>
          <dt className="text-muted">Co-publications</dt>
          <dd className="tabular text-ink">{formatNumber(focusedNode.strength)}</dd>
        </div>
        <div>
          <dt className="text-muted">Partners</dt>
          <dd className="tabular text-ink">
            {formatDecimal(focusedNode.degree_centrality, 3)}
          </dd>
        </div>
        <div>
          <dt className="text-muted">Brokerage</dt>
          <dd className="tabular text-ink">
            {formatDecimal(focusedNode.betweenness_centrality, 3)}
          </dd>
        </div>
      </dl>
      {topPartners.length > 0 ? (
        <div className="mt-3 border-t border-rule pt-3">
          <p className="label-caps text-muted">Top partners</p>
          <ul className="mt-2 space-y-1.5">
            {topPartners.map((partner) => (
              <li
                key={partner.id}
                className="flex items-baseline justify-between gap-2 text-body-sm"
              >
                {partner.href ? (
                  <Link
                    href={partner.href}
                    className="min-w-0 truncate text-primary hover:underline"
                  >
                    {partner.label}
                  </Link>
                ) : (
                  <span className="min-w-0 truncate text-ink">{partner.label}</span>
                )}
                <span className="shrink-0 tabular text-muted">
                  {formatNumber(partner.weight)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {focusedHref ? (
        <Link
          href={focusedHref}
          className="mt-3 inline-block text-body-sm text-primary hover:underline"
        >
          Open full profile →
        </Link>
      ) : null}
    </aside>
  ) : (
    <aside className="network-inspector hidden rounded-lg border border-dashed border-rule bg-wash/50 p-4 text-body-sm text-muted md:block">
      Select a node on the map or from Explore to see metrics and top partners.
    </aside>
  );

  const adjacencyTable = (
    <div className="overflow-x-auto rounded-lg border border-rule">
      <table className="w-full text-left text-body-sm">
        <caption className="sr-only">Collaboration pairs by shared publications</caption>
        <thead className="border-b border-rule bg-wash text-body-sm text-muted">
          <tr>
            <th className="px-3 py-2 font-medium">Entity</th>
            <th className="px-3 py-2 font-medium">Collaborator</th>
            <th className="px-3 py-2 text-right font-medium">Shared</th>
          </tr>
        </thead>
        <tbody>
          {adjacencyRows.map((row) => (
            <tr key={row.key} className="border-b border-rule last:border-0">
              <td className="px-3 py-2 text-ink">{row.source}</td>
              <td className="px-3 py-2 text-ink">{row.target}</td>
              <td className="px-3 py-2 text-right tabular text-ink">
                {formatNumber(row.weight)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <label htmlFor={sizeSelectId} className="flex flex-col gap-1 text-body-sm text-muted">
          Size nodes by
          <select
            id={sizeSelectId}
            value={metric}
            onChange={(event) => setMetric(event.target.value as SizeMetric)}
            className="rounded border border-rule bg-surface px-2 py-1.5 text-body-sm text-ink"
          >
            {SIZE_METRICS.map((entry) => (
              <option key={entry.value} value={entry.value}>
                {entry.label}
              </option>
            ))}
          </select>
        </label>
        <label
          htmlFor={exploreSelectId}
          className="flex flex-col gap-1 text-body-sm text-muted"
        >
          Explore a node
          <select
            id={exploreSelectId}
            value={focusId}
            onChange={(event) => setFocusId(event.target.value)}
            className="max-w-56 rounded border border-rule bg-surface px-2 py-1.5 text-body-sm text-ink"
          >
            <option value="">All connections</option>
            {network.nodes.map((node) => (
              <option key={node.id} value={node.id}>
                {node.label}
              </option>
            ))}
          </select>
        </label>
        {isMobile ? (
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => setShowMap((v) => !v)}
          >
            {showMap ? "Hide map" : "Show map"}
          </Button>
        ) : null}
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={controlsDisabled}
          onClick={resetView}
        >
          Reset view
        </Button>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={controlsDisabled}
          onClick={savePng}
        >
          Save PNG
        </Button>
        {selected && !compact ? (
          <span className="max-w-xs text-body-sm text-ink-secondary">
            {selected.hint}
          </span>
        ) : null}
      </div>

      {isMobile && !showMap ? (
        <div className="space-y-4">
          {focusedNode ? inspector : null}
          {adjacencyTable}
        </div>
      ) : (
        <div
          className={
            compact
              ? "space-y-3"
              : "grid gap-4 md:grid-cols-[minmax(0,1fr)_15rem] md:items-start"
          }
        >
          <div>
            <div className="relative">
              <div
                id={canvasId}
                ref={containerRef}
                role="application"
                aria-label="Collaboration network map. Arrow keys pan, plus and minus zoom, Escape clears selection."
                tabIndex={0}
                onKeyDown={onCanvasKeyDown}
                style={{ height: canvasHeight }}
                className="network-canvas w-full rounded-xl border border-rule bg-surface outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
              />
              {!ready ? (
                <p className="absolute inset-0 flex items-center justify-center text-body-sm text-muted">
                  Laying out network…
                </p>
              ) : null}
            </div>
            <p className="mt-2 text-body-sm text-muted">
              Click a node to inspect it.
            </p>
          </div>
          {!compact ? inspector : focusedNode ? inspector : null}
        </div>
      )}

      {communityCount > 0 && graphVisible ? (
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

    </div>
  );
}
