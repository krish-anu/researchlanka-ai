export interface DriftMonth {
  month: string;
  auto_ai_rate: number;
  auto_ai_count: number;
  total: number;
}

export interface MLDriftAlert {
  dimension: string;
  severity: "warning" | "critical";
  message: string;
}

export interface PredictionDrift {
  previous_total: number;
  current_total: number;
  previous_ai_rate: number;
  current_ai_rate: number;
  ai_rate_delta_points: number;
  previous_non_ai_rate: number;
  current_non_ai_rate: number;
  previous_review_rate: number;
  current_review_rate: number;
  psi_score: number;
  alert: boolean;
  alert_reasons: string[];
}

export interface ConfidenceDrift {
  previous_mean_p_ai: number;
  current_mean_p_ai: number;
  mean_p_ai_delta: number;
  previous_median_p_ai: number;
  current_median_p_ai: number;
  previous_std_p_ai: number;
  current_std_p_ai: number;
  bins: {
    low: { previous_pct: number; current_pct: number };
    medium: { previous_pct: number; current_pct: number };
    high: { previous_pct: number; current_pct: number; delta_points?: number };
  };
  alert: boolean;
  alert_reasons: string[];
}

export interface FeatureDrift {
  previous_avg_title_words: number;
  current_avg_title_words: number;
  title_words_shift_pct: number;
  previous_avg_abstract_words: number;
  current_avg_abstract_words: number;
  abstract_words_shift_pct: number;
  previous_abstract_presence_pct: number;
  current_abstract_presence_pct: number;
  abstract_presence_delta_points: number;
  alert: boolean;
  alert_reasons: string[];
}

export interface HumanDisagreementDrift {
  previous_human_decisions: number;
  current_human_decisions: number;
  previous_disagreement_rate: number;
  current_disagreement_rate: number;
  disagreement_delta_points: number;
  current_fp_overturns: number;
  current_fn_overturns: number;
  alert: boolean;
  alert_reasons: string[];
}

export interface SourceDriftItem {
  source: string;
  name: string;
  previous_pct: number;
  current_pct: number;
  delta_points: number;
  alert: boolean;
}

export interface SourceDrift {
  sources: SourceDriftItem[];
  max_source_shift_points: number;
  alert: boolean;
  alert_reasons: string[];
}

export interface InstitutionDriftItem {
  institution: string;
  current_count: number;
  current_share_pct: number;
  previous_share_pct: number;
  delta_points: number;
  alert: boolean;
}

export interface InstitutionDrift {
  top_institutions: InstitutionDriftItem[];
  top3_concentration_current_pct: number;
  top3_concentration_previous_pct: number;
  alert: boolean;
  alert_reasons: string[];
}

export interface MissingDataFieldItem {
  label: string;
  previous_pct: number;
  current_pct: number;
  delta_points: number;
  alert: boolean;
}

export interface MissingDataDrift {
  fields: Record<string, MissingDataFieldItem>;
  alert: boolean;
  alert_reasons: string[];
}

export interface MLMonitoringReport {
  status: string;
  date_basis: string;
  previous_period: string | null;
  current_period: string | null;
  overall_alert: boolean;
  active_alerts_count: number;
  active_alerts: MLDriftAlert[];
  prediction_drift: PredictionDrift;
  confidence_drift: ConfidenceDrift;
  feature_drift: FeatureDrift;
  human_disagreement_drift: HumanDisagreementDrift;
  source_drift: SourceDrift;
  institution_drift: InstitutionDrift;
  missing_data_drift: MissingDataDrift;
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
    ml_monitoring?: MLMonitoringReport;
  };
  ml_monitoring?: MLMonitoringReport;
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
