/**
 * Author profile calls to the backend.
 *
 * Server-only: everything here goes through `backendRequest`, which carries
 * the backend admin token and the signed-in account as the actor. The backend
 * re-checks that the actor owns what they are changing; the server actions
 * that call these still check the capability first.
 */

import { backendRequest, type BackendResult } from "@/services/backend";
import type { SessionUser } from "@/types/auth";
import type {
  ApplicationReview,
  AuthorQueueSummary,
  AuthorWorkspace,
  Contribution,
  DoiLookupResult,
  EditableField,
  ReviewedClaim,
  ReviewedContribution,
  ReviewPage,
} from "@/types/authors";

export interface ApplicationInput {
  display_name: string;
  name_variants: string[];
  orcid: string;
  institution: string;
  department: string;
  position_title: string;
  application_note: string;
  claims: ClaimInput[];
}

export interface ClaimInput {
  publication_key: string;
  name_as_listed: string;
}

export const getAuthorWorkspace = (actor: SessionUser) =>
  backendRequest<AuthorWorkspace>("/author/me", { actor });

export const submitAuthorApplication = (actor: SessionUser, input: ApplicationInput) =>
  backendRequest<AuthorWorkspace>("/author/applications", {
    method: "POST",
    actor,
    body: { ...input },
  });

export const updateAuthorProfile = (actor: SessionUser, input: Record<string, unknown>) =>
  backendRequest<AuthorWorkspace>("/author/profile", { method: "POST", actor, body: input });

/** `nameVariants` are spellings merged with "Add all as me", recorded on the profile. */
export const requestAuthorClaims = (actor: SessionUser, claims: ClaimInput[], nameVariants: string[] = []) =>
  backendRequest<AuthorWorkspace>("/author/claims", {
    method: "POST",
    actor,
    body: { claims, name_variants: nameVariants },
  });

export const proposePublicationEdit = (
  actor: SessionUser,
  input: { publication_key: string; changes: Partial<Record<EditableField, string>>; note: string },
) => backendRequest<Contribution>("/author/contributions/edit", { method: "POST", actor, body: input });

export const submitNewPublication = (actor: SessionUser, input: Record<string, unknown>) =>
  backendRequest<Contribution>("/author/contributions/new", { method: "POST", actor, body: input });

export const withdrawContribution = (actor: SessionUser, contributionId: string) =>
  backendRequest<Contribution>("/author/contributions/withdraw", {
    method: "POST",
    actor,
    body: { contribution_id: contributionId },
  });

export interface EditablePublication {
  publication_key: string;
  values: Partial<Record<EditableField, string | number | null>>;
  name_as_listed: string;
  pending_edit: Contribution | null;
  fields: Record<EditableField, string>;
  publication_types: string[];
}

export const getEditablePublication = (actor: SessionUser, publicationKey: string) =>
  backendRequest<EditablePublication>("/author/publication", {
    actor,
    params: { publication_key: publicationKey },
  });

export const lookupPublicationDoi = (actor: SessionUser, doi: string) =>
  backendRequest<DoiLookupResult>("/author/lookup/doi", { actor, params: { doi } });

/* --------------------------------------------------------------- admin */

export const listAuthorApplications = (
  actor: SessionUser,
  params: { status?: string; page?: number } = {},
) =>
  backendRequest<ReviewPage<ApplicationReview>>("/admin/authors/applications", {
    actor,
    params: { status: params.status, page: params.page },
  });

export const decideAuthorApplication = (actor: SessionUser, input: Record<string, unknown>) =>
  backendRequest<{ user_id: string; status: string; display_name: string; already_decided: boolean }>(
    "/admin/authors/applications/decide",
    { method: "POST", actor, body: input },
  );

export const listAuthorClaimRequests = (actor: SessionUser, page = 1) =>
  backendRequest<ReviewPage<ReviewedClaim>>("/admin/authors/claims", { actor, params: { page } });

export const decideAuthorClaims = (actor: SessionUser, input: Record<string, unknown>) =>
  backendRequest<{ approved: number; rejected: number }>("/admin/authors/claims/decide", {
    method: "POST",
    actor,
    body: input,
  });

export const listAuthorContributions = (
  actor: SessionUser,
  params: { status?: string; type?: string; page?: number } = {},
) =>
  backendRequest<ReviewPage<ReviewedContribution>>("/admin/authors/contributions", {
    actor,
    params: { status: params.status, type: params.type, page: params.page },
  });

export const decideAuthorContribution = (actor: SessionUser, input: Record<string, unknown>) =>
  backendRequest<Contribution>("/admin/authors/contributions/decide", {
    method: "POST",
    actor,
    body: input,
  });

export const getAuthorQueueSummary = () =>
  backendRequest<AuthorQueueSummary>("/admin/authors/summary");

/** First field the backend named in a validation error, for focusing the input. */
export function errorField(result: BackendResult<unknown>): string | null {
  if (result.ok) return null;
  const field = result.details?.field;
  return typeof field === "string" ? field : null;
}

export const removeAuthorClaim = (actor: SessionUser, claimId: string) =>
  backendRequest<AuthorWorkspace>("/author/claims/remove", {
    method: "POST",
    actor,
    body: { claim_id: claimId },
  });
