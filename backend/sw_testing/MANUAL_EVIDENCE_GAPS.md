# Manual / evidence-only Master Test Plan items

These requirements from the Master Test Plan are **not** claimed as automated
pytest passes. Attach CI logs, screenshots, or measurement sheets instead.

| Plan section | Item | Why automated coverage is limited |
|--------------|------|-----------------------------------|
| 3.1.2 ETL | Live OpenAlex/Crossref/SLJOL pagination & rate limits | Requires external network and source availability |
| 3.1.2 ETL | Full Dagster materialization run IDs | Needs `dg/dev` operator session |
| 3.1.4 AI Review | Live Google Sheets sync / reconcile | Needs Sheets credentials (`SheetsNotConfigured` without them) |
| 3.1.6 UI | Multi-browser matrix (Chrome/Firefox/Edge) | Hardware/CI browser farm not assumed |
| 3.1.6 UI | Lighthouse / accessibility audit scores | Separate tool run |
| 3.1.6 UI | Cytoscape visual correctness on large graphs | Visual/manual judgment |
| 3.1.7 Performance | Locust load / production baselines | Needs agreed environment baselines |
| 3.1.7 Performance | Pipeline wall-clock on full corpus | Long-running ops evidence |
| 3.1.8 Security | OWASP ZAP scan, dependency CVE triage | External scanners |
| 3.1.9 Recovery | Kill DB container / full Dagster restart | Ops procedure evidence |
| 3.1.10 Deploy | GitHub Actions green run + EC2 smoke | CI/deploy logs as evidence |
| 3.1.11 Compat | Windows/macOS/Safari matrix | Not exercised in this Linux suite |

Automated tests under `software_testing/` cover the **testable** subset of each
section with real ResearchLanka code paths.
