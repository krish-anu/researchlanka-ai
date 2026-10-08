"use client";

import { useState } from "react";

import { INPUT_CLASS, inputBorder } from "@/components/authors/FormFields";
import { Button } from "@/components/ui/Button";
import { buildQuery } from "@/services/api";
import { likelyListedName } from "@/services/authorNames";
import type { ListResponse, PublicationSummary } from "@/types/api";
import type { AuthorLookupResult, AuthorNameOption } from "@/types/authors";

export interface ClaimDraft {
  publication_key: string;
  name_as_listed: string;
  title: string;
  publication_year: number | null;
}

type SearchMode = "researcher" | "q";

/** Most publications one "add all" pulls in; more than this is almost certainly several people. */
const BULK_LIMIT = 300;

function sameName(left: string, right: string): boolean {
  return left.replace(/\s+/g, " ").trim().toLowerCase() === right.replace(/\s+/g, " ").trim().toLowerCase();
}

/**
 * Find publications in the public corpus and say which listed author you are.
 *
 * Researchers here are only names, and one paper can list the same person
 * twice in different spellings, so a claim names a specific author string —
 * picking the paper alone would not say which "Perera" you are. Searches go
 * through the same-origin `/api/v1` rewrite, the public read-only API.
 */
export function ClaimPicker({
  value,
  onChange,
  names,
  invalid = false,
  max = 100,
  excludeKeys = [],
  selectedLabel = "Your publications",
  emptyHint = "None yet. You can also leave this empty and add publications after approval.",
  mySlug = null,
  onSpellingAdded,
}: {
  value: ClaimDraft[];
  onChange: (next: ClaimDraft[]) => void;
  /** The applicant's name and variants, to preselect the likely author. */
  names: string[];
  invalid?: boolean;
  max?: number;
  /** Publications already claimed, which are shown as such rather than offered. */
  excludeKeys?: string[];
  selectedLabel?: string;
  emptyHint?: string;
  /** The signed-in author's own profile, so their already-claimed spellings are not flagged. */
  mySlug?: string | null;
  /** Told about each spelling merged with "Add all as me", to record it as a name variant. */
  onSpellingAdded?: (name: string) => void;
}) {
  const [mode, setMode] = useState<SearchMode>("researcher");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PublicationSummary[] | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chosenNames, setChosenNames] = useState<Record<string, string>>({});
  const [spellings, setSpellings] = useState<AuthorNameOption[]>([]);
  const [bulk, setBulk] = useState<{ name: string; message: string } | null>(null);
  const [bulkLoading, setBulkLoading] = useState<string | null>(null);

  const chosenKeys = new Set(value.map((claim) => claim.publication_key));
  const excluded = new Set(excludeKeys);
  const usableNames = names.map((name) => name.trim()).filter(Boolean);

  async function search() {
    const term = query.trim() || usableNames[0] || "";
    if (!term) {
      setError("Type your name, or part of a title.");
      return;
    }
    setLoading(true);
    setError(null);
    setBulk(null);
    if (mode === "researcher") {
      // The same person is often printed several ways; list the spellings so
      // all of them can be merged into one profile.
      fetch(`/api/v1/lookup/authors${buildQuery({ q: term })}`, { headers: { Accept: "application/json" } })
        .then((response) => (response.ok ? response.json() : null))
        .then((payload: { data: AuthorLookupResult } | null) => setSpellings(payload?.data.names ?? []))
        .catch(() => setSpellings([]));
    } else {
      setSpellings([]);
    }
    try {
      const response = await fetch(
        `/api/v1/publications${buildQuery({ [mode]: term, page_size: 25, sort: "year_desc" })}`,
        { headers: { Accept: "application/json" } },
      );
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = (await response.json()) as ListResponse<PublicationSummary>;
      setResults(payload.data);
      setTotal(payload.pagination.total);
      setChosenNames((current) => {
        const next = { ...current };
        for (const publication of payload.data) {
          if (!next[publication.publication_key]) {
            next[publication.publication_key] =
              likelyListedName(publication.authors, usableNames) ?? "";
          }
        }
        return next;
      });
    } catch {
      setError("Search is unavailable right now. Try again in a moment.");
    } finally {
      setLoading(false);
    }
  }

  function add(publication: PublicationSummary) {
    const listed = chosenNames[publication.publication_key];
    if (!listed || value.length >= max) return;
    onChange([
      ...value,
      {
        publication_key: publication.publication_key,
        name_as_listed: listed,
        title: publication.title ?? publication.publication_key,
        publication_year: publication.publication_year,
      },
    ]);
  }

  /** Claim every publication printed under one exact spelling. */
  async function addAllUnder(name: string) {
    setBulkLoading(name);
    setBulk(null);
    const found: ClaimDraft[] = [];
    const taken = new Set([...value.map((claim) => claim.publication_key), ...excluded]);
    try {
      for (let page = 1; found.length < BULK_LIMIT; page += 1) {
        const response = await fetch(
          `/api/v1/researchers/${encodeURIComponent(name)}/publications${buildQuery({ page, page_size: 100 })}`,
          { headers: { Accept: "application/json" } },
        );
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = (await response.json()) as ListResponse<PublicationSummary>;
        for (const publication of payload.data) {
          // The name page also matches longer names that contain this one;
          // only papers that print exactly this spelling are taken.
          const listed = publication.authors.find((author) => sameName(author, name));
          if (!listed || taken.has(publication.publication_key)) continue;
          taken.add(publication.publication_key);
          found.push({
            publication_key: publication.publication_key,
            name_as_listed: listed,
            title: publication.title ?? publication.publication_key,
            publication_year: publication.publication_year,
          });
        }
        if (page >= payload.pagination.total_pages) break;
      }
      const room = Math.max(0, max - value.length);
      const added = found.slice(0, room);
      onChange([...value, ...added]);
      onSpellingAdded?.(name);
      setBulk({
        name,
        message:
          added.length === 0
            ? `Every paper printed as "${name}" is already on your list.`
            : `Added ${added.length} ${added.length === 1 ? "paper" : "papers"} printed as "${name}".${
                found.length > added.length ? ` ${found.length - added.length} more did not fit; send these first.` : ""
              } Remove any that are not yours.`,
      });
    } catch {
      setBulk({ name, message: "Could not load those papers. Try again." });
    } finally {
      setBulkLoading(null);
    }
  }

  function remove(publicationKey: string) {
    onChange(value.filter((claim) => claim.publication_key !== publicationKey));
  }

  return (
    <div className={`flex flex-col gap-4 rounded border p-4 ${invalid ? "border-critical" : "border-rule"}`}>
      <div className="flex flex-col gap-2 sm:flex-row">
        <label className="sr-only" htmlFor="claim-search-mode">
          Search by
        </label>
        <select
          id="claim-search-mode"
          value={mode}
          onChange={(event) => setMode(event.target.value as SearchMode)}
          className={`${INPUT_CLASS} ${inputBorder(false)} sm:w-44`}
        >
          <option value="researcher">Author name</option>
          <option value="q">Title or DOI</option>
        </select>
        <label className="sr-only" htmlFor="claim-search">
          Search publications
        </label>
        <input
          id="claim-search"
          type="search"
          value={query}
          placeholder={mode === "researcher" ? usableNames[0] || "e.g. Jayatilake" : "Words from the title, or a DOI"}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              void search();
            }
          }}
          className={`${INPUT_CLASS} ${inputBorder(false)} flex-1`}
        />
        <Button type="button" variant="secondary" loading={loading} onClick={() => void search()}>
          Search
        </Button>
      </div>

      {error ? <p className="text-body-sm text-serious">{error}</p> : null}

      {spellings.length > 0 ? (
        <div className="rounded border border-rule p-3">
          <p className="label-caps text-muted">How the dataset prints this name</p>
          <p className="mt-1 text-body-sm text-muted">
            One person often appears under several spellings. Add every spelling that is you, and they
            all join your one profile.
          </p>
          <ul className="mt-2 flex flex-col gap-2">
            {spellings.map((option) => {
              const claimedByOther = option.profile && option.profile.slug !== mySlug;
              return (
                <li key={option.name} className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                  <span className="text-body-sm text-ink">
                    {option.name}
                    <span className="ml-2 text-muted">
                      {option.publication_count} {option.publication_count === 1 ? "paper" : "papers"}
                      {option.year_min ? ` · ${option.year_min}–${option.year_max}` : ""}
                    </span>
                    {claimedByOther ? (
                      <span className="ml-2 text-serious">already claimed by {option.profile?.display_name}</span>
                    ) : null}
                  </span>
                  <Button
                    type="button"
                    variant="secondary"
                    loading={bulkLoading === option.name}
                    disabled={bulkLoading !== null || value.length >= max}
                    onClick={() => void addAllUnder(option.name)}
                  >
                    Add all as me
                  </Button>
                </li>
              );
            })}
          </ul>
          {bulk ? <p role="status" className="mt-2 text-body-sm text-ink-secondary">{bulk.message}</p> : null}
        </div>
      ) : null}

      {results !== null ? (
        results.length === 0 ? (
          <p className="text-body-sm text-muted">
            Nothing matched. Try another spelling — the dataset prints names the way each source did.
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            <p className="text-body-sm text-muted">
              {total > results.length
                ? `Showing the ${results.length} newest of ${total} matches. Narrow the search to find older ones.`
                : `${results.length} ${results.length === 1 ? "match" : "matches"}.`}
            </p>
            <ul className="flex max-h-[28rem] flex-col divide-y divide-rule overflow-y-auto rounded border border-rule">
              {results.map((publication) => {
                const key = publication.publication_key;
                const already = chosenKeys.has(key) || excluded.has(key);
                const selectId = `listed-${key}`;
                return (
                  <li key={key} className="flex flex-col gap-2 p-3">
                    <p className="text-body-sm font-medium text-ink">
                      {publication.title ?? key}
                      {publication.publication_year ? (
                        <span className="ml-2 font-normal text-muted">{publication.publication_year}</span>
                      ) : null}
                    </p>
                    <p className="text-body-sm text-ink-secondary">{publication.authors.join("; ")}</p>
                    {already ? (
                      <p className="label-caps text-muted">
                        {excluded.has(key) ? "Already on your profile" : "Added"}
                      </p>
                    ) : (
                      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                        <label htmlFor={selectId} className="text-body-sm text-muted sm:shrink-0">
                          You are listed as
                        </label>
                        <select
                          id={selectId}
                          value={chosenNames[key] ?? ""}
                          onChange={(event) =>
                            setChosenNames((current) => ({ ...current, [key]: event.target.value }))
                          }
                          className={`${INPUT_CLASS} ${inputBorder(false)} sm:max-w-xs`}
                        >
                          <option value="">Choose your name</option>
                          {publication.authors.map((author, index) => (
                            <option key={`${author}-${index}`} value={author}>
                              {author}
                            </option>
                          ))}
                        </select>
                        <Button
                          type="button"
                          variant="secondary"
                          disabled={!chosenNames[key] || value.length >= max}
                          onClick={() => add(publication)}
                        >
                          Add
                        </Button>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )
      ) : null}

      <div>
        <p className="label-caps text-muted">
          {selectedLabel} ({value.length}
          {max < 1000 ? ` of up to ${max}` : ""})
        </p>
        {value.length === 0 ? (
          <p className="mt-1 text-body-sm text-muted">{emptyHint}</p>
        ) : (
          <ul className="mt-2 flex flex-col gap-2">
            {value.map((claim) => (
              <li
                key={claim.publication_key}
                className="flex items-start justify-between gap-3 rounded border border-rule px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="text-body-sm text-ink">
                    {claim.title}
                    {claim.publication_year ? (
                      <span className="ml-2 text-muted">{claim.publication_year}</span>
                    ) : null}
                  </p>
                  <p className="text-body-sm text-muted">Listed as {claim.name_as_listed}</p>
                </div>
                <Button type="button" variant="ghost" onClick={() => remove(claim.publication_key)}>
                  Remove
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
