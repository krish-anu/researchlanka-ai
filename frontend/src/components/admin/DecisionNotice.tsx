const MESSAGES: Record<string, string> = {
  approve: "Application approved. The account works from its next request, and the profile is public.",
  request_changes: "The applicant was asked to update the application. They see your message when they sign in.",
  reject: "Application not approved. The applicant sees your reason when they sign in.",
  claim_approved: "Claim approved. The publication now shows on the author's profile.",
  claim_rejected: "Claim rejected. The author sees your reason.",
  correction_approved: "Correction approved. It shows on the public record now and survives pipeline reloads.",
  publication_approved: "Publication approved and added to the public dataset as an AI publication.",
  rejected: "Rejected. The author sees your reason.",
};

/** Confirmation after a decision, keyed by a fixed code so the URL cannot inject text. */
export function DecisionNotice({ code }: { code: string | undefined }) {
  const message = code ? MESSAGES[code] : undefined;
  if (!message) return null;
  return (
    <p role="status" className="rounded border border-l-[3px] border-rule border-l-good bg-surface px-3 py-2 text-body-sm text-success-text">
      {message}
    </p>
  );
}
