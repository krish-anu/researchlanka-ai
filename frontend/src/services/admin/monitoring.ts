export interface DriftMonth {
  month: string;
  auto_ai_rate: number;
  auto_ai_count: number;
  total: number;
}

export interface MonitoringMetrics {
  public_publications: number;
  pending_reviews: number;
  ai_acceptance_rate: number;
  auto_ai_rate: number;
  auto_non_ai_rate: number;
  false_positive_rate: number;
  human_disagreement_rate: number;
  publications_collected_per_day: number;
  failed_ingestion_jobs: number;
  duplicate_rate: number;
  missing_abstract_percentage: number;
  missing_doi_percentage: number;
  ownership_review_count: number;
  model_version: string | null;
  dataset_version: string | null;
  pipeline_version: string | null;
  last_successful_pipeline_run: string | null;
  avg_publications_collected_per_run: number;
  drift: {
    previous_month: DriftMonth | null;
    current_month: DriftMonth | null;
    auto_ai_rate_delta_points: number | null;
    alert: boolean;
    alert_threshold_points: number;
    monthly: DriftMonth[];
  };
  metric_notes: Record<string, string>;
}

const REMOTE_API_BASE_URL = process.env.API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL;
const REMOTE_ADMIN_API_TOKEN = process.env.RESEARCHLANKA_ADMIN_API_TOKEN;

export async function readMonitoringMetrics(): Promise<MonitoringMetrics | null> {
  if (!REMOTE_API_BASE_URL) return null;
  try {
    const response = await fetch(
      `${REMOTE_API_BASE_URL.replace(/\/$/, "")}/admin/monitoring`,
      {
        headers: {
          Accept: "application/json",
          ...(REMOTE_ADMIN_API_TOKEN
            ? { "X-ResearchLanka-Admin-Token": REMOTE_ADMIN_API_TOKEN }
            : {}),
        },
        cache: "no-store",
      },
    );
    if (!response.ok) return null;
    const payload = (await response.json()) as { data?: MonitoringMetrics };
    return payload.data ?? null;
  } catch {
    return null;
  }
}
