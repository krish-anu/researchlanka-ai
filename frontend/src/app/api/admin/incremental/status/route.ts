import { NextResponse } from "next/server";

import { can } from "@/services/auth/permissions";
import { getViewer } from "@/services/auth/server";
import { readIncrementalRunSnapshot } from "@/services/admin/incremental";

export async function GET() {
  const viewer = await getViewer();
  if (!can(viewer.role, "admin.pipeline.view")) {
    return NextResponse.json(
      { error: { code: "forbidden", message: "Administrator access required." } },
      { status: 403 },
    );
  }

  const status = await readIncrementalRunSnapshot();
  return NextResponse.json({ ...status, data: status });
}
