"use server";

import { revalidatePath } from "next/cache";

import { requireCapability } from "@/services/auth/server";
import type { ActionState } from "@/services/forms/state";
import {
  countActiveAdmins,
  findUserById,
  setUserDisabled,
  setUserRole,
} from "@/services/auth/store";
import { decideCandidate } from "@/services/workspace/resolution";
import { recordAudit, resolveFlag } from "@/services/workspace/store";
import { isAccountRole } from "@/types/auth";

/* ------------------------------------------------------------ flag triage */

export async function triageFlag(
  _state: ActionState,
  formData: FormData,
): Promise<ActionState> {
  const actor = await requireCapability("admin.flags.triage", "/admin/flags");

  const flagId = String(formData.get("flag_id") ?? "");
  const decision = String(formData.get("decision") ?? "");
  const note = String(formData.get("note") ?? "");

  if (decision !== "accepted" && decision !== "rejected") {
    return { status: "error", message: "Choose accept or reject." };
  }

  const flag = await resolveFlag({ flagId, status: decision, note, actor });
  if (!flag) return { status: "error", message: "That flag no longer exists." };

  revalidatePath("/admin/flags");
  revalidatePath("/admin");
  revalidatePath("/account/flags");
  return {
    status: "ok",
    message:
      decision === "accepted"
        ? "Accepted. The record is queued for the next pipeline correction pass."
        : "Rejected and closed.",
  };
}

/* ------------------------------------------------------ resolution queue */

export async function decideResolution(
  _state: ActionState,
  formData: FormData,
): Promise<ActionState> {
  const actor = await requireCapability(
    "admin.resolution.decide",
    "/admin/review",
  );

  const candidateId = String(formData.get("candidate_id") ?? "");
  const decision = String(formData.get("decision") ?? "");

  if (decision !== "merged" && decision !== "rejected") {
    return { status: "error", message: "Choose merge or keep separate." };
  }

  const candidate = await decideCandidate({ candidateId, decision, actor });
  if (!candidate) {
    return { status: "error", message: "That candidate is no longer queued." };
  }

  revalidatePath("/admin/review");
  revalidatePath("/admin");
  return {
    status: "ok",
    message:
      decision === "merged"
        ? "Marked as the same work. The merge is applied on the next pipeline run."
        : "Kept as two distinct records.",
  };
}

/* -------------------------------------------------------- user management */

/**
 * Change a user's role.
 *
 * Guarded against removing the last administrator: with no administrator left,
 * nobody could grant the role back and the console would be permanently
 * unreachable. The same guard covers suspension below.
 */
export async function changeUserRole(
  _state: ActionState,
  formData: FormData,
): Promise<ActionState> {
  const actor = await requireCapability("admin.users.manage", "/admin/users");

  const userId = String(formData.get("user_id") ?? "");
  const role = String(formData.get("role") ?? "");
  if (!isAccountRole(role)) {
    return { status: "error", message: "Unknown role." };
  }

  const target = await findUserById(userId);
  if (!target) return { status: "error", message: "No such account." };
  if (target.role === role) {
    return { status: "ok", message: `${target.name} is already ${role}.` };
  }

  if (
    target.role === "admin" &&
    role === "user" &&
    (await countActiveAdmins()) <= 1
  ) {
    return {
      status: "error",
      message:
        "This is the last active administrator. Promote someone else before stepping down.",
    };
  }

  await setUserRole(userId, role);
  await recordAudit({
    action: "user.role_changed",
    subject: userId,
    summary: `${target.name} changed from ${target.role} to ${role}`,
    actor,
  });

  revalidatePath("/admin/users");
  revalidatePath("/admin");
  return {
    status: "ok",
    message: `${target.name} is now ${role === "admin" ? "an administrator" : "a signed-in user"}. The change applies at their next sign-in.`,
  };
}

export async function toggleUserAccess(
  _state: ActionState,
  formData: FormData,
): Promise<ActionState> {
  const actor = await requireCapability("admin.users.manage", "/admin/users");

  const userId = String(formData.get("user_id") ?? "");
  const disable = String(formData.get("disable") ?? "") === "true";

  const target = await findUserById(userId);
  if (!target) return { status: "error", message: "No such account." };

  if (disable && target.id === actor.id) {
    return { status: "error", message: "You cannot suspend your own account." };
  }
  if (
    disable &&
    target.role === "admin" &&
    (await countActiveAdmins()) <= 1
  ) {
    return {
      status: "error",
      message: "This is the last active administrator and cannot be suspended.",
    };
  }

  await setUserDisabled(userId, disable);
  await recordAudit({
    action: disable ? "user.disabled" : "user.enabled",
    subject: userId,
    summary: `${target.name} ${disable ? "suspended" : "reinstated"}`,
    actor,
  });

  revalidatePath("/admin/users");
  return {
    status: "ok",
    message: disable
      ? `${target.name} is suspended. Their existing session stays valid until it expires.`
      : `${target.name} can sign in again.`,
  };
}
