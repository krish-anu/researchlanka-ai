import { ROLE_LABEL, type Role } from "@/types/auth";

/**
 * Role chips use brand / neutral tiers only. Machine violet is reserved for
 * model-generated content (`MachinePanel`), not role labels.
 */
const TONE: Record<Role, string> = {
  guest: "border-rule bg-surface text-muted",
  user: "border-rule bg-wash text-ink-secondary",
  reviewer: "border-warning/45 bg-wash text-ink-secondary",
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
