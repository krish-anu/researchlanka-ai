import Link from "next/link";
import { notFound } from "next/navigation";

import { ProfileHeader } from "@/components/layout/ProfileHeader";
import { PublicationCardList } from "@/components/publications/PublicationCard";
import { ApiErrorPanel, EmptyState, SectionHeading } from "@/components/ui/Feedback";
import { Pagination } from "@/components/ui/Pagination";
import { StatTile, StatTileGrid } from "@/components/ui/StatTile";
import { getAuthorProfile, getAuthorProfilePublications, isNotFound } from "@/services/api";
import { extractPage, type SearchParams } from "@/services/filters";
import { formatCompact, formatDate, formatYearRange } from "@/services/format";
import { periodLabel } from "@/services/affiliations";
import { authorProfileHref, institutionHref, researcherHref } from "@/services/links";
import { PROFILE_LINK_LABEL, type ProfileLinks } from "@/types/authors";

interface PageProps {
  params: Promise<{ slug: string }>;
  searchParams: Promise<SearchParams>;
}

const PAGE_SIZE = 25;

export async function generateMetadata({ params }: PageProps) {
  const { slug } = await params;
  const profile = await getAuthorProfile(slug);
  if (!profile.ok) return { title: "Author profile" };
  return {
    title: profile.value.data.display_name,
    description: `Verified author profile and publications of ${profile.value.data.display_name}.`,
  };
}

/**
 * A verified author profile.
 *
 * Unlike /researchers/<name>, which groups every record sharing a printed
 * name, this lists only publications the author claimed and an administrator
 * approved — so two people called "A. Perera" stay two people.
 */
export default async function AuthorProfilePage({ params, searchParams }: PageProps) {
  const { slug } = await params;
  const page = extractPage(await searchParams);

  const profile = await getAuthorProfile(slug);
  if (isNotFound(profile)) notFound();
  if (!profile.ok) return <ApiErrorPanel error={profile.error} what="this author profile" />;
  const data = profile.value.data;
  const publications = await getAuthorProfilePublications(slug, { page, page_size: PAGE_SIZE });

  const links = (Object.keys(PROFILE_LINK_LABEL) as (keyof ProfileLinks)[]).filter((field) => data.links[field]);
  const affiliations = data.affiliations ?? [];
  const current = affiliations.find((affiliation) => affiliation.end_year === null);
  const subtitle = (
    current
      ? [current.position_title, current.department, current.institution]
      : [data.position_title, data.department, data.institution]
  )
    .filter(Boolean)
    .join(" · ");
  const periods = data.institution_breakdown?.institutions ?? [];
  const unattributed = data.institution_breakdown?.unattributed ?? 0;
  const spellings = data.listed_name_counts ?? [];

  return (
    <div className="flex flex-col gap-4">
      <ProfileHeader
        title={data.display_name}
        subtitle={subtitle}
        breadcrumbs={
          <nav className="text-body-sm text-muted">
            <Link href="/researchers" className="hover:text-ink hover:underline">
              Researchers
            </Link>
            <span aria-hidden> / </span>
            <span>{data.display_name}</span>
          </nav>
        }
        notice={
          <div className="panel border-good/40 p-3 detail-measure">
            <p className="flex gap-2 text-body-sm text-ink-secondary">
              <span aria-hidden className="text-success-text">
                ✓
              </span>
              <span>
                <strong className="font-medium text-ink">Verified author profile.</strong> Each
                publication here was claimed by the author and approved by a ResearchLanka
                administrator{data.verified_at ? `; profile verified ${formatDate(data.verified_at)}` : ""}.
                The bio and links are the author&apos;s own.
              </span>
            </p>
          </div>
        }
        metrics={
          <StatTileGrid>
            <StatTile
              label="Publications"
              value={formatCompact(data.stats.publication_count)}
              caption="claimed and approved"
            />
            <StatTile
              label="Active years"
              value={formatYearRange(data.stats.year_min, data.stats.year_max)}
              caption="first to most recent record"
            />
            <StatTile
              label="Citations"
              value={formatCompact(data.stats.citation_total)}
              caption="across these publications"
            />
          </StatTileGrid>
        }
      />

      {data.bio || links.length > 0 || data.orcid ? (
        <section className="panel p-4 detail-measure">
          {data.bio ? <p className="whitespace-pre-line text-body-md text-ink">{data.bio}</p> : null}
          <ul className="mt-3 flex flex-wrap gap-2">
            {data.orcid ? (
              <li>
                <a href={`https://orcid.org/${data.orcid}`} className="chip" rel="noopener noreferrer" target="_blank">
                  ORCID <span className="data-mono text-muted">{data.orcid}</span>
                </a>
              </li>
            ) : null}
            {links.map((field) => (
              <li key={field}>
                <a href={data.links[field] ?? "#"} className="chip" rel="noopener noreferrer nofollow" target="_blank">
                  {PROFILE_LINK_LABEL[field]}
                </a>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {affiliations.length > 0 || periods.length > 0 ? (
        <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-2">
          {affiliations.length > 0 ? (
            <section className="panel p-4">
              <SectionHeading title="Affiliations" description="As given by the author." />
              <ol className="flex flex-col divide-y divide-rule">
                {affiliations.map((affiliation, index) => (
                  <li key={`${affiliation.institution}-${index}`} className="flex flex-wrap justify-between gap-2 py-2">
                    <span className="min-w-0">
                      <Link href={institutionHref(affiliation.institution)} className="text-body-sm text-ink hover:text-primary hover:underline">
                        {affiliation.institution}
                      </Link>
                      {affiliation.position_title || affiliation.department ? (
                        <span className="block text-body-sm text-muted">
                          {[affiliation.position_title, affiliation.department].filter(Boolean).join(" · ")}
                        </span>
                      ) : null}
                    </span>
                    <span className="data-mono text-body-sm text-muted">{periodLabel(affiliation)}</span>
                  </li>
                ))}
              </ol>
            </section>
          ) : null}
          {periods.length > 0 ? (
            <section className="panel p-4">
              <SectionHeading
                title="Where this work was done"
                description="Each publication counts for the institution on the paper, so work from before a move stays with the earlier institution."
              />
              <ul className="flex flex-col divide-y divide-rule">
                {periods.map((period) => (
                  <li key={period.institution} className="flex flex-wrap items-baseline justify-between gap-2 py-2">
                    <Link href={institutionHref(period.institution)} className="text-body-sm text-ink hover:text-primary hover:underline">
                      {period.institution}
                    </Link>
                    <span className="text-body-sm text-muted">
                      <span className="data-mono text-ink">{period.publication_count}</span>{" "}
                      {period.publication_count === 1 ? "publication" : "publications"}
                      {period.year_min ? ` · ${formatYearRange(period.year_min, period.year_max)}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
              {unattributed > 0 ? (
                <p className="mt-2 text-body-sm text-muted">
                  {unattributed} {unattributed === 1 ? "publication does" : "publications do"} not list an
                  institution from the author&apos;s history.
                </p>
              ) : null}
            </section>
          ) : null}
        </div>
      ) : null}

      <section>
        <SectionHeading title="Publications" description="Newest first." />
        {!publications.ok ? (
          <ApiErrorPanel error={publications.error} what="publications" />
        ) : publications.value.data.length === 0 ? (
          <EmptyState title="No public publications yet" />
        ) : (
          <div className="flex flex-col gap-4">
            <PublicationCardList publications={publications.value.data} />
            <Pagination
              pagination={publications.value.pagination}
              basePath={authorProfileHref(slug)}
              searchParams={await searchParams}
            />
          </div>
        )}
      </section>

      {spellings.length > 0 ? (
        <p className="text-body-sm text-muted">
          Printed in the dataset as{" "}
          {spellings.map((spelling, index) => (
            <span key={spelling.name_as_listed}>
              {index > 0 ? ", " : ""}
              <Link href={researcherHref(spelling.name_as_listed)} className="text-primary hover:underline">
                {spelling.name_as_listed}
              </Link>{" "}
              ({spelling.publication_count})
            </span>
          ))}
          . This profile brings those spellings together; the name pages group every record with one
          spelling, which can include other people.
        </p>
      ) : null}
    </div>
  );
}
