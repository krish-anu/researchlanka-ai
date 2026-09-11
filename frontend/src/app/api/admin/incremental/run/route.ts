import { NextResponse } from "next/server";

import { can } from "@/services/auth/permissions";
import { getViewer } from "@/services/auth/server";
import { startIncrementalJob } from "@/services/admin/incremental";
import { recordAudit } from "@/services/workspace/store";

export async function POST(request: Request) {
  const viewer = await getViewer();
  if (!viewer.user || !can(viewer.role, "admin.pipeline.run")) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    body = {};
  }

  const input = body && typeof body === "object" ? body as Record<string, unknown> : {};
  const status = await startIncrementalJob({
    fromDate: typeof input.from_date === "string" ? input.from_date : "",
    toDate: typeof input.to_date === "string" ? input.to_date : "",
    confidenceReviewThreshold:
      typeof input.confidence_review_threshold === "string"
        ? input.confidence_review_threshold
        : "",
  });

  await recordAudit({
    action: "pipeline.incremental_started",
    subject: "incremental-ai-update",
    summary: `Started AI-only incremental update with labels ${status.db_labels.join(", ")}`,
    actor: viewer.user,
  }).catch((error) => {
    console.error("Could not record incremental update audit entry", error);
  });

  return NextResponse.json(status);
}
