"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";

import type { Suggestion } from "@/types/api";

/**
 * Global search with autocomplete.
 *
 * This is the one place the browser calls the API directly. It goes through the
 * same-origin `/api/v1/*` rewrite declared in `next.config.ts`, so no CORS
 * headers are required from the Python service.
 */
export function SearchBox({ initialQuery = "" }: { initialQuery?: string }) {
  const router = useRouter();
  const listId = useId();
  const [query, setQuery] = useState(initialQuery);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 3) {
      setSuggestions([]);
      return;
    }

    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const response = await fetch(
          `/api/v1/search/suggest?q=${encodeURIComponent(trimmed)}&limit=8`,
          { signal: controller.signal },
        );
        if (!response.ok) return;
        const body = (await response.json()) as { data: Suggestion[] };
        setSuggestions(body.data ?? []);
      } catch {
        // Suggestions are a convenience; a failure must not block submitting.
      }
    }, 250);

    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [query]);

  useEffect(() => {
    function onPointerDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, []);

  function submit(value: string) {
    const trimmed = value.trim();
    setOpen(false);
    router.push(
      trimmed ? `/publications?q=${encodeURIComponent(trimmed)}` : "/publications",
    );
  }

  return (
    <div ref={containerRef} className="relative">
      <form
        role="search"
        onSubmit={(event) => {
          event.preventDefault();
          submit(query);
        }}
      >
        <label htmlFor={`${listId}-input`} className="sr-only">
          Search publications
        </label>
        <div className="flex gap-2">
          <input
            id={`${listId}-input`}
            type="search"
            value={query}
            autoComplete="off"
            placeholder="Search titles, authors, journals…"
            aria-expanded={open && suggestions.length > 0}
            aria-controls={listId}
            onChange={(event) => {
              setQuery(event.target.value);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={(event) => {
              if (event.key === "Escape") setOpen(false);
            }}
            className="w-full rounded-md border border-hairline bg-page px-3 py-1.5 text-sm text-ink placeholder:text-muted"
          />
          <button
            type="submit"
            className="shrink-0 rounded-md border border-hairline bg-wash px-3 py-1.5 text-sm font-medium text-ink hover:bg-page"
          >
            Search
          </button>
        </div>
      </form>

      {open && suggestions.length > 0 ? (
        <ul
          id={listId}
          role="listbox"
          className="panel absolute z-20 mt-1 max-h-80 w-full overflow-y-auto p-1 shadow-lg"
        >
          {suggestions.map((suggestion, index) => (
            <li key={`${suggestion.type}-${suggestion.key}-${index}`}>
              <button
                type="button"
                role="option"
                aria-selected={false}
                onClick={() => submit(suggestion.value)}
                className="flex w-full items-start gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-wash"
              >
                <span className="mt-0.5 shrink-0 rounded border border-hairline px-1 text-[10px] uppercase text-muted">
                  {suggestion.type}
                </span>
                <span className="line-clamp-2 text-ink-secondary">
                  {suggestion.value}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
