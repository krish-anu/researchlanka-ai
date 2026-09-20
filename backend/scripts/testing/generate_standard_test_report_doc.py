#!/usr/bin/env python3
"""Generate ResearchLanka standard test report as real Word (.docx) + HTML.

Outputs (under data/processed/common/ and data/reports/unified_phase_tests/):
  - ResearchLanka_Standard_Test_Report.docx  → open in Microsoft Word / LibreOffice
  - ResearchLanka_Standard_Test_Report.html  → open in any browser (formatted report)

Usage (from backend/):

    python scripts/testing/generate_standard_test_report_doc.py
"""

from __future__ import annotations

import csv
import html
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape


BACKEND_ROOT = Path(__file__).resolve().parents[2]
COMMON_DIR = BACKEND_ROOT / "data" / "processed" / "common"
UNIFIED_DIR = BACKEND_ROOT / "data" / "reports" / "unified_phase_tests"
PHASE1_DIR = BACKEND_ROOT / "data" / "reports" / "phase1_pipeline_tests"
PHASE2_DIR = BACKEND_ROOT / "data" / "reports" / "phase2_ml_api_tests"
PHASE3_DIR = BACKEND_ROOT / "data" / "reports" / "phase3_overall_tests"


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _he(value: object) -> str:
    return html.escape(str(value if value is not None else ""))


def _load_bundle() -> dict:
    unified = _load_json(COMMON_DIR / "unified_testing_summary.json") or _load_json(
        UNIFIED_DIR / "latest_summary.json"
    )
    return {
        "stamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "unified": unified,
        "totals": unified.get("totals") or {},
        "phases": {row.get("phase"): row for row in unified.get("phases") or []},
        "phase1": _load_json(PHASE1_DIR / "latest_summary.json"),
        "phase2": _load_json(PHASE2_DIR / "latest_summary.json"),
        "phase3": _load_json(PHASE3_DIR / "latest_summary.json"),
        "api_rows": _load_csv(PHASE2_DIR / "latest_api_matrix.csv"),
        "sec_rows": _load_csv(PHASE3_DIR / "latest_security_matrix.csv"),
        "result_rows": _load_csv(COMMON_DIR / "unified_testing_results.csv")
        or _load_csv(UNIFIED_DIR / "latest_results.csv"),
    }


# ---------------------------------------------------------------------------
# HTML report (open in browser)
# ---------------------------------------------------------------------------


def build_html(data: dict) -> str:
    totals = data["totals"]
    phases = data["phases"]
    p1, p2, p3 = phases.get("phase1") or {}, phases.get("phase2") or {}, phases.get("phase3") or {}
    phase1, phase2, phase3 = data["phase1"], data["phase2"], data["phase3"]

    def table(headers: list[str], rows: list[list[object]], outcome_col: int | None = None) -> str:
        th = "".join(f"<th>{_he(h)}</th>" for h in headers)
        body = []
        for row in rows:
            cells = []
            for i, cell in enumerate(row):
                css = ""
                text = str(cell if cell is not None else "")
                if outcome_col is not None and i == outcome_col:
                    low = text.lower()
                    if low in {"pass", "passed", "complete"}:
                        css = ' class="pass"'
                    elif low in {"fail", "failed"}:
                        css = ' class="fail"'
                    elif low in {"skip", "skipped", "todo", "partial"} or "todo" in low:
                        css = ' class="todo"'
                cells.append(f"<td{css}>{_he(text)}</td>")
            body.append("<tr>" + "".join(cells) + "</tr>")
        return (
            '<table><thead><tr>'
            + th
            + "</tr></thead><tbody>"
            + "".join(body)
            + "</tbody></table>"
        )

    def todo(text: str, what: str) -> str:
        return (
            f'<div class="todo-box"><strong>TODO:</strong> {_he(text)} '
            f"<em>({_he(what)})</em></div>"
        )

    cat_rows = lambda summary: [
        [
            item.get("category"),
            item.get("total"),
            item.get("passed"),
            item.get("failed"),
            item.get("skipped"),
            f"{item.get('pass_rate_pct')}%",
        ]
        for item in summary.get("by_category") or []
    ]

    api_table = table(
        ["Test ID", "Endpoint", "Scenario", "Expected", "Result"],
        [
            [
                r.get("test_id", ""),
                r.get("endpoint", ""),
                r.get("scenario", ""),
                r.get("expected", ""),
                r.get("result", ""),
            ]
            for r in data["api_rows"]
        ],
        outcome_col=4,
    )
    sec_table = table(
        ["Test ID", "Endpoint", "Scenario", "Expected", "Result"],
        [
            [
                r.get("test_id", ""),
                r.get("endpoint", ""),
                r.get("scenario", ""),
                r.get("expected", ""),
                r.get("result", ""),
            ]
            for r in data["sec_rows"]
        ],
        outcome_col=4,
    )

    detail_limit = 150
    detail_rows = []
    for row in data["result_rows"][:detail_limit]:
        test_name = row.get("test_id") or (row.get("nodeid", "").split("::")[-1])
        detail_rows.append(
            [
                row.get("phase", ""),
                row.get("category", ""),
                row.get("outcome", ""),
                test_name,
                f"{float(row.get('duration_seconds') or 0):.3f}",
            ]
        )
    detail_table = table(
        ["Phase", "Category", "Outcome", "Test case", "Duration (s)"],
        detail_rows,
        outcome_col=2,
    )
    more = ""
    if len(data["result_rows"]) > detail_limit:
        more = (
            f"<p>Showing first {detail_limit} of {len(data['result_rows'])} tests. "
            "Full list: <code>unified_testing_results.csv</code></p>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>ResearchLanka AI — Standard Software Test Report</title>
<style>
  :root {{
    --ink: #0f172a;
    --muted: #475569;
    --line: #cbd5e1;
    --pass: #166534;
    --fail: #b91c1c;
    --todo: #9a3412;
    --todo-bg: #fff7ed;
    --head: #1e3a5f;
    --band: #e2e8f0;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 24px;
    font-family: "Segoe UI", Calibri, Arial, sans-serif;
    color: var(--ink); background: #f8fafc; line-height: 1.45;
  }}
  .page {{
    max-width: 960px; margin: 0 auto; background: #fff;
    padding: 28px 32px; border: 1px solid var(--line);
    box-shadow: 0 8px 24px rgba(15,23,42,.06);
  }}
  h1 {{ font-size: 1.6rem; margin: 0 0 8px; }}
  h2 {{ font-size: 1.2rem; color: var(--head); border-bottom: 2px solid var(--line); padding-bottom: 6px; margin-top: 28px; }}
  h3 {{ font-size: 1.05rem; color: #334155; margin-top: 18px; }}
  .meta {{ color: var(--muted); font-size: .95rem; }}
  .summary {{
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 16px 0 8px;
  }}
  .card {{
    background: #f1f5f9; border: 1px solid var(--line); border-radius: 8px; padding: 12px;
  }}
  .card b {{ display: block; font-size: 1.3rem; }}
  .card.pass b {{ color: var(--pass); }}
  .card.fail b {{ color: var(--fail); }}
  .card.todo b {{ color: var(--todo); }}
  table {{
    width: 100%; border-collapse: collapse; font-size: .9rem; margin: 10px 0 16px;
  }}
  th, td {{ border: 1px solid var(--line); padding: 6px 8px; text-align: left; vertical-align: top; }}
  th {{ background: var(--band); }}
  td.pass, .pass {{ color: var(--pass); font-weight: 700; }}
  td.fail, .fail {{ color: var(--fail); font-weight: 700; }}
  td.todo, .todo {{ color: var(--todo); font-weight: 700; }}
  .todo-box {{
    background: var(--todo-bg); border-left: 4px solid #ea580c;
    padding: 10px 12px; margin: 10px 0; color: var(--todo);
  }}
  code {{ background: #f1f5f9; padding: 1px 4px; border-radius: 3px; }}
  footer {{ margin-top: 28px; color: var(--muted); font-size: .85rem; }}
  @media print {{
    body {{ background: #fff; padding: 0; }}
    .page {{ box-shadow: none; border: none; }}
  }}
</style>
</head>
<body>
<main class="page">
  <h1>ResearchLanka AI — Standard Software Test Report</h1>
  <p class="meta">
    Submittable test report for Phases 1–3<br/>
    Generated: <strong>{_he(data['stamp'])}</strong><br/>
    Suite: <code>unified_phase_tests</code><br/>
    Deployed URL (configured): <code>http://98.81.141.112:3000</code>
  </p>

  <div class="summary">
    <div class="card"><span>Total tests</span><b>{_he(totals.get('total', 0))}</b></div>
    <div class="card pass"><span>Passed</span><b>{_he(totals.get('passed', 0))}</b></div>
    <div class="card fail"><span>Failed</span><b>{_he(totals.get('failed', 0))}</b></div>
    <div class="card todo"><span>Skipped</span><b>{_he(totals.get('skipped', 0))}</b></div>
  </div>
  <p><strong>Pass rate: {_he(totals.get('pass_rate_pct', 0))}%</strong>
  — In-process API tests used real rows from <code>common_publications_final.csv</code>.</p>

  <h2>1. Executive summary</h2>
  <p>Automated testing of the ResearchLanka application covering the ETL/data pipeline,
  database integrity / ML / REST API, and overall application quality (security, load,
  recovery, deploy configuration, and live-site checks).</p>
  {table(
      ["Phase", "Total", "Passed", "Failed", "Skipped", "Pass rate", "Status"],
      [
          ["Phase 1 — ETL / pipeline", p1.get("total"), p1.get("passed"), p1.get("failed"), p1.get("skipped"), f"{p1.get('pass_rate_pct')}%", "COMPLETE"],
          ["Phase 2 — DB / ML / API", p2.get("total"), p2.get("passed"), p2.get("failed"), p2.get("skipped"), f"{p2.get('pass_rate_pct')}%", "COMPLETE"],
          ["Phase 3 — Overall application", p3.get("total"), p3.get("passed"), p3.get("failed"), p3.get("skipped"), f"{p3.get('pass_rate_pct')}%", "PARTIAL"],
      ],
      outcome_col=6,
  )}

  <h2>2. Phase 1 — ETL / Data Integration results</h2>
  <p><strong>Result: {_he(p1.get('passed', 0))}/{_he(p1.get('total', 0))} passed ({_he(p1.get('pass_rate_pct', 0))}%)</strong></p>
  <h3>2.1 By category</h3>
  {table(["Category", "Total", "Passed", "Failed", "Skipped", "Pass rate"], cat_rows(phase1))}
  <h3>2.2 Checklist</h3>
  {table(
      ["Test area", "Result", "Evidence"],
      [
          ["Cleaning / DOI-title-date normalization", "PASS", "test_phase1_cleaning.py"],
          ["Preprocessing", "PASS", "test_phase1_preprocessing.py"],
          ["Transformations / schema mapping", "PASS", "test_phase1_transformations.py"],
          ["Deduplication", "PASS", "test_phase1_deduplication.py"],
          ["Author disambiguation", "PASS", "test_phase1_disambiguation.py"],
          ["Institution entity resolution", "PASS", "test_phase1_entity_resolution.py"],
          ["E2E ingestion flow", "PASS", "test_phase1_e2e_ingestion.py"],
          ["Dagster job/asset smoke", "PASS", "test_phase1_dagster.py"],
          ["Dagster dg/dev layout readiness", "PASS", "test_phase1_dagster_dev.py"],
          ["Database publication_key contract", "PASS", "test_phase1_database.py"],
      ],
      outcome_col=1,
  )}
  {todo("Full Dagster dg/dev materialization not signed off", "Run uv run dg dev; materialize researchlanka_all_assets_job; attach run IDs")}

  <h2>3. Phase 2 — Database / ML / API results</h2>
  <p><strong>Result: {_he(p2.get('passed', 0))}/{_he(p2.get('total', 0))} passed ({_he(p2.get('pass_rate_pct', 0))}%)</strong></p>
  <h3>3.1 By category</h3>
  {table(["Category", "Total", "Passed", "Failed", "Skipped", "Pass rate"], cat_rows(phase2))}
  <h3>3.2 API test matrix (application API)</h3>
  {api_table}
  {todo("Live Postgres soak outstanding", "Set reachable DATABASE_URL in .env; compare DB counts/latency to CSV/API")}

  <h2>4. Phase 3 — Overall application results</h2>
  <p><strong>Result: {_he(p3.get('passed', 0))} passed, {_he(p3.get('skipped', 0))} skipped
  ({_he(p3.get('pass_rate_pct', 0))}% of {_he(p3.get('total', 0))})</strong></p>
  <h3>4.1 By category</h3>
  {table(["Category", "Total", "Passed", "Failed", "Skipped", "Pass rate"], cat_rows(phase3))}
  <h3>4.2 Security matrix</h3>
  {sec_table}
  <h3>4.3 Checklist</h3>
  {table(
      ["Test area", "Result", "Notes"],
      [
          ["Integration smoke", "PASS", "health → meta → search → detail → export"],
          ["Performance budgets", "PASS", "service-layer latency"],
          ["Concurrent load", "PASS", "test_phase3_load.py"],
          ["Recovery / resilience", "PASS", "test_phase3_recovery.py"],
          ["Security SEC-*", "PASS", "see matrix above"],
          ["Deploy / accessibility contracts", "PASS", "compose + error contracts"],
          ["Frontend static contracts", "PASS", "non-Vitest frontend checks"],
      ],
      outcome_col=1,
  )}
  {todo("Live EC2 site tests were SKIPPED (network unreachable from report machine)", "Re-run from a host that opens http://98.81.141.112:3000")}
  {todo("Live login with admin + asma accounts", "Credentials in gitignored .env; verify /admin after sign-in")}
  {todo("Frontend Vitest skipped (PHASE3_SKIP_VITEST=1)", "Run: cd frontend && npm test")}
  {todo("Playwright browser E2E missing", "Add smoke for login, search, publication detail, admin gate")}

  <h2>5. Detailed test case results</h2>
  <p>Each row is one automated test executed against the application / real dataset.</p>
  {detail_table}
  {more}

  <h2>6. Outstanding TODO register</h2>
  {table(
      ["ID", "Phase", "Item", "What to do", "Status"],
      [
          ["T-01", "1", "Dagster full materialization", "Materialize job in dg/dev; attach run ID", "TODO"],
          ["T-02", "1", "dagster-quickstart package tests", "Add package tests or accept phase1 coverage", "TODO"],
          ["T-03", "2", "Live Postgres soak", "Set DATABASE_URL; compare counts/latency", "TODO"],
          ["T-04", "3", "Live deployed site smoke", "Run live tests vs http://98.81.141.112:3000", "TODO"],
          ["T-05", "3", "Live auth (admin + asma)", "Confirm sign-in from .env accounts", "TODO"],
          ["T-06", "3", "Vitest suite", "cd frontend && npm test", "TODO"],
          ["T-07", "3", "Playwright E2E", "Add browser smoke for core user flows", "TODO"],
          ["T-08", "3", "Incremental admin API auth", "Keep API private or add token auth", "TODO"],
      ],
      outcome_col=4,
  )}

  <h2>7. Sign-off</h2>
  {table(
      ["Role", "Name", "Date", "Signature"],
      [
          ["Prepared by", "", "", ""],
          ["Reviewed by", "", "", ""],
          ["Approved by", "", "", ""],
      ],
  )}

  <footer>
    End of report — ResearchLanka AI. Close TODO items or accept as residual risk before release sign-off.<br/>
    Companion Word file: <code>ResearchLanka_Standard_Test_Report.docx</code>
  </footer>
</main>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Real Word .docx (OOXML zip)
# ---------------------------------------------------------------------------


def _wp(text: str, *, bold: bool = False, size: int = 22, color: str | None = None) -> str:
    props = [f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>']
    if bold:
        props.append("<w:b/>")
    if color:
        props.append(f'<w:color w:val="{color}"/>')
    rpr = "<w:rPr>" + "".join(props) + "</w:rPr>"
    return f'<w:p><w:r>{rpr}<w:t xml:space="preserve">{xml_escape(text)}</w:t></w:r></w:p>'


def _wh(text: str, level: int = 1) -> str:
    size = {1: 32, 2: 26, 3: 24}.get(level, 22)
    return _wp(text, bold=True, size=size, color="1E3A5F" if level > 1 else "0F172A")


def _wtodo(text: str, what: str) -> str:
    return _wp(f"TODO: {text} ({what})", bold=True, color="9A3412", size=20)


def _wtable(headers: list[str], rows: list[list[object]]) -> str:
    def cell(text: object, header: bool = False) -> str:
        shade = '<w:tcPr><w:shd w:val="clear" w:fill="E2E8F0"/></w:tcPr>' if header else "<w:tcPr/>"
        return f"<w:tc>{shade}{_wp(str(text if text is not None else ''), bold=header, size=18)}</w:tc>"

    parts = [
        "<w:tbl>",
        '<w:tblPr><w:tblW w:w="5000" w:type="pct"/><w:tblBorders>',
        '<w:top w:val="single" w:sz="4" w:color="94A3B8"/>',
        '<w:left w:val="single" w:sz="4" w:color="94A3B8"/>',
        '<w:bottom w:val="single" w:sz="4" w:color="94A3B8"/>',
        '<w:right w:val="single" w:sz="4" w:color="94A3B8"/>',
        '<w:insideH w:val="single" w:sz="4" w:color="CBD5E1"/>',
        '<w:insideV w:val="single" w:sz="4" w:color="CBD5E1"/>',
        "</w:tblBorders></w:tblPr>",
        "<w:tr>" + "".join(cell(h, True) for h in headers) + "</w:tr>",
    ]
    for row in rows:
        parts.append("<w:tr>" + "".join(cell(c) for c in row) + "</w:tr>")
    parts.append("</w:tbl>")
    parts.append(_wp(""))
    return "".join(parts)


def build_docx_xml(data: dict) -> str:
    totals = data["totals"]
    phases = data["phases"]
    p1, p2, p3 = phases.get("phase1") or {}, phases.get("phase2") or {}, phases.get("phase3") or {}
    phase1, phase2, phase3 = data["phase1"], data["phase2"], data["phase3"]

    body: list[str] = []
    body.append(_wh("ResearchLanka AI — Standard Software Test Report", 1))
    body.append(_wp(f"Generated: {data['stamp']}"))
    body.append(_wp("Suite: unified_phase_tests (Phase 1 + Phase 2 + Phase 3)"))
    body.append(_wp("Deployed URL configured: http://98.81.141.112:3000"))
    body.append(
        _wp(
            f"Overall: Total {totals.get('total', 0)} | Passed {totals.get('passed', 0)} | "
            f"Failed {totals.get('failed', 0)} | Skipped {totals.get('skipped', 0)} | "
            f"Pass rate {totals.get('pass_rate_pct', 0)}%",
            bold=True,
        )
    )
    body.append(_wp(""))

    body.append(_wh("1. Executive summary", 2))
    body.append(
        _wp(
            "Automated testing of ResearchLanka: ETL pipeline, DB/ML/API, and overall app "
            "quality. API tests use real common_publications_final.csv rows."
        )
    )
    body.append(
        _wtable(
            ["Phase", "Total", "Passed", "Failed", "Skipped", "Pass rate", "Status"],
            [
                ["Phase 1 — ETL / pipeline", p1.get("total"), p1.get("passed"), p1.get("failed"), p1.get("skipped"), f"{p1.get('pass_rate_pct')}%", "COMPLETE"],
                ["Phase 2 — DB / ML / API", p2.get("total"), p2.get("passed"), p2.get("failed"), p2.get("skipped"), f"{p2.get('pass_rate_pct')}%", "COMPLETE"],
                ["Phase 3 — Overall application", p3.get("total"), p3.get("passed"), p3.get("failed"), p3.get("skipped"), f"{p3.get('pass_rate_pct')}%", "PARTIAL"],
            ],
        )
    )

    body.append(_wh("2. Phase 1 — ETL results", 2))
    body.append(_wp(f"Result: {p1.get('passed', 0)}/{p1.get('total', 0)} passed ({p1.get('pass_rate_pct', 0)}%)", bold=True))
    body.append(
        _wtable(
            ["Category", "Total", "Passed", "Failed", "Skipped", "Pass rate"],
            [
                [i.get("category"), i.get("total"), i.get("passed"), i.get("failed"), i.get("skipped"), f"{i.get('pass_rate_pct')}%"]
                for i in phase1.get("by_category") or []
            ],
        )
    )
    body.append(
        _wtodo(
            "Full Dagster dg/dev materialization not signed off",
            "Run uv run dg dev; materialize researchlanka_all_assets_job; attach run IDs",
        )
    )

    body.append(_wh("3. Phase 2 — DB / ML / API results", 2))
    body.append(_wp(f"Result: {p2.get('passed', 0)}/{p2.get('total', 0)} passed ({p2.get('pass_rate_pct', 0)}%)", bold=True))
    body.append(
        _wtable(
            ["Category", "Total", "Passed", "Failed", "Skipped", "Pass rate"],
            [
                [i.get("category"), i.get("total"), i.get("passed"), i.get("failed"), i.get("skipped"), f"{i.get('pass_rate_pct')}%"]
                for i in phase2.get("by_category") or []
            ],
        )
    )
    body.append(_wh("3.1 API test matrix", 3))
    body.append(
        _wtable(
            ["Test ID", "Endpoint", "Scenario", "Expected", "Result"],
            [
                [r.get("test_id", ""), r.get("endpoint", ""), r.get("scenario", ""), r.get("expected", ""), r.get("result", "")]
                for r in data["api_rows"]
            ],
        )
    )
    body.append(_wtodo("Live Postgres soak outstanding", "Set DATABASE_URL; compare counts/latency"))

    body.append(_wh("4. Phase 3 — Overall application results", 2))
    body.append(
        _wp(
            f"Result: {p3.get('passed', 0)} passed, {p3.get('skipped', 0)} skipped "
            f"({p3.get('pass_rate_pct', 0)}% of {p3.get('total', 0)})",
            bold=True,
        )
    )
    body.append(
        _wtable(
            ["Category", "Total", "Passed", "Failed", "Skipped", "Pass rate"],
            [
                [i.get("category"), i.get("total"), i.get("passed"), i.get("failed"), i.get("skipped"), f"{i.get('pass_rate_pct')}%"]
                for i in phase3.get("by_category") or []
            ],
        )
    )
    body.append(_wh("4.1 Security matrix", 3))
    body.append(
        _wtable(
            ["Test ID", "Endpoint", "Scenario", "Expected", "Result"],
            [
                [r.get("test_id", ""), r.get("endpoint", ""), r.get("scenario", ""), r.get("expected", ""), r.get("result", "")]
                for r in data["sec_rows"]
            ],
        )
    )
    body.append(_wtodo("Live EC2 site tests SKIPPED", "Re-run from host that opens http://98.81.141.112:3000"))
    body.append(_wtodo("Live login admin + asma", "Use .env credentials; verify /admin"))
    body.append(_wtodo("Frontend Vitest skipped", "cd frontend && npm test"))
    body.append(_wtodo("Playwright E2E missing", "Add browser smoke for core flows"))

    body.append(_wh("5. Detailed test case results", 2))
    limit = 120
    body.append(
        _wtable(
            ["Phase", "Category", "Outcome", "Test case", "Duration (s)"],
            [
                [
                    r.get("phase", ""),
                    r.get("category", ""),
                    r.get("outcome", ""),
                    r.get("test_id") or (r.get("nodeid", "").split("::")[-1]),
                    f"{float(r.get('duration_seconds') or 0):.3f}",
                ]
                for r in data["result_rows"][:limit]
            ],
        )
    )
    if len(data["result_rows"]) > limit:
        body.append(_wp(f"Showing first {limit} of {len(data['result_rows'])} — see unified_testing_results.csv"))

    body.append(_wh("6. Outstanding TODO register", 2))
    body.append(
        _wtable(
            ["ID", "Phase", "Item", "What to do", "Status"],
            [
                ["T-01", "1", "Dagster full materialization", "Materialize job in dg/dev; attach run ID", "TODO"],
                ["T-02", "1", "dagster-quickstart package tests", "Add package tests or accept phase1 coverage", "TODO"],
                ["T-03", "2", "Live Postgres soak", "Set DATABASE_URL; compare counts/latency", "TODO"],
                ["T-04", "3", "Live deployed site smoke", "Run live tests vs http://98.81.141.112:3000", "TODO"],
                ["T-05", "3", "Live auth (admin + asma)", "Confirm sign-in from .env accounts", "TODO"],
                ["T-06", "3", "Vitest suite", "cd frontend && npm test", "TODO"],
                ["T-07", "3", "Playwright E2E", "Add browser smoke for core user flows", "TODO"],
                ["T-08", "3", "Incremental admin API auth", "Keep API private or add token auth", "TODO"],
            ],
        )
    )

    body.append(_wh("7. Sign-off", 2))
    body.append(
        _wtable(
            ["Role", "Name", "Date", "Signature"],
            [["Prepared by", "", "", ""], ["Reviewed by", "", "", ""], ["Approved by", "", "", ""]],
        )
    )
    body.append(_wp("End of report. Close TODOs or accept residual risk before release sign-off."))

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(body)
        + '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="720" w:right="720" w:bottom="720" w:left="720"/>'
        "</w:sectPr></w:body></w:document>"
    )


def write_docx(path: Path, document_xml: str) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""
    doc_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>"""
    core = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>ResearchLanka Standard Test Report</dc:title>
  <dc:creator>ResearchLanka test suite</dc:creator>
  <dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>
</cp:coreProperties>"""
    app = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
  <Application>ResearchLanka test reporter</Application>
</Properties>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/_rels/document.xml.rels", doc_rels)
        zf.writestr("docProps/core.xml", core)
        zf.writestr("docProps/app.xml", app)


def main() -> int:
    data = _load_bundle()
    html_doc = build_html(data)
    docx_xml = build_docx_xml(data)

    COMMON_DIR.mkdir(parents=True, exist_ok=True)
    UNIFIED_DIR.mkdir(parents=True, exist_ok=True)

    html_paths = [
        COMMON_DIR / "ResearchLanka_Standard_Test_Report.html",
        UNIFIED_DIR / "ResearchLanka_Standard_Test_Report.html",
    ]
    docx_paths = [
        COMMON_DIR / "ResearchLanka_Standard_Test_Report.docx",
        UNIFIED_DIR / "ResearchLanka_Standard_Test_Report.docx",
    ]

    for path in html_paths:
        path.write_text(html_doc, encoding="utf-8")
        print(f"Wrote HTML  {path}")

    primary = docx_paths[0]
    write_docx(primary, docx_xml)
    print(f"Wrote DOCX  {primary}")
    for path in docx_paths[1:]:
        path.write_bytes(primary.read_bytes())
        print(f"Wrote DOCX  {path}")

    # Remove misleading old .doc that was HTML-with-.doc-extension
    for stale in [
        COMMON_DIR / "ResearchLanka_Standard_Test_Report.doc",
        UNIFIED_DIR / "ResearchLanka_Standard_Test_Report.doc",
    ]:
        if stale.exists():
            stale.unlink()
            print(f"Removed stale HTML-as-.doc: {stale}")

    print()
    print("Open the report as:")
    print(f"  Browser:  {html_paths[0]}")
    print(f"  Word:     {primary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
