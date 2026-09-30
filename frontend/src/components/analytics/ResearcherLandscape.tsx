"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { RankingBarChart } from "@/components/charts/RankingBarChart";
import { ChartPanel } from "@/components/ui/ChartPanel";
import { formatNumber } from "@/services/format";
import type { ResponseMeta } from "@/types/api";

/** Same bands as `researcher_landscape` in the API. */
const OUTPUT_BANDS: Record<string, { min: number; max?: number }> = {
  "1": { min: 1, max: 1 },
  "2–4": { min: 2, max: 4 },
  "5–9": { min: 5, max: 9 },
  "10–24": { min: 10, max: 24 },
  "25+": { min: 25 },
};

function bandHref(queryString: string, label: string): string | undefined {
  const band = OUTPUT_BANDS[label];
  if (!band) return undefined;
  const params = new URLSearchParams(queryString);
  params.delete("page");
  params.delete("landscape");
  params.set("min_count", String(band.min));
  if (band.max != null) params.set("max_count", String(band.max));
  else params.delete("max_count");
  const qs = params.toString();
  return qs ? `/researchers?${qs}` : "/researchers";
}

type Band = ResponseMeta["landscape"];

/**
 * Loads the researcher landscape when the insights section is opened.
 * The directory list stays on the ranking query; these counts scan the
 * full selection and are not needed until the charts are shown.
 */
export function ResearcherLandscape({ queryString }: { queryString: string }) {
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [landscape, setLandscape] = useState<Band>(undefined);

  useEffect(() => {
    const params = new URLSearchParams(queryString);
    params.delete("page");
    params.set("landscape", "1");
    const controller = new AbortController();
    setStatus("loading");
    fetch(`/api/v1/researchers?${params.toString()}`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(String(response.status));
        return response.json() as Promise<{ meta?: ResponseMeta }>;
      })
      .then((body) => {
        setLandscape(body.meta?.landscape);
        setStatus("ready");
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setStatus("error");
      });
    return () => controller.abort();
  }, [queryString]);

  if (status === "loading") {
    return <p className="text-body-sm text-ink-secondary">Loading landscape…</p>;
  }
  if (status === "error" || !landscape) {
    return (
      <p className="text-body-sm text-ink-secondary">
        The landscape could not be loaded for this selection.
      </p>
    );
  }

  return (
    <>
      {landscape.by_institution.length ? (
        <ChartPanel
          title="Researchers by institution"
          description="Distinct researchers on publications that name each institution."
        >
          <RankingBarChart
            entries={landscape.by_institution.map((entry) => ({
              label: entry.label,
              value: entry.researcher_count,
            }))}
            valueLabel="Researchers"
            ariaLabel="Researchers by institution"
          />
        </ChartPanel>
      ) : null}
      {landscape.by_output.length ? (
        <ChartPanel
          title="Researchers by publication count"
          description="Select a band to list the researchers with that many publications."
        >
          <RankingBarChart
            entries={landscape.by_output.map((entry) => ({
              label: entry.label,
              value: entry.researcher_count,
              href: bandHref(queryString, entry.label),
            }))}
            valueLabel="Researchers"
            ariaLabel="Researchers grouped by publication count"
            clickHint="Click to list these researchers"
          />
          <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
            {landscape.by_output.map((entry) => {
              const href = bandHref(queryString, entry.label);
              if (!href) return null;
              return (
                <li key={entry.label}>
                  <Link href={href} className="text-body-sm text-primary hover:underline">
                    {entry.label}
                    <span className="sr-only">
                      , {formatNumber(entry.researcher_count)} researchers
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </ChartPanel>
      ) : null}
    </>
  );
}
