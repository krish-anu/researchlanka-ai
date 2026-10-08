"use client";

import { useState } from "react";

import { INPUT_CLASS, inputBorder } from "@/components/authors/FormFields";
import { InstitutionPicker } from "@/components/authors/InstitutionPicker";
import { Button } from "@/components/ui/Button";
import type { Affiliation } from "@/types/authors";

interface Draft {
  institution: string;
  department: string;
  position_title: string;
  start_year: string;
  end_year: string;
}

function toDraft(affiliation: Affiliation): Draft {
  return {
    institution: affiliation.institution,
    department: affiliation.department,
    position_title: affiliation.position_title,
    start_year: affiliation.start_year === null ? "" : String(affiliation.start_year),
    end_year: affiliation.end_year === null ? "" : String(affiliation.end_year),
  };
}

const BLANK: Draft = { institution: "", department: "", position_title: "", start_year: "", end_year: "" };

/**
 * Where the author has worked, with years. Saved with the rest of the profile.
 *
 * It does not move any publication: each paper counts for the institution on
 * the paper. The history decides which of a paper's institutions is shown as
 * the author's on their profile, and pre-fills the institution when they add
 * a paper from a given year.
 */
export function AffiliationHistoryEditor({
  initial,
  errorIndex,
}: {
  initial: Affiliation[];
  errorIndex: number | null;
}) {
  const [rows, setRows] = useState<Draft[]>(() => (initial.length > 0 ? initial.map(toDraft) : []));

  function update(index: number, patch: Partial<Draft>) {
    setRows((current) => current.map((row, position) => (position === index ? { ...row, ...patch } : row)));
  }

  const payload = rows
    .filter((row) => row.institution.trim())
    .map((row) => ({
      institution: row.institution,
      department: row.department,
      position_title: row.position_title,
      start_year: row.start_year || null,
      end_year: row.end_year || null,
    }));

  return (
    <div className="flex flex-col gap-3">
      <input type="hidden" name="affiliations" value={JSON.stringify(payload)} />
      {rows.length === 0 ? (
        <p className="text-body-sm text-muted">
          No history yet. Add the institutions you have worked at, so papers from before a move are
          shown under the institution of the time.
        </p>
      ) : (
        <ol className="flex flex-col gap-2">
          {rows.map((row, index) => (
            <li
              key={index}
              className={`grid gap-2 rounded border p-3 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_5.5rem_5.5rem_auto] md:items-start ${
                errorIndex === index ? "border-critical" : "border-rule"
              }`}
            >
              <div className="flex flex-col gap-2">
                <InstitutionPicker
                  id={`affiliation-${index}-institution`}
                  value={row.institution}
                  invalid={errorIndex === index}
                  onChange={(label) => update(index, { institution: label })}
                />
                <input
                  aria-label={`Affiliation ${index + 1} department`}
                  placeholder="Department (optional)"
                  value={row.department}
                  onChange={(event) => update(index, { department: event.target.value })}
                  className={`${INPUT_CLASS} ${inputBorder(false)}`}
                />
              </div>
              <input
                aria-label={`Affiliation ${index + 1} position`}
                placeholder="Position"
                value={row.position_title}
                onChange={(event) => update(index, { position_title: event.target.value })}
                className={`${INPUT_CLASS} ${inputBorder(false)}`}
              />
              <input
                aria-label={`Affiliation ${index + 1} start year`}
                placeholder="From"
                inputMode="numeric"
                maxLength={4}
                value={row.start_year}
                onChange={(event) => update(index, { start_year: event.target.value.replace(/\D/g, "") })}
                className={`${INPUT_CLASS} ${inputBorder(errorIndex === index)}`}
              />
              <input
                aria-label={`Affiliation ${index + 1} end year, empty if current`}
                placeholder="Now"
                inputMode="numeric"
                maxLength={4}
                value={row.end_year}
                onChange={(event) => update(index, { end_year: event.target.value.replace(/\D/g, "") })}
                className={`${INPUT_CLASS} ${inputBorder(errorIndex === index)}`}
              />
              <Button
                type="button"
                variant="ghost"
                aria-label={`Remove affiliation ${index + 1}`}
                onClick={() => setRows((current) => current.filter((_, position) => position !== index))}
              >
                ✕
              </Button>
            </li>
          ))}
        </ol>
      )}
      <div>
        <Button type="button" variant="secondary" onClick={() => setRows((current) => [...current, BLANK])}>
          Add an affiliation
        </Button>
      </div>
    </div>
  );
}
