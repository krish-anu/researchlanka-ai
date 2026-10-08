import { redirect } from "next/navigation";

import { ApplicationForm, EMPTY_APPLICATION, type ApplicationDraft } from "@/components/authors/ApplicationForm";
import { ApiErrorPanel } from "@/components/ui/Feedback";
import { APPLICATION_STATUS_PATH, getViewer } from "@/services/auth/server";
import { getAuthorWorkspace } from "@/services/authors";
import { asApiFailure } from "@/services/backend";
import type { AuthorWorkspace } from "@/types/authors";

export const metadata = {
  title: "Apply for an author profile",
  description:
    "Researchers whose work is in the ResearchLanka dataset can apply for a verified author profile.",
};

function draftFrom(workspace: AuthorWorkspace): ApplicationDraft {
  const profile = workspace.profile;
  if (!profile) return EMPTY_APPLICATION;
  return {
    display_name: profile.display_name,
    name_variants: profile.name_variants.join("\n"),
    orcid: profile.orcid ?? "",
    institution: profile.institution,
    department: profile.department,
    position_title: profile.position_title,
    application_note: profile.application_note,
    claims: workspace.claims
      .filter((claim) => claim.status === "pending")
      .map((claim) => ({
        publication_key: claim.publication_key,
        name_as_listed: claim.name_as_listed,
        title: claim.publication.title ?? claim.publication_key,
        publication_year: claim.publication.publication_year,
      })),
  };
}

/**
 * One page, three entrances: a visitor signs up as an author (the account
 * waits for approval), a signed-in account applies, or an applicant who was
 * asked for changes revises the application.
 */
export default async function AuthorApplicationPage() {
  const viewer = await getViewer();
  const account = viewer.user ?? (viewer.applicant ? { ...viewer.applicant } : null);

  let mode: "sign-up" | "account" | "resubmit" = "sign-up";
  let initial = EMPTY_APPLICATION;

  if (account) {
    const workspace = await getAuthorWorkspace(account);
    if (!workspace.ok) {
      return <ApiErrorPanel error={asApiFailure(workspace)} what="your author application" />;
    }
    const status = workspace.data.profile?.status;
    if (viewer.user) {
      if (status) redirect("/account/author");
      mode = "account";
      initial = { ...EMPTY_APPLICATION, display_name: viewer.user.name };
    } else {
      // An applicant can only revise an application that was returned to them,
      // or send one if their first attempt never reached the server.
      if (status && status !== "changes_requested") redirect(APPLICATION_STATUS_PATH);
      mode = "resubmit";
      initial = workspace.data.profile ? draftFrom(workspace.data) : { ...EMPTY_APPLICATION, display_name: account.name };
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
      <header>
        <p className="page-eyebrow">Author profiles</p>
        <h1 className="mt-1 font-display text-h1 text-ink">
          {mode === "resubmit" ? "Update your author application" : "Apply for an author profile"}
        </h1>
        <p className="mt-2 max-w-prose text-body-sm text-ink-secondary">
          A verified profile groups your publications under you rather than under a name that other
          researchers may share. Once approved you can write your own bio and links, suggest
          corrections to your publications, and add papers the dataset is missing — each correction
          and new paper is reviewed by an administrator first.
        </p>
      </header>
      <div className="panel p-6 md:p-8">
        <ApplicationForm mode={mode} initial={initial} />
      </div>
    </div>
  );
}
