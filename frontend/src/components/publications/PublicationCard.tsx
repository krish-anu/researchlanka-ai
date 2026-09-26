import Link from "next/link";
import { ViewSwitcher } from "@/components/ui/ViewSwitcher";
import { DataTable } from "@/components/ui/DataTable";

import { AIRelevanceStatus } from "@/components/publications/AIRelevanceStatus";
import { QualityFlagList } from "@/components/ui/QualityFlags";
import { ProvenanceList, ProvenanceStripe } from "@/components/ui/Provenance";
import { formatDate } from "@/services/format";
import { publicationHref, researcherHref } from "@/services/links";
import type { PublicationSummary } from "@/types/api";

/** Author names link to profiles; the first few are individually clickable. */
function AuthorLine({ authors }: { authors: string[] }) {
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
          {index < linked.length - 1 ? ", " : null}
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
    oa_status: oaStatus,
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

      <div className="p-5">
        <h3 className="font-display text-h3 leading-snug text-ink">
          <Link href={publicationHref(key)} className="hover:text-primary hover:underline">
            {title ?? "Untitled record"}
          </Link>
        </h3>

        <p className="mt-2 text-body-sm text-ink-secondary">
          <AuthorLine authors={authors} />
        </p>

        <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-body-sm text-ink-secondary">
          {displayYear ? (
            <span className="tabular" title={date ? `Published ${formatDate(date)}` : undefined}>
              Published {displayYear}
            </span>
          ) : null}
          {journal ? (
            <>
              <span aria-hidden className="text-muted">
                ·
              </span>
              <span className="italic">{journal}</span>
            </>
          ) : null}
          {type ? (
            <>
              <span aria-hidden className="text-muted">
                ·
              </span>
              <span>{type}</span>
            </>
          ) : null}
        </p>

        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-body-sm">
          <AIRelevanceStatus trace={publication.trace} compact />

          {isOa ? (
            <span className="inline-flex items-center gap-1 text-success-text">
              <span aria-hidden>●</span>
              Open access{oaStatus ? ` (${oaStatus})` : ""}
            </span>
          ) : null}

          {field ? <span className="text-ink-secondary">{field}</span> : null}
        </div>

        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <QualityFlagList flags={flags} max={3} />
          <ProvenanceList sources={sources} />
        </div>

        {/* Machine identifier sits last, in the mono data face. */}
        {doi ? (
          <div className="mt-3 border-t border-rule pt-3">
            <a
              href={`https://doi.org/${doi}`}
              target="_blank"
              rel="noopener noreferrer"
              className="data-mono text-muted hover:text-primary hover:underline"
            >
              doi:{doi}
            </a>
          </div>
        ) : null}
      </div>
    </article>
  );
}

export function PublicationCardList({ publications, initialView = "cards" }: { publications: PublicationSummary[]; initialView?: "cards" | "table" }) {
  return <ViewSwitcher label="Publication view" initialView={initialView} cards={
    <ul className="flex flex-col gap-4">{publications.map(publication => <li key={publication.publication_key}><PublicationCard publication={publication} /></li>)}</ul>
  } table={<section className="panel p-3"><DataTable rows={publications} rowKey={p => p.publication_key} columns={[
    { key: "title", header: "Publication", render: p => <div><Link href={publicationHref(p.publication_key)} className="font-medium text-ink hover:text-primary">{p.title ?? "Untitled record"}</Link><p className="mt-2 text-xs text-muted"><AuthorLine authors={p.authors} /></p><div className="mt-2 flex flex-wrap items-center gap-2"><AIRelevanceStatus trace={p.trace} compact /><QualityFlagList flags={p.quality_flags} max={3} /></div></div> },
    { key: "field", header: "Field", render: p => p.primary_field ?? "Unclassified" },
    { key: "year", header: "Year", numeric: true, render: p => p.publication_year ?? yearFromDate(p.publication_date) ?? "—" },
    { key: "access", header: "Access", render: p => p.is_oa ? <span className="rounded bg-primary-muted px-2 py-1 text-xs text-primary">Open access</span> : "Not marked open" },
    { key: "source", header: "Sources", render: p => <ProvenanceList sources={p.source_dataset} /> },
  ]} /><p className="px-3 pb-2 text-xs text-muted">Open a publication for its full metadata, references, related research, and record actions. Switch to cards to see journal and DOI details inline.</p></section>} />;
}
