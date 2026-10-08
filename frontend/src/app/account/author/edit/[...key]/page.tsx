import Link from "next/link";

import { PublicationEditForm } from "@/components/authors/PublicationEditForm";
import { ApiErrorPanel, SectionHeading } from "@/components/ui/Feedback";
import { requireCapability } from "@/services/auth/server";
import { getEditablePublication } from "@/services/authors";
import { asApiFailure } from "@/services/backend";
import { formatDate } from "@/services/format";
import { decodePublicationKeySegments, publicationHref } from "@/services/links";

export const metadata = { title: "Suggest a correction" };

interface PageProps {
  params: Promise<{ key: string[] }>;
}

export default async function SuggestCorrectionPage({ params }: PageProps) {
  const { key } = await params;
  const publicationKey = decodePublicationKeySegments(key);
  const user = await requireCapability("author.contribute", "/account/author");
  const result = await getEditablePublication(user, publicationKey);

  const back = (
    <Link href="/account/author" className="text-body-sm text-primary underline">
      Back to your author profile
    </Link>
  );

  if (!result.ok) {
    if (result.status === 403 || result.status === 404) {
      return (
        <section className="panel p-5">
          <h1 className="font-display text-h2 text-ink">You cannot edit this publication</h1>
          <p className="mt-2 max-w-prose text-body-sm text-ink-secondary">{result.message}</p>
          <div className="mt-3">{back}</div>
        </section>
      );
    }
    return <ApiErrorPanel error={asApiFailure(result)} what="this publication" />;
  }

  const { values, fields, publication_types: types, pending_edit: pending } = result.data;

  return (
    <div className="flex flex-col gap-4">
      {back}
      <section className="panel p-5">
        <SectionHeading
          level={1}
          title="Suggest a correction"
          description={
            <>
              To{" "}
              <Link href={publicationHref(publicationKey)} className="text-primary underline">
                {String(values.title ?? publicationKey)}
              </Link>
              . Authors, affiliations and the DOI are not edited here — they decide how records are
              matched and appear on other people&apos;s profiles. Flag the record if those are wrong.
            </>
          }
        />
        {pending ? (
          <p className="text-body-sm text-ink-secondary">
            A correction you sent on {formatDate(pending.created_at)} is still waiting for review.
            Withdraw it from your author profile if you want to send a different one.
          </p>
        ) : (
          <PublicationEditForm
            publicationKey={publicationKey}
            values={values}
            labels={fields}
            publicationTypes={types}
          />
        )}
      </section>
    </div>
  );
}
