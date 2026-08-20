"use server";

import { revalidatePath } from "next/cache";

import { requireCapability } from "@/services/auth/server";
import type { ActionState } from "@/services/forms/state";
import {
  createFlag,
  removeSavedItem,
  toggleSavedItem,
} from "@/services/workspace/store";
import type { FlagReason } from "@/services/workspace/types";
import { FLAG_REASON_LABEL } from "@/services/workspace/types";

function isFlagReason(value: string): value is FlagReason {
  return Object.hasOwn(FLAG_REASON_LABEL, value);
}

/**
 * Save or unsave a publication.
 *
 * The capability check is repeated here rather than trusted from the calling
 * component: a server action is a public endpoint, so a hidden button is no
 * guarantee the action is never invoked.
 */
export async function toggleSave(
  _state: ActionState,
  formData: FormData,
): Promise<ActionState> {
  const publicationKey = String(formData.get("publication_key") ?? "");
  const title = String(formData.get("title") ?? "Untitled record");
  if (!publicationKey) {
    return { status: "error", message: "Missing publication." };
  }

  const user = await requireCapability(
    "library.save",
    `/publications/${publicationKey}`,
  );
  const { saved } = await toggleSavedItem({
    userId: user.id,
    publicationKey,
    title,
  });

  revalidatePath("/account/saved");
  return {
    status: "ok",
    message: saved ? "Saved to your library." : "Removed from your library.",
  };
}

export async function removeSaved(formData: FormData): Promise<void> {
  const itemId = String(formData.get("item_id") ?? "");
  const user = await requireCapability("library.save", "/account/saved");
  if (itemId) await removeSavedItem(user.id, itemId);
  revalidatePath("/account/saved");
}

export async function submitFlag(
  _state: ActionState,
  formData: FormData,
): Promise<ActionState> {
  const publicationKey = String(formData.get("publication_key") ?? "");
  const title = String(formData.get("title") ?? "Untitled record");
  const reason = String(formData.get("reason") ?? "");
  const detail = String(formData.get("detail") ?? "");

  if (!publicationKey || !isFlagReason(reason)) {
    return { status: "error", message: "Choose what looks wrong." };
  }
  if (detail.trim().length < 10) {
    return {
      status: "error",
      message: "Add a sentence or two so a reviewer knows what to check.",
    };
  }

  const user = await requireCapability(
    "record.flag",
    `/publications/${publicationKey}`,
  );
  const created = await createFlag({
    publicationKey,
    title,
    reason,
    detail,
    reporter: user,
  });

  if (!created.ok) {
    return {
      status: "error",
      message: "You already have an open flag on this record.",
    };
  }

  revalidatePath("/account/flags");
  revalidatePath("/admin/flags");
  return {
    status: "ok",
    message: "Flag submitted. An administrator will review it.",
  };
}
