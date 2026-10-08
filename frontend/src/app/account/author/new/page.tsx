import Link from "next/link";
import { redirect } from "next/navigation";

import { NewPublicationForm } from "@/components/authors/NewPublicationForm";
import { ApiErrorPanel, SectionHeading } from "@/components/ui/Feedback";
import { getCategoryOptions } from "@/services/api";
import { requireCapability } from "@/services/auth/server";
import { getAuthorWorkspace } from "@/services/authors";
import { asApiFailure } from "@/services/backend";
import type { AuthorWorkspace } from "@/types/authors";

export const metadata = { title: "Add a publication" };

/** The submitter's spellings, the one the dataset prints most often first. */
function submitterNames(workspace: AuthorWorkspace): string[] {
  const counts = new Map<string, number>();
  for (const claim of workspace.claims) {
    if (claim.status !== "approved") continue;
    counts.set(claim.name_as_listed, (counts.get(claim.name_as_listed) ?? 0) + 1);
  }
  const printed = [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([name]) => name);
  const profile = workspace.profile;
  const all = [...printed, profile?.display_name ?? "", ...(profile?.name_variants ?? [])];
  const seen = new Set<string>();
  return all.filter((name) => {
    const key = name.trim().toLowerCase();
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export default async function AddPublicationPage() {
  const user = await requireCapability("author.contribute", "/account/author/new");
  const [result, categories] = await Promise.all([getAuthorWorkspace(user), getCategoryOptions()]);
  if (!result.ok) return <ApiErrorPanel error={asApiFailure(result)} what="your author profile" />;
  const { profile, limits } = result.data;
  if (profile?.status !== "approved") redirect("/account/author");

  return (
    <div className="flex flex-col gap-4">
      <Link href="/account/author" className="text-body-sm text-primary underline">
        Back to your author profile
      </Link>
      <section className="panel p-5">
        <SectionHeading
          level={1}
          title="Add a missing publication"
          description="The dataset covers AI research led from Sri Lanka. A paper that is not AI research, or not Sri Lanka-led, will be declined — that keeps every record judged by the same rules."
        />
        <NewPublicationForm
          me={{
            slug: profile.slug,
            display_name: profile.display_name,
            names: submitterNames(result.data),
            institution: profile.institution,
            affiliations: profile.affiliations ?? [],
          }}
          publicationTypes={limits.publication_types}
          categories={categories.ok ? categories.value.data.fields : []}
        />
      </section>
    </div>
  );
}
