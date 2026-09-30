"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import { SearchIcon } from "@/components/layout/NavIcons";
import { Button } from "@/components/ui/Button";
import { institutionHref, publicationHref, researcherHref } from "@/services/links";
import { titleCase } from "@/services/format";
import type { Suggestion } from "@/types/api";

type SuggestionType = "publication" | "journal" | "researcher" | "institution";

const TYPE_GROUPS: { type: SuggestionType; label: string }[] = [
  { type: "publication", label: "Publications" },
  { type: "journal", label: "Journals" },
  { type: "researcher", label: "Researchers" },
  { type: "institution", label: "Institutions" },
];

function groupSuggestions(items: Suggestion[]) {
  const byType = new Map<string, Suggestion[]>();
  for (const item of items) {
    const list = byType.get(item.type) ?? [];
    list.push(item);
    byType.set(item.type, list);
  }

  const groups: { type: string; label: string; items: Suggestion[] }[] = [];
  for (const group of TYPE_GROUPS) {
    const grouped = byType.get(group.type);
    if (grouped?.length) {
      groups.push({ ...group, items: grouped });
      byType.delete(group.type);
    }
  }
  for (const [type, grouped] of byType) {
    if (grouped.length) {
      groups.push({ type, label: titleCase(type), items: grouped });
    }
  }
  return groups;
}

function emptyStateLabel(targetPath: SearchBoxProps["targetPath"]): string {
  if (targetPath === "/researchers") return "No matches — search all researchers";
  if (targetPath === "/institutions") return "No matches — search all institutions";
  return "No matches — search all publications";
}

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
interface SearchBoxProps {
  initialQuery?: string;
  label?: string;
  placeholder?: string;
  targetPath?: "/publications" | "/researchers" | "/institutions";
  suggestionTypes?: SuggestionType[];
  /** Sighted label above the field. Defaults to screen-reader only. */
  showLabel?: boolean;
  /** Persistent hint under the field, tied to the input with aria-describedby. */
  hint?: string;
}

export function SearchBox({
  initialQuery = "",
  label = "Search publications, researchers, and institutions",
  placeholder = "Search publications, researchers, institutions...",
  targetPath = "/publications",
  suggestionTypes,
  showLabel = false,
  hint,
}: SearchBoxProps) {
  const router = useRouter();
  const pageParams = useSearchParams();
  const selectionScoped = [...(pageParams?.keys() ?? [])].some((key) => key !== "q");
  const listId = useId();
  const [query, setQuery] = useState(initialQuery);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [fetchState, setFetchState] = useState<"idle" | "loading" | "ready" | "error">(
    "idle",
  );
  const [errorToast, setErrorToast] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const effectiveSuggestionTypes =
    suggestionTypes ??
    (targetPath === "/institutions"
      ? ["institution"]
      : targetPath === "/researchers"
        ? ["researcher"]
        : undefined);
  const suggestionTypeKey = effectiveSuggestionTypes?.join(",");
  const trimmed = query.trim();
  const groups = useMemo(() => groupSuggestions(suggestions), [suggestions]);
  const showEmpty =
    open && trimmed.length >= 2 && fetchState === "ready" && suggestions.length === 0;
  const showLoading =
    open && trimmed.length >= 2 && fetchState === "loading" && suggestions.length === 0;
  const showList = open && suggestions.length > 0;
  const expanded = showList || showEmpty || showLoading;
  const completion = suggestions.find((item) =>
    item.value.toLowerCase().startsWith(trimmed.toLowerCase()),
  );
  const optionCount = showEmpty ? 1 : suggestions.length;

  useEffect(() => {
    if (trimmed.length < 2) {
      setSuggestions([]);
      setFetchState("idle");
      setActive(-1);
      return;
    }

    const controller = new AbortController();
    setFetchState("loading");
    const timer = setTimeout(async () => {
      try {
        const search = new URLSearchParams({ q: trimmed, limit: "8" });
        for (const type of effectiveSuggestionTypes ?? []) {
          search.append("type", type);
        }
        const response = await fetch(
          `/api/v1/search/suggest?${search.toString()}`,
          { signal: controller.signal },
        );
        if (!response.ok) {
          setSuggestions([]);
          setFetchState("error");
          setErrorToast("Couldn’t load suggestions");
          setActive(-1);
          return;
        }
        const body = (await response.json()) as { data: Suggestion[] };
        setSuggestions(body.data ?? []);
        setFetchState("ready");
        setActive(-1);
      } catch {
        if (controller.signal.aborted) return;
        setSuggestions([]);
        setFetchState("error");
        setErrorToast("Couldn’t load suggestions");
        setActive(-1);
      }
    }, 250);

    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [query, suggestionTypeKey]);

  useEffect(() => {
    if (!errorToast) return;
    const timer = setTimeout(() => setErrorToast(null), 3500);
    return () => clearTimeout(timer);
  }, [errorToast]);

  useEffect(() => {
    function onPointerDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, []);

  function searchHref(value: string) {
    const next = value.trim();
    return next ? `${targetPath}?q=${encodeURIComponent(next)}` : targetPath;
  }

  function suggestionHref(suggestion: Suggestion) {
    if (suggestion.type === "publication") return publicationHref(suggestion.key);
    if (suggestion.type === "researcher") return researcherHref(suggestion.value);
    if (suggestion.type === "institution") return institutionHref(suggestion.value);
    return searchHref(suggestion.value);
  }

  function submit(value: string) {
    setOpen(false);
    setActive(-1);
    router.push(searchHref(value));
  }

  function selectSuggestion(suggestion: Suggestion) {
    setQuery(suggestion.value);
    setOpen(false);
    setActive(-1);
    if (suggestion.type === "institution" && targetPath === "/institutions") {
      router.push(searchHref(suggestion.value));
      return;
    }
    router.push(suggestionHref(suggestion));
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (
      event.key === "Tab" &&
      completion &&
      completion.value.toLowerCase() !== trimmed.toLowerCase()
    ) {
      event.preventDefault();
      setQuery(completion.value);
      return;
    }

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
        if (next < -1) return optionCount - 1;
        if (next >= optionCount) return -1;
        return next;
      });
      return;
    }

    if (event.key === "Enter" && active >= 0) {
      event.preventDefault();
      if (showEmpty) {
        submit(query);
        return;
      }
      selectSuggestion(suggestions[active]);
    }
  }

  let optionIndex = 0;

  return (
    <div ref={containerRef} className="relative max-w-[40rem]">
      <form
        role="search"
        onSubmit={(event) => {
          event.preventDefault();
          submit(query);
        }}
      >
        <label
          htmlFor={`${listId}-input`}
          className={
            showLabel
              ? "mb-2 block text-body-sm font-medium text-ink"
              : "sr-only"
          }
        >
          {label}
        </label>
        {/* Recessed field, per the design system's "cut into the page" inputs. */}
        <div className="search-shell">
          <SearchIcon className="h-4 w-4 shrink-0 text-muted" />
          <input
            id={`${listId}-input`}
            type="text"
            role="combobox"
            value={query}
            autoComplete="off"
            placeholder={placeholder}
            aria-expanded={expanded}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={
              active >= 0 ? `${listId}-option-${active}` : undefined
            }
            aria-describedby={hint ? `${listId}-hint` : undefined}
            onChange={(event) => {
              setQuery(event.target.value);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={onKeyDown}
            className="search-shell-input"
          />
          {fetchState === "loading" ? (
            <span className="search-spinner" role="status" aria-label="Loading suggestions" />
          ) : null}
          <Button type="submit" variant="primary" size="sm" className="search-shell-submit">
            Search
          </Button>
        </div>
        {completion && completion.value.toLowerCase() !== trimmed.toLowerCase() ? (
          <p className="mt-1 text-label text-muted">
            Tab fills <span className="text-ink-secondary">{completion.value}</span>
          </p>
        ) : null}
        {hint ? (
          <p id={`${listId}-hint`} className="mt-2 text-body-sm text-muted">
            {hint}
          </p>
        ) : null}
      </form>

      {errorToast ? (
        <p
          role="status"
          className="absolute right-0 z-30 mt-1 max-w-[min(100%,18rem)] rounded border border-rule bg-surface px-2.5 py-1.5 text-body-sm text-ink-secondary shadow-[0_2px_8px_rgba(13,30,37,0.1)]"
        >
          {errorToast}
        </p>
      ) : null}

      {expanded ? (
        <ul
          id={listId}
          role="listbox"
          aria-label="Search suggestions"
          className="panel absolute z-20 mt-1 max-h-80 w-full overflow-y-auto p-1 shadow-[0_2px_8px_rgba(13,30,37,0.1)]"
        >
          {showLoading ? (
            <li className="search-suggest-skeleton" aria-hidden="true">
              <span style={{ width: "72%" }} />
              <span style={{ width: "54%" }} />
              <span style={{ width: "63%" }} />
            </li>
          ) : showEmpty ? (
            <li
              id={`${listId}-option-0`}
              role="option"
              aria-selected={active === 0}
              onMouseDown={(event) => {
                event.preventDefault();
                submit(query);
              }}
              onMouseEnter={() => setActive(0)}
              className={`cursor-pointer rounded px-2 py-2 text-left text-body-sm ${
                active === 0 ? "bg-wash" : ""
              }`}
            >
              <span className="text-ink-secondary">
                {selectionScoped
                  ? emptyStateLabel(targetPath).replace(
                      "No matches — ",
                      "No matches in this selection — ",
                    )
                  : emptyStateLabel(targetPath)}
              </span>
            </li>
          ) : (
            groups.flatMap((group) => {
              const heading = (
                <li
                  key={`heading-${group.type}`}
                  role="presentation"
                  className="label-caps px-2 pb-1 pt-2 text-muted first:pt-1"
                >
                  {group.label}
                </li>
              );
              const options = group.items.map((suggestion) => {
                const index = optionIndex;
                optionIndex += 1;
                return (
                  <li
                    key={`${suggestion.type}-${suggestion.key}-${index}`}
                    id={`${listId}-option-${index}`}
                    role="option"
                    aria-selected={index === active}
                    // `mousedown` fires before the input's blur, so the click is not
                    // eaten by the dismiss handler.
                    onMouseDown={(event) => {
                      event.preventDefault();
                      selectSuggestion(suggestion);
                    }}
                    onMouseEnter={() => setActive(index)}
                    className={`cursor-pointer rounded px-2 py-1.5 text-left text-body-sm text-ink-secondary ${
                      index === active ? "bg-wash" : ""
                    }`}
                  >
                    <span className="line-clamp-2">{suggestion.value}</span>
                  </li>
                );
              });
              return [heading, ...options];
            })
          )}
        </ul>
      ) : null}
    </div>
  );
}
