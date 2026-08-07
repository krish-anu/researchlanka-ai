import Link from "next/link";
import { notFound } from "next/navigation";

import { PublicationCardList } from "@/components/publications/PublicationCard";
import { DataTable } from "@/components/ui/DataTable";
import { ApiErrorPanel, SectionHeading } from "@/components/ui/Feedback";
import { ProvenanceList } from "@/components/ui/Provenance";
import { QualityFlagBadge, describeFlag } from "@/components/ui/QualityFlags";
import {
  getPublication,
  getPublicationReferences,
  isNotFound,
  listPublications,
} from "@/services/api";
import { formatDate, formatNumber, truncate } from "@/services/format";
import {
  decodeKeySegments,
  institutionHref,
  publicationSearchHref,
  researcherHref,
  topicHref,
} from "@/services/links";
import type { PublicationDetail } from "@/types/api";

interface PageProps {
  params: Promise<{ key: string[] }>;
}

export async function generateMetadata({ params }: PageProps) {
  const { key } = await params;
  const result = await getPublication(decodeKeySegments(key));
  if (!result.ok) return { title: "Publication" };
  return {
    title: truncate(result.value.data.title ?? "Publication", 70),
    description: result.value.data.abstract
      ? truncate(result.value.data.abstract, 160)
      : undefined,
  };
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="border-b border-rule py-2 last:border-0">
      <dt className="text-xs uppercase tracking-wide text-muted">{label}</dt>
      <dd className="mt-0.5 text-sm text-ink-secondary">{children}</dd>
    </div>
  );
}

function LinkedList({
  items,
  href,
}: {
  items: string[];
  href: (value: string) => string;
}) {
  if (items.length === 0) return <span className="text-muted">Not recorded</span>;
  return (
    <ul className="flex flex-wrap gap-x-1 gap-y-1">
      {items.map((item, index) => (
        <li key={`${item}-${index}`}>
          <Link
            href={href(item)}
            className="rounded border border-rule px-1.5 py-0.5 text-xs hover:bg-wash"
          >
            {item}
          </Link>
        </li>
      ))}
    </ul>
  );
}

/** Count divergence is surfaced explicitly rather than silently picking a winner. */
function ImpactPanel({ publication }: { publication: PublicationDetail }) {
  const { impact } = publication;
  const diverges =
    impact.citation_count_divergence_flag || impact.reference_count_divergence_flag;

  return (
    <section className="panel p-4">
      <h2 className="text-base font-semibold text-ink">Impact</h2>
      <dl className="mt-2">
        <Field label="Citations">{formatNumber(impact.citation_count)}</Field>
        <Field label="References">{formatNumber(impact.reference_count)}</Field>
        {impact.citation_count_difference_oa_minus_crossref !== null ? (
          <Field label="Citation difference (OpenAlex − Crossref)">
            {formatNumber(impact.citation_count_difference_oa_minus_crossref)}
          </Field>
        ) : null}
        {impact.reference_count_difference_oa_minus_crossref !== null ? (
          <Field label="Reference difference (OpenAlex − Crossref)">
            {formatNumber(impact.reference_count_difference_oa_minus_crossref)}
          </Field>
        ) : null}
      </dl>
      {diverges ? (
        <p className="mt-3 flex gap-2 rounded-md border border-serious/40 bg-wash p-2 text-xs text-ink-secondary">
          <span aria-hidden className="text-serious">
            ≠
          </span>
          Sources disagree on these counts. Treat the figure above as indicative
          rather than authoritative.
        </p>
      ) : null}
    </section>
  );
}

export default async function PublicationDetailPage({ params }: PageProps) {
  const { key } = await params;
  const publicationKey = decodeKeySegments(key);

  const result = await getPublication(publicationKey);
  if (isNotFound(result)) notFound();
  if (!result.ok) {
    return <ApiErrorPanel error={result.error} what="this publication" />;
  }

  const publication = result.value.data;
  const topic =
    publication.classification.primary_topic ??
    publication.classification.topics[0];
  const field = publication.classification.primary_field;

  // The API has no recommendation endpoint — semantic search is explicitly out
  // of scope for the MVP — so "related" is an honest topic/field match, and is
  // labelled as such rather than presented as a recommender.
  const [references, related] = await Promise.all([
    getPublicationReferences(publicationKey, { page_size: 100 }),
    topic || field
      ? listPublications({
          ...(topic ? { topic } : { field }),
          page_size: 6,
          sort: "citations_desc",
        })
      : Promise.resolve(null),
  ]);

  const relatedPublications =
    related?.ok
      ? related.value.data.filter(
          (item) => item.publication_key !== publication.publication_key,
        )
      : [];

  return (
    <article className="flex flex-col gap-4">
      <nav className="text-sm text-muted">
        <Link href="/publications" className="hover:text-ink hover:underline">
          Publications
        </Link>
        <span aria-hidden> / </span>
        <span>{publication.publication_year ?? "Record"}</span>
      </nav>

      <header className="flex flex-col gap-3">
        <h1 className="text-2xl font-semibold leading-snug text-ink">
          {publication.title ?? "Untitled record"}
        </h1>

        {/* A div, not a p: LinkedList renders a <ul>, and a list inside a
            paragraph is invalid HTML that browsers re-parent — which desyncs
            the server and client trees and triggers a hydration error. */}
        <div className="text-sm text-ink-secondary">
          <LinkedList items={publication.authors} href={researcherHref} />
        </div>

        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-ink-secondary">
          {publication.publication_year ? (
            <span className="tabular">{publication.publication_year}</span>
          ) : null}
          {publication.venue.journal ? (
            <span className="italic">{publication.venue.journal}</span>
          ) : null}
          {publication.type ? <span>{publication.type}</span> : null}
          {publication.access.is_oa ? (
            <span className="inline-flex items-center gap-1 text-success-text">
              <span aria-hidden>●</span>
              Open access
              {publication.access.oa_status ? ` (${publication.access.oa_status})` : ""}
            </span>
          ) : null}
        </div>

        <div className="flex flex-wrap gap-2">
          {publication.doi ? (
            <a
              href={`https://doi.org/${publication.doi}`}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-md border border-rule px-3 py-1.5 text-sm hover:bg-wash"
            >
              View at DOI ↗
            </a>
          ) : null}
          {publication.url ? (
            <a
              href={publication.url}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-md border border-rule px-3 py-1.5 text-sm hover:bg-wash"
            >
              Source record ↗
            </a>
          ) : null}
          {publication.pdf_url ? (
            <a
              href={publication.pdf_url}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-md border border-rule px-3 py-1.5 text-sm hover:bg-wash"
            >
              PDF ↗
            </a>
          ) : null}
        </div>

        {publication.quality_flags.length > 0 ? (
          <ul className="flex flex-col gap-1.5 rounded-md border border-rule bg-wash p-3">
            {publication.quality_flags.map((flag) => (
              <li key={flag} className="flex flex-wrap items-center gap-2">
                <QualityFlagBadge flag={flag} />
                <span className="text-xs text-ink-secondary">
                  {describeFlag(flag)}
                </span>
              </li>
            ))}
          </ul>
        ) : null}
      </header>

      {publication.abstract ? (
        <section className="panel p-4">
          <h2 className="text-base font-semibold text-ink">Abstract</h2>
          <p className="mt-2 max-w-prose whitespace-pre-line text-sm leading-relaxed text-ink-secondary">
            {publication.abstract}
          </p>
        </section>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section className="panel p-4">
          <h2 className="text-base font-semibold text-ink">Venue &amp; access</h2>
          <dl className="mt-2">
            <Field label="Journal">
              {publication.venue.journal ?? <span className="text-muted">Not recorded</span>}
            </Field>
            <Field label="Publisher">
              {publication.venue.publisher ?? <span className="text-muted">Not recorded</span>}
            </Field>
            <Field label="Volume / issue / pages">
              {[
                publication.venue.volume,
                publication.venue.issue,
                publication.venue.pages.first
                  ? `pp. ${publication.venue.pages.first}${
                      publication.venue.pages.last
                        ? `–${publication.venue.pages.last}`
                        : ""
                    }`
                  : null,
              ]
                .filter(Boolean)
                .join(" · ") || <span className="text-muted">Not recorded</span>}
            </Field>
            <Field label="ISSN">
              {publication.venue.issn.length > 0
                ? publication.venue.issn.join(", ")
                : <span className="text-muted">Not recorded</span>}
            </Field>
            <Field label="Licence">
              {publication.access.license ? (
                publication.access.license_url ? (
                  <a
                    href={publication.access.license_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:underline"
                  >
                    {publication.access.license} ↗
                  </a>
                ) : (
                  publication.access.license
                )
              ) : (
                <span className="text-muted">Not recorded</span>
              )}
            </Field>
            <Field label="Published">{formatDate(publication.publication_date)}</Field>
          </dl>
        </section>

        <ImpactPanel publication={publication} />

        <section className="panel p-4">
          <h2 className="text-base font-semibold text-ink">
            Affiliations &amp; classification
          </h2>
          <dl className="mt-2">
            <Field label="Sri Lankan institutions">
              <LinkedList
                items={publication.sri_lankan_institutions}
                href={institutionHref}
              />
            </Field>
            <Field label="All institutions">
              <LinkedList items={publication.institutions} href={institutionHref} />
            </Field>
            <Field label="Countries">
              {publication.countries.length > 0
                ? publication.countries.join(", ")
                : <span className="text-muted">Not recorded</span>}
            </Field>
            <Field label="Field / subfield / domain">
              {[
                publication.classification.primary_field,
                publication.classification.primary_subfield,
                publication.classification.primary_domain,
              ]
                .filter(Boolean)
                .join(" · ") || <span className="text-muted">Not recorded</span>}
            </Field>
            <Field label="Topics">
              <LinkedList items={publication.classification.topics} href={topicHref} />
            </Field>
            <Field label="Concepts">
              {publication.classification.concepts.length > 0
                ? publication.classification.concepts.join(", ")
                : <span className="text-muted">Not recorded</span>}
            </Field>
          </dl>
        </section>

        <section className="panel p-4">
          <h2 className="text-base font-semibold text-ink">Provenance</h2>
          <dl className="mt-2">
            <Field label="Source datasets">
              <ProvenanceList sources={publication.provenance.source_dataset} />
            </Field>
            <Field label="Source record id">
              {publication.provenance.source_record_id ?? (
                <span className="text-muted">Not recorded</span>
              )}
            </Field>
            <Field label="Source datestamp">
              {formatDate(publication.provenance.source_datestamp)}
            </Field>
            <Field label="OpenAlex id">
              {publication.openalex_id ? (
                <a
                  href={publication.openalex_id}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline"
                >
                  {publication.openalex_id} ↗
                </a>
              ) : (
                <span className="text-muted">Not recorded</span>
              )}
            </Field>
            <Field label="Funding">
              {publication.funding.funder_name.length > 0
                ? publication.funding.funder_name.join(", ")
                : <span className="text-muted">Not recorded</span>}
            </Field>
          </dl>
        </section>
      </div>

      {references.ok && references.value.data.length > 0 ? (
        <section className="panel p-4">
          <SectionHeading
            title="References"
            description={`${formatNumber(references.value.pagination.total)} reference entries captured for this record.`}
          />
          <DataTable
            columns={[
              {
                key: "index",
                header: "#",
                numeric: true,
                render: (row) => row.reference_index ?? "—",
              },
              {
                key: "title",
                header: "Reference",
                render: (row) =>
                  row.reference_title ?? (
                    <span className="text-muted">Title not captured</span>
                  ),
              },
              {
                key: "author",
                header: "Author",
                render: (row) => row.reference_author ?? "—",
              },
              {
                key: "year",
                header: "Year",
                numeric: true,
                render: (row) => row.reference_year ?? "—",
              },
              {
                key: "doi",
                header: "DOI",
                render: (row) =>
                  row.reference_doi ? (
                    <a
                      href={`https://doi.org/${row.reference_doi}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary hover:underline"
                    >
                      link ↗
                    </a>
                  ) : (
                    "—"
                  ),
              },
            ]}
            rows={references.value.data}
            rowKey={(row, index) => `${row.reference_id ?? index}`}
          />
        </section>
      ) : null}

      {relatedPublications.length > 0 ? (
        <section>
          <SectionHeading
            title="Related publications"
            description={
              topic
                ? `Most-cited records sharing the topic "${topic}". Matched on shared classification, not a semantic recommender.`
                : `Most-cited records in ${field}. Matched on shared classification, not a semantic recommender.`
            }
            action={
              <Link
                href={publicationSearchHref(topic ? { topic } : { field: field ?? "" })}
                className="text-sm text-primary hover:underline"
              >
                See all →
              </Link>
            }
          />
          <PublicationCardList publications={relatedPublications.slice(0, 5)} />
        </section>
      ) : null}
    </article>
  );
}
