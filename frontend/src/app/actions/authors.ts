"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { checkPasswordStrength } from "@/services/auth/password";
import {
  APPLICATION_STATUS_PATH,
  getViewer,
  requireCapability,
} from "@/services/auth/server";
import { sessionSecretProblem } from "@/services/auth/session";
import { startSession } from "@/services/auth/sessionCookie";
import {
  createUser,
  deleteUnusedPendingUser,
  findUserByEmail,
  findUserById,
  recordSignIn,
  setUserStatus,
} from "@/services/auth/store";
import * as authors from "@/services/authors";
import type { BackendResult } from "@/services/backend";
import type { AuthorFormState } from "@/services/forms/state";
import { authorProfileHref } from "@/services/links";
import { recordAudit } from "@/services/workspace/store";
import { accountStatus, publicUser } from "@/types/auth";
import type { DoiLookupResult, EditableField } from "@/types/authors";

/*
 * Every export here is a server action the browser can call directly, so each
 * one checks who is calling before doing anything. Helpers stay unexported.
 */

const EDITABLE_FIELDS: EditableField[] = [
  "title",
  "abstract",
  "keywords",
  "publication_year",
  "type",
  "journal",
  "publisher",
  "volume",
  "issue",
  "first_page",
  "last_page",
  "language",
  "url",
  "pdf_url",
];

const NEW_PUBLICATION_FIELDS = [
  "doi",
  "title",
  "abstract",
  "keywords",
  "publication_year",
  "publication_date",
  "type",
  "journal",
  "publisher",
  "volume",
  "issue",
  "first_page",
  "last_page",
  "language",
  "url",
  "pdf_url",
  "your_author_name",
  "primary_field",
  "primary_subfield",
  "note",
] as const;

function text(formData: FormData, name: string): string {
  return String(formData.get(name) ?? "").trim();
}

function lines(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function parseJsonList(formData: FormData, name: string): unknown[] | null {
  const raw = text(formData, name);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function parseClaims(formData: FormData): authors.ClaimInput[] | null {
  const list = parseJsonList(formData, "claims");
  if (list === null) return null;
  const claims: authors.ClaimInput[] = [];
  for (const item of list) {
    if (!item || typeof item !== "object") return null;
    const { publication_key, name_as_listed } = item as Record<string, unknown>;
    if (typeof publication_key !== "string" || typeof name_as_listed !== "string") return null;
    claims.push({ publication_key, name_as_listed });
  }
  return claims;
}

/** Backend field names that live inside the claim picker rather than an input. */
const CLAIM_FIELDS = new Set(["publication_key", "name_as_listed", "claims"]);

function failure(result: BackendResult<unknown>): AuthorFormState {
  if (result.ok) return { status: "ok", message: "" };
  const field = typeof result.details?.field === "string" ? result.details.field : null;
  return {
    status: "error",
    message: result.message,
    field: field && CLAIM_FIELDS.has(field) ? "claims" : field,
    details: result.details ?? null,
  };
}

function error(message: string, field: string | null = null): AuthorFormState {
  return { status: "error", message, field };
}

function applicationInput(formData: FormData): authors.ApplicationInput | null {
  const claims = parseClaims(formData);
  if (claims === null) return null;
  return {
    display_name: text(formData, "display_name"),
    name_variants: lines(String(formData.get("name_variants") ?? "")),
    orcid: text(formData, "orcid"),
    institution: text(formData, "institution"),
    department: text(formData, "department"),
    position_title: text(formData, "position_title"),
    application_note: String(formData.get("application_note") ?? "").trim(),
    claims,
  };
}

/* ------------------------------------------------------------ application */

/**
 * Submit an author application.
 *
 * Three callers share it: a visitor signing up (a new account is created in
 * the `pending` state and only becomes usable once an administrator approves),
 * an applicant resubmitting after being asked for changes, and an existing
 * active account applying for a profile — whose account keeps working as it
 * does now while the application waits.
 */
export async function submitAuthorApplicationAction(
  _state: AuthorFormState,
  formData: FormData,
): Promise<AuthorFormState> {
  const input = applicationInput(formData);
  if (!input) return error("The publication list could not be read. Reload the page and try again.", "claims");
  if (!input.display_name) return error("Enter your name as you want it on your profile.", "display_name");

  const viewer = await getViewer();

  if (viewer.user) {
    const user = await requireCapability("author.apply", "/register/author");
    const result = await authors.submitAuthorApplication(user, input);
    if (!result.ok) return failure(result);
    revalidatePath("/account/author");
    redirect("/account/author");
  }

  if (viewer.applicant) {
    const { status, ...user } = viewer.applicant;
    if (status === "rejected") {
      return error("This application was not approved. Contact a platform administrator.");
    }
    const result = await authors.submitAuthorApplication(user, input);
    if (!result.ok) return failure(result);
    revalidatePath(APPLICATION_STATUS_PATH);
    redirect(APPLICATION_STATUS_PATH);
  }

  const misconfigured = sessionSecretProblem();
  if (misconfigured) return error(misconfigured);

  const email = text(formData, "email");
  const password = String(formData.get("password") ?? "");
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    return error("Enter a valid email address.", "email");
  }
  const weak = checkPasswordStrength(password);
  if (weak) return error(weak.message, "password");
  if (await findUserByEmail(email)) {
    return error(
      "An account already exists for that email address. Sign in and apply from your account instead.",
      "email",
    );
  }

  const created = await createUser({
    name: input.display_name,
    email,
    password,
    role: "user",
    status: "pending",
  });
  if (!created.ok) {
    return error("An account already exists for that email address.", "email");
  }

  const result = await authors.submitAuthorApplication(publicUser(created.user), input);
  if (!result.ok) {
    // Nothing reached the backend, so do not leave a pending account behind
    // that the visitor cannot see or fix: undo it and let them correct the form.
    await deleteUnusedPendingUser(created.user.id);
    return failure(result);
  }

  await recordSignIn(created.user.id);
  await startSession(created.user);
  redirect(APPLICATION_STATUS_PATH);
}

/* ----------------------------------------------------------- author tools */

/** Bio, position, department and links: the author's own words, live at once. */
export async function updateAuthorProfileAction(
  _state: AuthorFormState,
  formData: FormData,
): Promise<AuthorFormState> {
  const user = await requireCapability("author.contribute", "/account/author");
  const payload: Record<string, unknown> = {
    bio: String(formData.get("bio") ?? ""),
    department: text(formData, "department"),
    position_title: text(formData, "position_title"),
    links: {
      website_url: text(formData, "website_url"),
      google_scholar_url: text(formData, "google_scholar_url"),
      researchgate_url: text(formData, "researchgate_url"),
      linkedin_url: text(formData, "linkedin_url"),
    },
  };
  // Sent only by forms that show the history, so others cannot clear it.
  if (formData.has("affiliations")) {
    const affiliations = parseJsonList(formData, "affiliations");
    if (affiliations === null) return error("The affiliation list could not be read. Reload the page and try again.", "affiliations");
    payload.affiliations = affiliations;
  }
  const result = await authors.updateAuthorProfile(user, payload);
  if (!result.ok) return failure(result);
  revalidatePath("/account/author");
  const slug = result.data.profile?.slug;
  if (slug) revalidatePath(authorProfileHref(slug));
  return { status: "ok", message: "Saved. Your public profile shows this now." };
}

export async function requestAuthorClaimsAction(
  _state: AuthorFormState,
  formData: FormData,
): Promise<AuthorFormState> {
  const user = await requireCapability("author.contribute", "/account/author");
  const claims = parseClaims(formData);
  if (claims === null) return error("The publication list could not be read. Reload the page and try again.", "claims");
  if (claims.length === 0) return error("Add at least one publication.", "claims");
  const variants = parseJsonList(formData, "name_variants") ?? [];
  const result = await authors.requestAuthorClaims(
    user,
    claims,
    variants.filter((item): item is string => typeof item === "string"),
  );
  if (!result.ok) return failure(result);
  revalidatePath("/account/author");
  const added = result.data.claims_added ?? 0;
  return {
    status: "ok",
    message:
      added === 0
        ? "Those publications are already on your list."
        : `${added} ${added === 1 ? "publication was" : "publications were"} sent to an administrator. They appear on your profile once approved.`,
  };
}

/**
 * Propose an edit to one publication.
 *
 * The form posts every editable field next to the value it was rendered with,
 * and only fields the author actually changed are sent — so an untouched
 * field never becomes a "change" because the record moved underneath it.
 */
export async function proposePublicationEditAction(
  _state: AuthorFormState,
  formData: FormData,
): Promise<AuthorFormState> {
  const user = await requireCapability("author.contribute", "/account/author");
  const publicationKey = text(formData, "publication_key");
  if (!publicationKey) return error("Choose a publication to edit.");

  const changes: Partial<Record<EditableField, string>> = {};
  for (const field of EDITABLE_FIELDS) {
    if (!formData.has(`field:${field}`)) continue;
    const value = String(formData.get(`field:${field}`) ?? "");
    const original = String(formData.get(`original:${field}`) ?? "");
    if (value.trim() !== original.trim()) changes[field] = value;
  }
  if (Object.keys(changes).length === 0) return error("Change at least one field before sending.");

  const result = await authors.proposePublicationEdit(user, {
    publication_key: publicationKey,
    changes,
    note: String(formData.get("note") ?? ""),
  });
  if (!result.ok) {
    const state = failure(result);
    return { ...state, field: state.field ? `field:${state.field}` : null };
  }
  revalidatePath("/account/author");
  redirect("/account/author?sent=edit");
}

export async function submitNewPublicationAction(
  _state: AuthorFormState,
  formData: FormData,
): Promise<AuthorFormState> {
  const user = await requireCapability("author.contribute", "/account/author/new");
  const authorRows = parseJsonList(formData, "authors");
  if (authorRows === null) return error("The author list could not be read. Reload the page and try again.", "authors");

  const payload: Record<string, unknown> = { authors: authorRows };
  for (const field of NEW_PUBLICATION_FIELDS) {
    payload[field] = String(formData.get(field) ?? "");
  }

  const result = await authors.submitNewPublication(user, payload);
  if (!result.ok) return failure(result);
  revalidatePath("/account/author");
  redirect("/account/author?sent=publication");
}

/** DOI autofill for the new-publication form. Returns only the public metadata. */
export async function lookupDoiAction(
  doi: string,
): Promise<{ ok: true; data: DoiLookupResult } | { ok: false; message: string }> {
  const user = await requireCapability("author.contribute", "/account/author/new");
  const result = await authors.lookupPublicationDoi(user, String(doi ?? "").trim());
  return result.ok ? { ok: true, data: result.data } : { ok: false, message: result.message };
}

/** Take a publication off the author's own profile; the publication itself stays. */
export async function removeClaimAction(
  _state: AuthorFormState,
  formData: FormData,
): Promise<AuthorFormState> {
  const user = await requireCapability("author.contribute", "/account/author");
  const result = await authors.removeAuthorClaim(user, text(formData, "claim_id"));
  if (!result.ok) return failure(result);
  revalidatePath("/account/author");
  const slug = result.data.profile?.slug;
  if (slug) revalidatePath(authorProfileHref(slug));
  return { status: "ok", message: "Removed from your profile." };
}

export async function withdrawContributionAction(
  _state: AuthorFormState,
  formData: FormData,
): Promise<AuthorFormState> {
  const user = await requireCapability("author.contribute", "/account/author");
  const result = await authors.withdrawContribution(user, text(formData, "contribution_id"));
  if (!result.ok) return failure(result);
  revalidatePath("/account/author");
  return { status: "ok", message: "Withdrawn." };
}

/* ------------------------------------------------------------ admin review */

const APPLICATION_AUDIT = {
  approve: "author.application_approved",
  request_changes: "author.application_changes_requested",
  reject: "author.application_rejected",
} as const;

/**
 * Decide an author application, then bring the account in line.
 *
 * The profile lives in the backend and the account in this app's store, so
 * the two are updated in order — backend first. The backend treats a repeat
 * of the same decision as a no-op, which makes this whole action safe to
 * retry if the account update fails after the backend has recorded it.
 */
export async function decideAuthorApplicationAction(
  _state: AuthorFormState,
  formData: FormData,
): Promise<AuthorFormState> {
  const actor = await requireCapability("admin.authors.manage", "/admin/authors");
  const decision = text(formData, "decision");
  if (decision !== "approve" && decision !== "request_changes" && decision !== "reject") {
    return error("Choose approve, request changes or reject.");
  }
  const rejectedClaims = formData.getAll("reject_claim").map(String);

  const result = await authors.decideAuthorApplication(actor, {
    profile_id: text(formData, "profile_id"),
    decision,
    reason: String(formData.get("reason") ?? ""),
    record_version: text(formData, "record_version") || undefined,
    claim_decisions: Object.fromEntries(rejectedClaims.map((id) => [id, "rejected"])),
  });
  if (!result.ok) return failure(result);

  const account = await findUserById(result.data.user_id);
  if (account && accountStatus(account) === "pending") {
    try {
      if (decision === "approve") await setUserStatus(account.id, "active");
      if (decision === "reject") await setUserStatus(account.id, "rejected");
    } catch (cause) {
      console.error("[authors] Could not update account status after decision", cause);
      return error(
        "The decision was recorded, but the account could not be updated. Submit the same decision again to retry.",
      );
    }
  }

  await recordAudit({
    action: APPLICATION_AUDIT[decision],
    subject: account?.id ?? result.data.user_id,
    summary: `${result.data.display_name}: author application ${decision.replace("_", " ")}`,
    actor,
  }).catch((cause) => console.error("[authors] Could not record audit entry", cause));

  revalidatePath("/admin/authors");
  revalidatePath("/admin");
  // The decided card leaves the queue on re-render, taking any inline message
  // with it, so the confirmation travels as a fixed code the page renders.
  redirect(`/admin/authors?decided=${decision}`);
}

export async function decideAuthorClaimAction(
  _state: AuthorFormState,
  formData: FormData,
): Promise<AuthorFormState> {
  const actor = await requireCapability("admin.authors.manage", "/admin/authors?tab=claims");
  const decision = text(formData, "decision");
  if (decision !== "approved" && decision !== "rejected") return error("Choose approve or reject.");
  const claimId = text(formData, "claim_id");

  const result = await authors.decideAuthorClaims(actor, {
    claim_decisions: { [claimId]: decision },
    reason: String(formData.get("reason") ?? ""),
  });
  if (!result.ok) return failure(result);

  await recordAudit({
    action: "author.claims_decided",
    subject: claimId,
    summary: `Publication claim ${decision}`,
    actor,
  }).catch((cause) => console.error("[authors] Could not record audit entry", cause));
  revalidatePath("/admin/authors");
  redirect(`/admin/authors?tab=claims&decided=claim_${decision}`);
}

export async function decideAuthorContributionAction(
  _state: AuthorFormState,
  formData: FormData,
): Promise<AuthorFormState> {
  const actor = await requireCapability("admin.authors.manage", "/admin/contributions");
  const decision = text(formData, "decision");
  if (decision !== "approve" && decision !== "reject") return error("Choose approve or reject.");

  const result = await authors.decideAuthorContribution(actor, {
    contribution_id: text(formData, "contribution_id"),
    decision,
    reason: String(formData.get("reason") ?? ""),
    record_version: text(formData, "record_version") || undefined,
    ai_decision: text(formData, "ai_decision") || undefined,
    ownership_verified: formData.get("ownership_verified") === "on",
    // Blank keeps the category the author, OpenAlex or the model gave.
    primary_field: text(formData, "override_primary_field") || undefined,
    primary_subfield: text(formData, "override_primary_subfield") || undefined,
  });
  if (!result.ok) return failure(result);

  await recordAudit({
    action: decision === "approve" ? "author.contribution_approved" : "author.contribution_rejected",
    subject: result.data.contribution_id,
    summary: `${result.data.contribution_type === "new_publication" ? "New publication" : "Publication edit"} ${decision === "approve" ? "approved" : "rejected"}`,
    actor,
  }).catch((cause) => console.error("[authors] Could not record audit entry", cause));
  revalidatePath("/admin/contributions");
  revalidatePath("/admin");
  const outcome =
    decision === "reject"
      ? "rejected"
      : result.data.contribution_type === "new_publication"
        ? "publication_approved"
        : "correction_approved";
  redirect(`/admin/contributions?decided=${outcome}`);
}
