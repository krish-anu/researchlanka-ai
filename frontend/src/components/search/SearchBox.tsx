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
 *
 * The popup follows the ARIA combobox pattern: the input keeps focus and owns
 * the keyboard, and the active option is pointed at with `aria-activedescendant`
 * rather than being focused. Options are therefore plain list items, not
 * buttons — a focusable control inside a listbox is not a valid option, and it
 * is what previously made the suggestions unreachable without a mouse.
 */
export function SearchBox({ initialQuery = "" }: { initialQuery?: string }) {
  const router = useRouter();
  const listId = useId();
  const [query, setQuery] = useState(initialQuery);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 3) {
      setSuggestions([]);
      setActive(-1);
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
        setActive(-1);
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

  const expanded = open && suggestions.length > 0;

  function submit(value: string) {
    const trimmed = value.trim();
    setOpen(false);
    setActive(-1);
    router.push(
      trimmed ? `/publications?q=${encodeURIComponent(trimmed)}` : "/publications",
    );
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      setOpen(false);
      setActive(-1);
      return;
    }

    if (!expanded) return;

    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      // Wraps through a virtual "no selection" slot, so arrowing back past the
      // top returns you to what you actually typed.
      setActive((current) => {
        const next = current + step;
        if (next < -1) return suggestions.length - 1;
        if (next >= suggestions.length) return -1;
        return next;
      });
      return;
    }

    if (event.key === "Enter" && active >= 0) {
      event.preventDefault();
      submit(suggestions[active].value);
    }
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
            role="combobox"
            value={query}
            autoComplete="off"
            placeholder="Search titles, authors, journals…"
            aria-expanded={expanded}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={
              active >= 0 ? `${listId}-option-${active}` : undefined
            }
            onChange={(event) => {
              setQuery(event.target.value);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={onKeyDown}
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

      {expanded ? (
        <ul
          id={listId}
          role="listbox"
          aria-label="Search suggestions"
          className="panel absolute z-20 mt-1 max-h-80 w-full overflow-y-auto p-1 shadow-[0_2px_8px_rgba(13,30,37,0.1)]"
        >
          {suggestions.map((suggestion, index) => (
            <li
              key={`${suggestion.type}-${suggestion.key}-${index}`}
              id={`${listId}-option-${index}`}
              role="option"
              aria-selected={index === active}
              // `mousedown` fires before the input's blur, so the click is not
              // eaten by the dismiss handler.
              onMouseDown={(event) => {
                event.preventDefault();
                submit(suggestion.value);
              }}
              onMouseEnter={() => setActive(index)}
              className={`flex cursor-pointer items-start gap-2 rounded px-2 py-1.5 text-left text-body-sm ${
                index === active ? "bg-wash" : ""
              }`}
            >
              <span className="label-caps mt-1 shrink-0 rounded border border-rule px-1 py-0.5 text-muted">
                {suggestion.type}
              </span>
              <span className="line-clamp-2 text-ink-secondary">
                {suggestion.value}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
