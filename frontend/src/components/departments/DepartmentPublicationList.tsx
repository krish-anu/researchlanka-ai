import Link from "next/link";

import { publicationsForDisplay } from "@/services/derive";
import { formatNumber } from "@/services/format";
import { publicationHref, researcherHref } from "@/services/links";
import type { DepartmentMatch, DepartmentPublication } from "@/types/api";

const MATCH_LABELS: Record<DepartmentMatch, string> = {
  explicit: "Named in affiliation",
  inferred: "Inferred from author history",
};

const MATCH_DESCRIPTIONS: Record<DepartmentMatch, string> = {
  explicit: "An author's affiliation on this publication names the department.",
  inferred:
    "Authors list only the university here, but name the department on their other publications.",
};

export function DepartmentMatchBadge({ match }: { match: DepartmentMatch }) {
  return (
    <span
      className={`publication-signal ${match === "explicit" ? "publication-signal-accent" : ""}`}
      title={MATCH_DESCRIPTIONS[match]}
    >
      <span aria-hidden>{match === "explicit" ? "●" : "○"}</span>
      {MATCH_LABELS[match]}
    </span>
  );
}

function normalizedName(value: string): string {
  return value.replace(/\s+/g, " ").trim().toLocaleLowerCase();
}

/** Every author, with the department's own authors emphasised and linked. */
function AuthorLine({ publication }: { publication: DepartmentPublication }) {
  const departmentNames = new Set(
    publication.department.authors.map((author) => normalizedName(author.name)),
  );
  const authors = publication.authors.length
    ? publication.authors
    : publication.department.authors.map((author) => author.name);
  const shown = authors.slice(0, 8);
  const remaining = authors.length - shown.length;

  return (
    <p className="publication-authors">
      {shown.map((author, index) => {
        const isDepartment = departmentNames.has(normalizedName(author));
        return (
          <span key={`${author}-${index}`}>
            <Link
              href={researcherHref(author)}
              className={`hover:text-primary hover:underline ${isDepartment ? "font-semibold text-ink" : ""}`}
            >
              {author}
            </Link>
            {index < shown.length - 1 ? ", " : null}
          </span>
        );
      })}
      {remaining > 0 ? <span className="text-muted"> and {remaining} others</span> : null}
    </p>
  );
}

export function DepartmentPublicationList({
  publications,
}: {
  publications: DepartmentPublication[];
}) {
  // Preprint versions of one work collapse into one entry, as on other lists.
  return (
    <ul className="publication-results">
      {publicationsForDisplay(publications).map((publication) => {
        const {
          publication_key: key,
          title,
          publication_year: year,
          journal,
          type,
          doi,
          citation_count: citations,
          is_oa: isOa,
          primary_subfield: subfield,
          department,
        } = publication;
        return (
          <li key={key}>
            <article className="publication-row">
              <div className="publication-body">
                <h3 className="publication-title">
                  <Link href={publicationHref(key)}>{title ?? "Untitled record"}</Link>
                </h3>
                <AuthorLine publication={publication} />
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
                  <DepartmentMatchBadge match={department.match} />
                  {subfield ? <span className="publication-signal">{subfield}</span> : null}
                  {department.evidence ? (
                    <span className="publication-signal max-w-full truncate" title={department.evidence}>
                      “{department.evidence}”
                    </span>
                  ) : null}
                </div>
              </div>
              {year || citations != null || isOa ? (
                <p className="publication-aside">
                  {year ? <span className="publication-year">{year}</span> : null}
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
          </li>
        );
      })}
    </ul>
  );
}
