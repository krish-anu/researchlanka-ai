"use client";

import { useEffect, useState } from "react";

import { buildQuery } from "@/services/api";

/**
 * Debounced GET against one of the public `/api/v1/lookup/*` endpoints.
 *
 * Results are only kept for the term that produced them, so a slow response
 * for an earlier keystroke can never overwrite the answer to a later one.
 */
export function useLookup<T>(path: string, term: string, { minLength = 2, delay = 250 } = {}) {
  const [state, setState] = useState<{ term: string; data: T | null; error: boolean }>({
    term: "",
    data: null,
    error: false,
  });
  const trimmed = term.trim();
  const active = trimmed.length >= minLength;

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch(`/api/v1/lookup/${path}${buildQuery({ q: trimmed })}`, {
          headers: { Accept: "application/json" },
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = (await response.json()) as { data: T };
        setState({ term: trimmed, data: payload.data, error: false });
      } catch (cause) {
        if ((cause as Error).name !== "AbortError") setState({ term: trimmed, data: null, error: true });
      }
    }, delay);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [path, trimmed, active, delay]);

  const current = active && state.term === trimmed;
  return {
    data: current ? state.data : null,
    error: current && state.error,
    loading: active && !current,
  };
}
