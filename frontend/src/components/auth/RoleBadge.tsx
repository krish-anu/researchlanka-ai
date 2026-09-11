import { ROLE_LABEL, type Role } from "@/types/auth";

/**
 * Role chips borrow the tiers already defined by the design system rather than
 * inventing a fourth colour: administrators take the brand petrol, signed-in
 * users the neutral surface. The machine violet stays reserved for AI output.
 */
const TONE: Record<Role, string> = {
  guest: "border-rule bg-surface text-muted",
  user: "border-rule bg-wash text-ink-secondary",
  admin: "border-primary bg-primary-container text-on-primary",
};

export function RoleBadge({
  role,
  className = "",
}: {
  role: Role;
  className?: string;
}) {
  return (
    <span
      className={`label-caps inline-flex items-center rounded border px-2 py-1 ${TONE[role]} ${className}`}
    >
      {ROLE_LABEL[role]}
    </span>
  );
}
