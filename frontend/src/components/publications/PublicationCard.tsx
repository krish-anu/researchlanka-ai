import Link from "next/link";
import type { ReactNode } from "react";
import { ViewSwitcher } from "@/components/ui/ViewSwitcher";
import { DataTable } from "@/components/ui/DataTable";


import { AIRelevanceStatus } from "@/components/publications/AIRelevanceStatus";


import { describeFlag, QualityFlagList } from "@/components/ui/QualityFlags";
import { ProvenanceList, ProvenanceStripe, SourceDot, sourceLabel } from "@/components/ui/Provenance";
import { publicationsForDisplay } from "@/services/derive";
import { formatDate, formatNumber } from "@/services/format";

import { publicationHref, researcherHref } from "@/services/links";
import type { PublicationSummary } from "@/types/api";

/** Author names link to profiles; the first few are individually clickable. */
function AuthorLine({
  authors,
  separator = ", ",
}: {
  authors: string[];
  separator?: string;
}) {
  if (authors.length === 0) {
    return <span className="text-muted">Authors not recorded</span>;
  }

  const linked = authors.slice(0, 4);
  const remaining = authors.length - linked.length;

  return (
    <span>
      {linked.map((author, index) => (
        <span key={`${author}-${index}`}>
          <Link
            href={researcherHref(author)}
            className="hover:text-primary hover:underline"
          >
            {author}
          </Link>
          {index < linked.length - 1 ? separator : null}
        </span>
      ))}
      {remaining > 0 ? (
        <span className="text-muted"> and {remaining} others</span>
      ) : null}
    </span>
  );
}

function yearFromDate(value: string | null): number | null {
  if (!value) return null;
  const match = /^(\d{4})/.exec(value);
  return match ? Number(match[1]) : null;
}

export function PublicationCard({
  publication,
}: {
  publication: PublicationSummary;
}) {
  const {
    publication_key: key,
    title,
    authors,
    publication_year: year,
    publication_date: date,
    journal,
    type,
    is_oa: isOa,
    primary_field: field,
    source_dataset: sources,
    quality_flags: flags,
    doi,
  } = publication;
  const displayYear = year ?? yearFromDate(date);

  return (
    <article className="panel publication-card overflow-hidden">
      {/* Signature stripe: which datasets this record was seen in. */}
      <ProvenanceStripe sources={sources} />

      <div className="px-4 py-3">
        <h3 className="font-display text-h3 leading-snug text-ink">
          <Link href={publicationHref(key)} className="hover:text-primary hover:underline">
            {title ?? "Untitled record"}
          </Link>
        </h3>

        <p className="mt-1 text-body-sm text-ink-secondary">
          <AuthorLine authors={authors} />
        </p>

        <p className="mt-2 flex flex-wrap items-baseline gap-x-1.5 gap-y-1 text-body-sm text-ink-secondary">
          {displayYear ? (
            <span className="tabular text-ink" title={date ? `Published ${formatDate(date)}` : undefined}>
              {displayYear}
            </span>
          ) : null}
          {journal ? (
            <>
              {displayYear ? <span aria-hidden className="text-muted">·</span> : null}
              <span className="italic">{journal}</span>
            </>
          ) : null}
          {type ? (
            <>
              {displayYear || journal ? <span aria-hidden className="text-muted">·</span> : null}
              <span>{type}</span>
            </>
          ) : null}
        </p>

        <div className="mt-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 text-body-sm">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <span className="text-ink-secondary">{field ?? "Unclassified"}</span>
            <AIRelevanceStatus trace={publication.trace} compact />
          </div>

          {isOa ? (
            <span className="inline-flex items-center gap-1.5 text-ink-secondary">
              <span aria-hidden className="text-muted">●</span>
              Open access
            </span>
          ) : null}
        </div>

        <div className="mt-2 flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
          <QualityFlagList flags={flags} max={2} compact />
          <ProvenanceList sources={sources} compact />
        </div>

        {doi ? (
          <div className="mt-2 border-t border-rule pt-2">
            <a
              href={`https://doi.org/${doi}`}
              target="_blank"
              rel="noopener noreferrer"
              className="data-mono text-muted hover:text-primary hover:underline"
            >
              DOI: {doi}
            </a>
          </div>
        ) : null}
      </div>
    </article>
  );
}

function listedInstitutions(names: string[]): string[] {
  return names.map((name) => name.trim()).filter(Boolean);
}

const DISAGREEMENT_LABELS: Record<string, string> = {
  citation_count_divergence: "Citation counts disagree",
  reference_count_divergence: "Reference counts disagree",
};

/** Bibliographic row: citation spine, title, venue line, then lineage signals. */
export function PublicationRow({
  publication,
}: {
  publication: PublicationSummary;
}) {
  const {
    publication_key: key,
    title,
    authors,
    institutions,
    publication_year: year,
    publication_date: date,
    journal,
    type,
    is_oa: isOa,
    primary_field: field,
    primary_subfield: subfield,
    source_dataset: sources,
    quality_flags: flags,
    doi,
    citation_count: citations,
  } = publication;
  const displayYear = year ?? yearFromDate(date);
  const places = listedInstitutions(institutions).slice(0, 2);
  const extraPlaces = listedInstitutions(institutions).length - places.length;
  const areas = [field, subfield].filter((value, index, all): value is string =>
    Boolean(value) && all.indexOf(value) === index,
  );
  const disagreements = flags.filter((flag) => flag in DISAGREEMENT_LABELS);
  const quietFlags = flags.filter((flag) => !(flag in DISAGREEMENT_LABELS));

  return (
    <article className="publication-row">
      <div className="publication-body">
        <h3 className="publication-title">
          <Link href={publicationHref(key)}>
            {title ?? "Untitled record"}
          </Link>
        </h3>
        <p className="publication-authors">
          <AuthorLine authors={authors} separator=", " />
        </p>
        {places.length ? (
          <p className="publication-institutions">
            {places.join(" · ")}
            {extraPlaces > 0 ? ` +${extraPlaces} more` : ""}
          </p>
        ) : null}
        {journal || doi || type ? (
          <p className="publication-venue">
            {journal ? <span className="publication-journal">{journal}</span> : null}
            {doi ? (
              <>
                {journal ? <span aria-hidden className="publication-dot"> · </span> : null}
                <a
                  href={`https://doi.org/${doi}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="publication-doi"
                >
                  {doi}
                </a>
              </>
            ) : null}
            {type ? (
              <>
                {journal || doi ? <span aria-hidden className="publication-dot"> · </span> : null}
                <span>{type}</span>
              </>
            ) : null}
          </p>
        ) : null}
        <div className="publication-signals">
          {areas.length ? (
            <span className="publication-signal">{areas.join(" · ")}</span>
          ) : null}
          {sources.map((source) => (
            <span key={source} className="publication-signal">
              <SourceDot source={source} />
              {sourceLabel(source)}
            </span>
          ))}
          <QualityFlagList flags={quietFlags} max={2} compact />
          {disagreements.map((flag) => (
            <span
              key={flag}
              className="publication-signal publication-signal-accent"
              title={describeFlag(flag)}
            >
              {DISAGREEMENT_LABELS[flag]}
            </span>
          ))}
        </div>
      </div>
      {displayYear || citations != null || isOa ? (
        <p className="publication-aside">
          {displayYear ? (
            <span className="publication-year" title={date ? `Published ${formatDate(date)}` : undefined}>
              {displayYear}
            </span>
          ) : null}
          {citations != null ? (
            <span className="publication-cite-count">
              {formatNumber(citations)}
              <span className="publication-cite-label">
                {citations === 1 ? " cite" : " cites"}
              </span>
            </span>
          ) : null}
          {isOa ? <span className="publication-oa">Open access</span> : null}
        </p>
      ) : null}
    </article>
  );
}

export function PublicationCardList({
  publications,
  initialView = "cards",
  toolbar,
  controls,
  layout = "card",
}: {
  publications: PublicationSummary[];
  initialView?: "cards" | "table";
  toolbar?: ReactNode;
  controls?: ReactNode;
  /** Directory rows on the publications page. Other pages keep the card. */
  layout?: "card" | "row";
}) {
  const displayPublications = publicationsForDisplay(publications);

  if (displayPublications.length === 0) {
    return <p className="panel p-4 text-body-sm text-muted">No displayable publication records.</p>;
  }

  return <ViewSwitcher label="Publication view" initialView={initialView} chrome={toolbar ? "inline" : "sticky"} leading={toolbar} extra={controls} cardsLabel={layout === "row" ? "List" : "Cards"} persistKey="publications" cards={
    layout === "row" ? (
      <div>
        <ul className="publication-results">
          {displayPublications.map((publication) => (
            <li key={publication.publication_key}>
              <PublicationRow publication={publication} />
            </li>
          ))}
        </ul>
      </div>
    ) : (
      <ul className="flex flex-col gap-3">{displayPublications.map(publication => <li key={publication.publication_key}><PublicationCard publication={publication} /></li>)}</ul>
    )
  } table={<section className="panel p-3"><DataTable rows={displayPublications} rowKey={p => p.publication_key} columns={[
    {
      key: "title",
      header: "Publication",
      render: (p) => (
        <div>
          <Link
            href={publicationHref(p.publication_key)}
            className="font-medium text-ink hover:text-primary"
          >
            {p.title ?? "Untitled record"}
          </Link>

          <p className="mt-2 text-body-sm text-muted">
            <AuthorLine authors={p.authors} />
          </p>

          <div className="mt-2 flex flex-wrap items-center gap-2">
            <AIRelevanceStatus trace={p.trace} compact />
            <QualityFlagList flags={p.quality_flags} max={3} />
          </div>
        </div>
      ),
    },
    { key: "title", header: "Publication", render: p => <div><Link href={publicationHref(p.publication_key)} className="font-medium text-ink hover:text-primary">{p.title ?? "Untitled record"}</Link><p className="mt-2 text-body-sm text-muted"><AuthorLine authors={p.authors} /></p><div className="mt-2"><QualityFlagList flags={p.quality_flags} max={3} /></div></div> },
    { key: "field", header: "Field", render: p => p.primary_field ?? "Unclassified" },
    { key: "year", header: "Year", numeric: true, render: p => p.publication_year ?? yearFromDate(p.publication_date) ?? "—" },
    { key: "access", header: "Access", render: p => p.is_oa ? "Open access" : "Not marked open" },
    { key: "source", header: "Sources", render: p => <ProvenanceList sources={p.source_dataset} /> },
  ]} /><p className="px-3 pb-2 text-body-sm text-muted">{layout === "row" ? "The list shows authors, venue, DOI, and citations beside each title." : "Open a publication for its full metadata, references, related research, and record actions. Switch to cards to see journal and DOI details inline."}</p></section>} />;
}
