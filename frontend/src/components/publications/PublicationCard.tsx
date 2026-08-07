import Link from "next/link";

import { QualityFlagList } from "@/components/ui/QualityFlags";
import { ProvenanceList } from "@/components/ui/Provenance";
import { formatAuthorList, formatNumber } from "@/services/format";
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
            className="hover:text-ink hover:underline"
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
    journal,
    type,
    citation_count: citations,
    is_oa: isOa,
    oa_status: oaStatus,
    primary_field: field,
    source_dataset: sources,
    quality_flags: flags,
    doi,
  } = publication;

  return (
    <article className="panel p-4">
      <h3 className="text-base font-medium leading-snug">
        <Link href={publicationHref(key)} className="hover:underline">
          {title ?? "Untitled record"}
        </Link>
      </h3>

      <p className="mt-1 text-sm text-ink-secondary">
        <AuthorLine authors={authors} />
      </p>

      <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-secondary">
        {year ? <span className="tabular">{year}</span> : null}
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

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
        <span className="text-ink-secondary">
          <span className="tabular font-medium text-ink">
            {formatNumber(citations)}
          </span>{" "}
          citations
        </span>

        {isOa ? (
          <span className="inline-flex items-center gap-1 text-success-text">
            <span aria-hidden>●</span>
            Open access{oaStatus ? ` (${oaStatus})` : ""}
          </span>
        ) : null}

        {field ? (
          <span className="text-ink-secondary">{field}</span>
        ) : null}

        {doi ? (
          <a
            href={`https://doi.org/${doi}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-series-1 hover:underline"
          >
            DOI
          </a>
        ) : null}
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <QualityFlagList flags={flags} max={3} />
        <ProvenanceList sources={sources} />
      </div>
    </article>
  );
}

export function PublicationCardList({
  publications,
}: {
  publications: PublicationSummary[];
}) {
  return (
    <ul className="flex flex-col gap-3">
      {publications.map((publication) => (
        <li key={publication.publication_key}>
          <PublicationCard publication={publication} />
        </li>
      ))}
    </ul>
  );
}
