"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { readChartTheme } from "@/components/charts/theme";
import { institutionHref, researcherHref } from "@/services/links";
import type { CollaborationNetwork as NetworkData } from "@/types/api";

interface CollaborationNetworkProps {
  network: NetworkData;
  scope: "institution" | "country" | "researcher";
  height?: number;
}

/**
 * Cytoscape.js collaboration graph.
 *
 * Loaded lazily on the client — layout is the expensive part and cannot be
 * server-rendered. Node size encodes publication count and edge width encodes
 * collaboration weight, so magnitude survives without relying on colour.
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
        const counts = network.nodes.map((node) => node.publication_count);
        const maxCount = Math.max(1, ...counts);
        const maxWeight = Math.max(1, ...network.edges.map((edge) => edge.weight));

        instance = cytoscape({
          container: element,
          elements: [
            ...network.nodes.map((node) => ({
              data: {
                id: node.id,
                label: node.label,
                size: 14 + (node.publication_count / maxCount) * 34,
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
                "background-color": theme.series[0],
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
              selector: "node:selected",
              style: {
                "background-color": theme.series[1],
                "border-color": theme.ink,
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
  }, [network, scope, router]);

  if (network.nodes.length === 0) {
    return (
      <p className="p-4 text-sm text-muted">
        No collaboration edges met the current filters and minimum weight. Try
        widening the year range or lowering the minimum weight.
      </p>
    );
  }

  if (failed) {
    return (
      <p className="p-4 text-sm text-muted">
        The network graph could not be loaded. Collaboration pairs are listed in
        the table below.
      </p>
    );
  }

  return (
    <div className="relative">
      <div
        ref={containerRef}
        style={{ height }}
        className="w-full rounded-md border border-rule bg-surface"
      />
      {!ready ? (
        <p className="absolute inset-0 flex items-center justify-center text-sm text-muted">
          Laying out network…
        </p>
      ) : null}
      <p className="mt-2 text-xs text-muted">
        Node size is publication count; edge thickness is the number of shared
        publications. Scroll to zoom, drag to pan
        {scope === "country" ? "." : ", and click a node to open its profile."}
      </p>
    </div>
  );
}
