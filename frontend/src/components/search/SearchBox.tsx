"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";

import { SearchIcon } from "@/components/layout/NavIcons";
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
        {/* Recessed field, per the design system's "cut into the page" inputs. */}
        <div className="flex items-center gap-2 rounded border border-rule bg-sunk px-3 py-1.5 focus-within:border-primary focus-within:ring-1 focus-within:ring-primary">
          <SearchIcon className="h-4 w-4 text-muted" />
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
            className="w-full border-none bg-transparent p-0 text-body-sm text-ink outline-none placeholder:text-muted"
          />
          <button
            type="submit"
            className="shrink-0 rounded bg-primary px-3 py-1 text-body-sm font-medium text-on-primary hover:bg-primary-hover"
          >
            Search
          </button>
        </div>
      </form>

      {open && suggestions.length > 0 ? (
        <ul
          id={listId}
          role="listbox"
          className="overlay absolute z-20 mt-1 max-h-80 w-full overflow-y-auto p-1"
        >
          {suggestions.map((suggestion, index) => (
            <li key={`${suggestion.type}-${suggestion.key}-${index}`}>
              <button
                type="button"
                role="option"
                aria-selected={false}
                onClick={() => submit(suggestion.value)}
                className="flex w-full items-start gap-2 rounded px-2 py-1.5 text-left text-body-sm hover:bg-wash"
              >
                <span className="label-caps mt-1 shrink-0 rounded border border-rule px-1 py-0.5 text-muted">
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
