import { NextResponse } from "next/server";

import { can } from "@/services/auth/permissions";
import { getViewer } from "@/services/auth/server";
import { readIncrementalJobStatus } from "@/services/admin/incremental";

export async function GET() {
  const viewer = await getViewer();
  if (!can(viewer.role, "admin.pipeline.view")) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const status = await readIncrementalJobStatus();
  return NextResponse.json(status);
}
