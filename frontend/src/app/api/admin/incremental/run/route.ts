import { NextResponse } from "next/server";

import { can } from "@/services/auth/permissions";
import { getViewer } from "@/services/auth/server";
import { startIncrementalJob } from "@/services/admin/incremental";

interface RunRequest {
  fromDate?: string;
  toDate?: string;
  reviewThreshold?: string;
}

export async function POST(request: Request) {
  const viewer = await getViewer();
  if (!can(viewer.role, "admin.pipeline.view")) {
    return NextResponse.json(
      { error: { code: "forbidden", message: "Administrator access required." } },
      { status: 403 },
    );
  }

  const body = (await request.json().catch(() => ({}))) as RunRequest;
  const result = await startIncrementalJob(body);
  if (!result.ok) {
    const status =
      result.code === "already_running"
        ? 409
        : result.code === "invalid_request"
          ? 400
          : 501;

    return NextResponse.json(
      { error: { code: result.code, message: result.message } },
      { status },
    );
  }

  return NextResponse.json({ data: result }, { status: 202 });
}
