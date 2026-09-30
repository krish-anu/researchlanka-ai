"""Comprehensive Real ML Monitoring for scholarly publication pipelines.

Tracks 7 critical drift dimensions:
1. Prediction drift (label shifts, PSI)
2. Confidence distribution drift (P(AI) mean, median, bins)
3. Feature drift (title/abstract lengths, text density)
4. Human disagreement drift (overturns, false positive proxies)
5. Source drift (OpenAlex, Crossref, SLJOL, Repositories %)
6. Institution distribution drift (Sri Lankan research organizations)
7. Missing-data drift (missing abstract, DOI, affiliations)
"""

from __future__ import annotations

import math
from typing import Any
from psycopg.rows import dict_row

# Configurable alert thresholds
PREDICTION_RATE_ALERT_POINTS = 15.0
PSI_ALERT_THRESHOLD = 0.15
CONFIDENCE_MEAN_DELTA_ALERT = 0.10
CONFIDENCE_HIGH_BIN_ALERT_POINTS = 20.0
FEATURE_DRIFT_PCT_THRESHOLD = 30.0
ABSTRACT_PRESENCE_DROP_ALERT_POINTS = 15.0
HUMAN_DISAGREEMENT_ALERT_RATE = 15.0
HUMAN_DISAGREEMENT_DELTA_POINTS = 10.0
SOURCE_DRIFT_ALERT_POINTS = 20.0
INSTITUTION_DRIFT_ALERT_POINTS = 15.0
INSTITUTION_CONCENTRATION_ALERT_PCT = 80.0
MISSING_DATA_INCREASE_ALERT_POINTS = 10.0


def compute_psi(actual_dist: dict[str, float], expected_dist: dict[str, float]) -> float:
    """Calculate Population Stability Index between two probability distributions."""
    psi = 0.0
    all_keys = set(actual_dist.keys()) | set(expected_dist.keys())
    for key in all_keys:
        act = max(actual_dist.get(key, 0.0), 0.0001)
        exp = max(expected_dist.get(key, 0.0), 0.0001)
        psi += (act - exp) * math.log(act / exp)
    return round(psi, 4)


def percent(numerator: Any, denominator: Any) -> float:
    """Calculate percentage rounded to 2 decimal places."""
    try:
        den = float(denominator or 0)
        if den <= 0:
            return 0.0
        return round((float(numerator or 0) / den) * 100, 2)
    except (TypeError, ValueError):
        return 0.0


def determine_date_basis_and_periods(
    connection: Any,
    date_basis: str = "auto",
) -> tuple[str, str | None, str | None]:
    """Determine whether to use loaded_at or publication_date, and fetch the latest 2 months."""
    with connection.cursor(row_factory=dict_row) as cursor:
        if date_basis in ("auto", "loaded_at"):
            cursor.execute(
                """
                SELECT to_char(date_trunc('month', loaded_at), 'YYYY-MM') AS month,
                       count(*) AS count
                FROM final_publications
                WHERE loaded_at IS NOT NULL
                GROUP BY 1
                ORDER BY 1 DESC
                LIMIT 2
                """
            )
            rows = cursor.fetchall()
            if len(rows) >= 2 or date_basis == "loaded_at":
                months = [r["month"] for r in rows]
                curr = months[0] if len(months) >= 1 else None
                prev = months[1] if len(months) >= 2 else None
                return "loaded_at", prev, curr

        # Fallback to publication_date for rich historical / temporal comparison
        cursor.execute(
            """
            SELECT to_char(date_trunc('month', publication_date), 'YYYY-MM') AS month,
                   count(*) AS count
            FROM final_publications
            WHERE publication_date IS NOT NULL
            GROUP BY 1
            ORDER BY 1 DESC
            LIMIT 2
            """
        )
        rows = cursor.fetchall()
        months = [r["month"] for r in rows]
        curr = months[0] if len(months) >= 1 else None
        prev = months[1] if len(months) >= 2 else None
        return "publication_date", prev, curr


def get_period_dates(month: str) -> tuple[str, str]:
    """Return start and end dates for a YYYY-MM month string."""
    parts = month.split("-")
    year = int(parts[0])
    m = int(parts[1])
    if m == 12:
        next_month = f"{year + 1:04d}-01-01"
    else:
        next_month = f"{year:04d}-{m + 1:02d}-01"
    return f"{month}-01", next_month


def query_period_stats(connection: Any, date_field: str, month: str) -> dict[str, Any]:
    """Query single-pass aggregated metrics for a specific month period."""
    start_date, end_date = get_period_dates(month)
    sql = f"""
        SELECT 
            count(*) as total,
            count(*) filter (where ai_classification_label = 'AI' or classifier_decision = 'AI') as ai_count,
            count(*) filter (where ai_classification_label = 'non-AI' or classifier_decision = 'non-AI') as non_ai_count,
            count(*) filter (where ai_classification_label = 'review' or classifier_decision = 'review') as review_count,
            round(avg(NULLIF(regexp_replace(classifier_probability, '[^0-9.]', '', 'g'), '')::numeric), 4) as avg_p_ai,
            percentile_cont(0.5) within group (order by NULLIF(regexp_replace(classifier_probability, '[^0-9.]', '', 'g'), '')::numeric) as median_p_ai,
            round(stddev(NULLIF(regexp_replace(classifier_probability, '[^0-9.]', '', 'g'), '')::numeric), 4) as std_p_ai,
            count(*) filter (where NULLIF(regexp_replace(classifier_probability, '[^0-9.]', '', 'g'), '')::numeric < 0.35) as p_low,
            count(*) filter (where NULLIF(regexp_replace(classifier_probability, '[^0-9.]', '', 'g'), '')::numeric >= 0.35 and NULLIF(regexp_replace(classifier_probability, '[^0-9.]', '', 'g'), '')::numeric < 0.65) as p_mid,
            count(*) filter (where NULLIF(regexp_replace(classifier_probability, '[^0-9.]', '', 'g'), '')::numeric >= 0.65) as p_high,
            round(avg(cardinality(regexp_split_to_array(btrim(title), '\\s+'))), 1) as avg_title_words,
            round(avg(cardinality(regexp_split_to_array(btrim(abstract), '\\s+'))), 1) as avg_abstract_words,
            count(*) filter (where NULLIF(btrim(coalesce(abstract, '')), '') is not null) as with_abstract_count,
            count(*) filter (where NULLIF(btrim(coalesce(abstract, '')), '') is null) as missing_abstract,
            count(*) filter (where NULLIF(btrim(coalesce(doi, '')), '') is null) as missing_doi,
            count(*) filter (where NULLIF(btrim(coalesce(sri_lankan_institutions, '')), '') is null) as missing_inst,
            count(*) filter (where source_dataset ilike '%%openalex%%') as openalex_count,
            count(*) filter (where source_dataset ilike '%%crossref%%') as crossref_count,
            count(*) filter (where source_dataset ilike '%%sljol%%') as sljol_count,
            count(*) filter (where source_dataset ilike '%%repositor%%') as repo_count
        FROM final_publications
        WHERE {date_field} >= %s AND {date_field} < %s
    """
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(sql, [start_date, end_date])
        row = cursor.fetchone() or {}

    # Query human decisions and disagreements for this period
    review_sql = f"""
        SELECT 
            count(*) as review_rows,
            count(*) filter (where r.review_status = 'auto_accepted') as auto_accepted,
            count(*) filter (where r.review_status = 'human_rejected') as human_rejected,
            count(*) filter (where r.review_status = 'pending_review') as pending_review,
            count(*) filter (where r.review_status = 'human_accepted') as human_accepted,
            count(*) filter (where r.decision_timestamp is not null) as total_human_decisions,
            count(*) filter (where r.decision_timestamp is not null and r.review_status = 'human_rejected' and r.original_ai_label = 'AI') as fp_overturns,
            count(*) filter (where r.decision_timestamp is not null and r.review_status = 'human_accepted' and r.original_ai_label != 'AI') as fn_overturns
        FROM final_publications p
        JOIN ai_review_records r ON p.publication_key = r.publication_key
        WHERE p.{date_field} >= %s AND p.{date_field} < %s
    """
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(review_sql, [start_date, end_date])
        review_row = cursor.fetchone() or {}

    # Query top institutions for this period
    inst_sql = f"""
        SELECT 
            btrim(inst) as institution,
            count(*) as count
        FROM final_publications,
             unnest(string_to_array(sri_lankan_institutions, ';')) as inst
        WHERE {date_field} >= %s AND {date_field} < %s
          AND btrim(inst) != ''
        GROUP BY 1
        ORDER BY count DESC
        LIMIT 5
    """
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(inst_sql, [start_date, end_date])
        inst_rows = cursor.fetchall() or []

    return {
        "month": month,
        "stats": row,
        "review_stats": review_row,
        "institutions": inst_rows,
    }


def compute_ml_monitoring(
    connection: Any,
    date_basis: str = "auto",
    custom_prev_month: str | None = None,
    custom_curr_month: str | None = None,
) -> dict[str, Any]:
    """Compute the full 7-dimension Real ML Monitoring report."""
    date_field, auto_prev, auto_curr = determine_date_basis_and_periods(connection, date_basis)
    prev_month = custom_prev_month or auto_prev
    curr_month = custom_curr_month or auto_curr

    if not curr_month:
        return {
            "status": "insufficient_data",
            "message": "No publication or ingestion data found to compute drift monitoring.",
            "overall_alert": False,
            "alerts": [],
        }

    curr_data = query_period_stats(connection, date_field, curr_month)
    prev_data = query_period_stats(connection, date_field, prev_month) if prev_month else None

    alerts: list[dict[str, Any]] = []

    # -------------------------------------------------------------
    # 1. Prediction Drift
    # -------------------------------------------------------------
    c_tot = int(curr_data["stats"].get("total") or 0)
    p_tot = int(prev_data["stats"].get("total") or 0) if prev_data else 0

    c_ai_pct = percent(curr_data["stats"].get("ai_count"), c_tot)
    p_ai_pct = percent(prev_data["stats"].get("ai_count"), p_tot) if prev_data else 0.0
    ai_delta = round(c_ai_pct - p_ai_pct, 2) if prev_data else 0.0

    c_non_ai_pct = percent(curr_data["stats"].get("non_ai_count"), c_tot)
    p_non_ai_pct = percent(prev_data["stats"].get("non_ai_count"), p_tot) if prev_data else 0.0

    c_rev_pct = percent(curr_data["stats"].get("review_count"), c_tot)
    p_rev_pct = percent(prev_data["stats"].get("review_count"), p_tot) if prev_data else 0.0

    psi_score = 0.0
    if prev_data and p_tot > 0 and c_tot > 0:
        actual_dist = {"AI": c_ai_pct / 100.0, "NON_AI": c_non_ai_pct / 100.0, "REVIEW": c_rev_pct / 100.0}
        expected_dist = {"AI": p_ai_pct / 100.0, "NON_AI": p_non_ai_pct / 100.0, "REVIEW": p_rev_pct / 100.0}
        psi_score = compute_psi(actual_dist, expected_dist)

    pred_alert = prev_data is not None and (abs(ai_delta) >= PREDICTION_RATE_ALERT_POINTS or psi_score >= PSI_ALERT_THRESHOLD)
    pred_reasons: list[str] = []
    if pred_alert:
        msg = f"Prediction Drift: AI classification rate shifted by {ai_delta:+.1f} points ({p_ai_pct}% -> {c_ai_pct}%, PSI={psi_score}) ⚠"
        pred_reasons.append(msg)
        alerts.append({"dimension": "prediction", "severity": "warning", "message": msg})

    prediction_drift = {
        "previous_total": p_tot,
        "current_total": c_tot,
        "previous_ai_rate": p_ai_pct,
        "current_ai_rate": c_ai_pct,
        "ai_rate_delta_points": ai_delta,
        "previous_non_ai_rate": p_non_ai_pct,
        "current_non_ai_rate": c_non_ai_pct,
        "previous_review_rate": p_rev_pct,
        "current_review_rate": c_rev_pct,
        "psi_score": psi_score,
        "alert": pred_alert,
        "alert_reasons": pred_reasons,
    }

    # -------------------------------------------------------------
    # 2. Confidence Distribution Drift (P(AI))
    # -------------------------------------------------------------
    c_mean_p = float(curr_data["stats"].get("avg_p_ai") or 0.0)
    p_mean_p = float(prev_data["stats"].get("avg_p_ai") or 0.0) if prev_data else 0.0
    delta_mean_p = round(c_mean_p - p_mean_p, 4) if prev_data else 0.0

    c_med_p = float(curr_data["stats"].get("median_p_ai") or 0.0)
    p_med_p = float(prev_data["stats"].get("median_p_ai") or 0.0) if prev_data else 0.0

    c_std_p = float(curr_data["stats"].get("std_p_ai") or 0.0)
    p_std_p = float(prev_data["stats"].get("std_p_ai") or 0.0) if prev_data else 0.0

    c_high_pct = percent(curr_data["stats"].get("p_high"), c_tot)
    p_high_pct = percent(prev_data["stats"].get("p_high"), p_tot) if prev_data else 0.0
    delta_high_pct = round(c_high_pct - p_high_pct, 2) if prev_data else 0.0

    conf_alert = prev_data is not None and (abs(delta_mean_p) >= CONFIDENCE_MEAN_DELTA_ALERT or abs(delta_high_pct) >= CONFIDENCE_HIGH_BIN_ALERT_POINTS)
    conf_reasons: list[str] = []
    if conf_alert:
        msg = f"Confidence Drift: Mean P(AI) shifted from {p_mean_p:.2f} to {c_mean_p:.2f} ({delta_mean_p:+.2f}) ⚠"
        conf_reasons.append(msg)
        alerts.append({"dimension": "confidence", "severity": "warning", "message": msg})

    confidence_drift = {
        "previous_mean_p_ai": round(p_mean_p, 4),
        "current_mean_p_ai": round(c_mean_p, 4),
        "mean_p_ai_delta": delta_mean_p,
        "previous_median_p_ai": round(p_med_p, 4),
        "current_median_p_ai": round(c_med_p, 4),
        "previous_std_p_ai": round(p_std_p, 4),
        "current_std_p_ai": round(c_std_p, 4),
        "bins": {
            "low": {
                "previous_pct": percent(prev_data["stats"].get("p_low"), p_tot) if prev_data else 0.0,
                "current_pct": percent(curr_data["stats"].get("p_low"), c_tot),
            },
            "medium": {
                "previous_pct": percent(prev_data["stats"].get("p_mid"), p_tot) if prev_data else 0.0,
                "current_pct": percent(curr_data["stats"].get("p_mid"), c_tot),
            },
            "high": {
                "previous_pct": p_high_pct,
                "current_pct": c_high_pct,
                "delta_points": delta_high_pct,
            },
        },
        "alert": conf_alert,
        "alert_reasons": conf_reasons,
    }

    # -------------------------------------------------------------
    # 3. Feature Drift
    # -------------------------------------------------------------
    c_title_w = float(curr_data["stats"].get("avg_title_words") or 0.0)
    p_title_w = float(prev_data["stats"].get("avg_title_words") or 0.0) if prev_data else 0.0
    title_w_shift = round(((c_title_w - p_title_w) / p_title_w) * 100, 1) if p_title_w > 0 else 0.0

    c_abs_w = float(curr_data["stats"].get("avg_abstract_words") or 0.0)
    p_abs_w = float(prev_data["stats"].get("avg_abstract_words") or 0.0) if prev_data else 0.0
    abs_w_shift = round(((c_abs_w - p_abs_w) / p_abs_w) * 100, 1) if p_abs_w > 0 else 0.0

    c_abs_pres = percent(curr_data["stats"].get("with_abstract_count"), c_tot)
    p_abs_pres = percent(prev_data["stats"].get("with_abstract_count"), p_tot) if prev_data else 0.0
    abs_pres_delta = round(c_abs_pres - p_abs_pres, 2) if prev_data else 0.0

    feat_alert = prev_data is not None and (
        abs(title_w_shift) >= FEATURE_DRIFT_PCT_THRESHOLD
        or (p_abs_w > 0 and abs(abs_w_shift) >= FEATURE_DRIFT_PCT_THRESHOLD)
        or (abs_pres_delta <= -ABSTRACT_PRESENCE_DROP_ALERT_POINTS)
    )
    feat_reasons: list[str] = []
    if feat_alert:
        if abs_pres_delta <= -ABSTRACT_PRESENCE_DROP_ALERT_POINTS:
            msg = f"Feature Drift: Abstract presence dropped by {abs(abs_pres_delta):.1f} points ({p_abs_pres}% -> {c_abs_pres}%) ⚠"
        else:
            msg = f"Feature Drift: Average word lengths shifted significantly (Title: {title_w_shift:+.1f}%, Abstract: {abs_w_shift:+.1f}%) ⚠"
        feat_reasons.append(msg)
        alerts.append({"dimension": "feature", "severity": "warning", "message": msg})

    feature_drift = {
        "previous_avg_title_words": round(p_title_w, 1),
        "current_avg_title_words": round(c_title_w, 1),
        "title_words_shift_pct": title_w_shift,
        "previous_avg_abstract_words": round(p_abs_w, 1),
        "current_avg_abstract_words": round(c_abs_w, 1),
        "abstract_words_shift_pct": abs_w_shift,
        "previous_abstract_presence_pct": p_abs_pres,
        "current_abstract_presence_pct": c_abs_pres,
        "abstract_presence_delta_points": abs_pres_delta,
        "alert": feat_alert,
        "alert_reasons": feat_reasons,
    }

    # -------------------------------------------------------------
    # 4. Human Disagreement Drift
    # -------------------------------------------------------------
    c_decisions = int(curr_data["review_stats"].get("total_human_decisions") or 0)
    p_decisions = int(prev_data["review_stats"].get("total_human_decisions") or 0) if prev_data else 0

    c_fp = int(curr_data["review_stats"].get("fp_overturns") or 0)
    c_fn = int(curr_data["review_stats"].get("fn_overturns") or 0)
    p_fp = int(prev_data["review_stats"].get("fp_overturns") or 0) if prev_data else 0
    p_fn = int(prev_data["review_stats"].get("fn_overturns") or 0) if prev_data else 0

    c_overturns = c_fp + c_fn
    p_overturns = p_fp + p_fn

    c_disagree_rate = percent(c_overturns, c_decisions)
    p_disagree_rate = percent(p_overturns, p_decisions) if prev_data else 0.0
    disagree_delta = round(c_disagree_rate - p_disagree_rate, 2) if prev_data else 0.0

    human_alert = (c_decisions >= 5 and c_disagree_rate >= HUMAN_DISAGREEMENT_ALERT_RATE) or (
        prev_data is not None and p_decisions >= 5 and disagree_delta >= HUMAN_DISAGREEMENT_DELTA_POINTS
    )
    human_reasons: list[str] = []
    if human_alert:
        msg = f"Human Disagreement Drift: Reviewer overturn rate is {c_disagree_rate:.1f}% ({c_overturns}/{c_decisions} decisions overturned) ⚠"
        human_reasons.append(msg)
        alerts.append({"dimension": "human_disagreement", "severity": "warning", "message": msg})

    human_drift = {
        "previous_human_decisions": p_decisions,
        "current_human_decisions": c_decisions,
        "previous_disagreement_rate": p_disagree_rate,
        "current_disagreement_rate": c_disagree_rate,
        "disagreement_delta_points": disagree_delta,
        "current_fp_overturns": c_fp,
        "current_fn_overturns": c_fn,
        "alert": human_alert,
        "alert_reasons": human_reasons,
    }

    # -------------------------------------------------------------
    # 5. Source Drift (OpenAlex, Crossref, SLJOL, Repositories)
    # -------------------------------------------------------------
    source_names = [
        ("OpenAlex", "openalex_count"),
        ("Crossref", "crossref_count"),
        ("SLJOL", "sljol_count"),
        ("Repositories", "repo_count"),
    ]
    sources_summary = []
    max_source_delta = 0.0
    source_alert = False
    source_reasons: list[str] = []

    for name, key in source_names:
        c_pct = percent(curr_data["stats"].get(key), c_tot)
        p_pct = percent(prev_data["stats"].get(key), p_tot) if prev_data else 0.0
        delta = round(c_pct - p_pct, 2) if prev_data else 0.0
        if prev_data and abs(delta) > max_source_delta:
            max_source_delta = abs(delta)

        src_flag = prev_data is not None and abs(delta) >= SOURCE_DRIFT_ALERT_POINTS
        if src_flag:
            source_alert = True
            msg = f"Source Drift: {name} contribution shifted by {delta:+.1f} points ({p_pct}% -> {c_pct}%) ⚠"
            source_reasons.append(msg)
            alerts.append({"dimension": "source", "severity": "warning", "message": msg})

        sources_summary.append({
            "source": name,
            "name": name,
            "previous_pct": p_pct,
            "current_pct": c_pct,
            "delta_points": delta,
            "alert": src_flag,
        })

    source_drift = {
        "sources": sources_summary,
        "max_source_shift_points": round(max_source_delta, 2),
        "alert": source_alert,
        "alert_reasons": source_reasons,
    }

    # -------------------------------------------------------------
    # 6. Institution Distribution Drift
    # -------------------------------------------------------------
    c_inst_list = curr_data.get("institutions") or []
    p_inst_list = prev_data.get("institutions") or [] if prev_data else []

    p_inst_map = {row["institution"]: row["count"] for row in p_inst_list}
    c_inst_map = {row["institution"]: row["count"] for row in c_inst_list}

    top_institutions_summary = []
    inst_alert = False
    inst_reasons: list[str] = []

    for item in c_inst_list:
        inst_name = item["institution"]
        c_share = percent(item["count"], c_tot)
        p_share = percent(p_inst_map.get(inst_name, 0), p_tot) if prev_data else 0.0
        delta = round(c_share - p_share, 2) if prev_data else 0.0
        inst_flag = prev_data is not None and abs(delta) >= INSTITUTION_DRIFT_ALERT_POINTS
        if inst_flag:
            inst_alert = True
            msg = f"Institution Drift: '{inst_name}' share shifted by {delta:+.1f} points ({p_share}% -> {c_share}%) ⚠"
            inst_reasons.append(msg)
            alerts.append({"dimension": "institution", "severity": "warning", "message": msg})

        top_institutions_summary.append({
            "institution": inst_name,
            "current_count": item["count"],
            "current_share_pct": c_share,
            "previous_share_pct": p_share,
            "delta_points": delta,
            "alert": inst_flag,
        })

    # Top-3 concentration
    c_top3_count = sum(r["count"] for r in c_inst_list[:3])
    c_top3_conc = percent(c_top3_count, c_tot)
    p_top3_count = sum(r["count"] for r in p_inst_list[:3])
    p_top3_conc = percent(p_top3_count, p_tot) if prev_data else 0.0

    if c_top3_conc >= INSTITUTION_CONCENTRATION_ALERT_PCT and c_tot >= 10:
        inst_alert = True
        msg = f"Institution Drift: Top 3 institutions represent {c_top3_conc:.1f}% of all publications (high concentration) ⚠"
        inst_reasons.append(msg)
        alerts.append({"dimension": "institution", "severity": "warning", "message": msg})

    institution_drift = {
        "top_institutions": top_institutions_summary,
        "top3_concentration_current_pct": c_top3_conc,
        "top3_concentration_previous_pct": p_top3_conc,
        "alert": inst_alert,
        "alert_reasons": inst_reasons,
    }

    # -------------------------------------------------------------
    # 7. Missing-Data Drift
    # -------------------------------------------------------------
    missing_items = [
        ("Missing Abstract", "missing_abstract"),
        ("Missing DOI", "missing_doi"),
        ("Missing Institution", "missing_inst"),
    ]
    missing_data_summary = {}
    missing_alert = False
    missing_reasons: list[str] = []

    for label, key in missing_items:
        c_pct = percent(curr_data["stats"].get(key), c_tot)
        p_pct = percent(prev_data["stats"].get(key), p_tot) if prev_data else 0.0
        delta = round(c_pct - p_pct, 2) if prev_data else 0.0

        item_alert = prev_data is not None and delta >= MISSING_DATA_INCREASE_ALERT_POINTS
        if item_alert:
            missing_alert = True
            msg = f"Missing-Data Drift: {label} rate surged by {delta:+.1f} points ({p_pct}% -> {c_pct}%) ⚠"
            missing_reasons.append(msg)
            alerts.append({"dimension": "missing_data", "severity": "warning", "message": msg})

        missing_data_summary[key] = {
            "label": label,
            "previous_pct": p_pct,
            "current_pct": c_pct,
            "delta_points": delta,
            "alert": item_alert,
        }

    missing_data_drift = {
        "fields": missing_data_summary,
        "alert": missing_alert,
        "alert_reasons": missing_reasons,
    }

    # -------------------------------------------------------------
    # Rollup Summary
    # -------------------------------------------------------------
    return {
        "status": "success",
        "date_basis": date_field,
        "previous_period": prev_month,
        "current_period": curr_month,
        "overall_alert": len(alerts) > 0,
        "active_alerts_count": len(alerts),
        "active_alerts": alerts,
        "prediction_drift": prediction_drift,
        "confidence_drift": confidence_drift,
        "feature_drift": feature_drift,
        "human_disagreement_drift": human_drift,
        "source_drift": source_drift,
        "institution_drift": institution_drift,
        "missing_data_drift": missing_data_drift,
    }
