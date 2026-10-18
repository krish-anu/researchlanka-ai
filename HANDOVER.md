# ResearchLanka AI Handover Status

Reviewed: 2026-10-18

## Ready

- Source repository: `https://github.com/krish-anu/researchlanka-ai`
- Production model manifest:
  `backend/configurations/ai_relevance_model_manifest.json`
- Production model artifact (present in this workspace but ignored by Git;
  transfer through the approved model-artifact channel after licensing):
  `backend/data/models/ai_relevance/metadata_ablation_precision_092/A2_title_abstract_keywords.joblib`
- Final AI-only dataset package: `researchlanka-ai-dataset/`
- Canonical release CSV:
  `researchlanka-ai-dataset/data/researchlanka_ai_publications_v1.0.csv`
- Backend runtime mirror:
  `backend/data/processed/common/researchlanka_ai_publications_final.csv`
- Documentation index: `docs/README.md`
- Backend documentation index: `backend/docs/README.md`
- AWS/Docker deployment: `docs/aws-ec2-app-deployment.md`
- CI deployment workflow: `.github/workflows/deploy-main-to-ec2.yml`

## Verification snapshot

- Backend: 786 passed, 12 skipped.
- Frontend: 228 passed; lint and TypeScript checks passed.
- Next.js production build passed with webpack.
- Python byte compilation and package dependency checks passed after aligning
  `pyproject.toml` with `requirements.txt`.
- The production model loads successfully and matches the SHA-256 in its
  manifest.
- No committed private keys or recognizable API-token patterns were found by
  the repository scan.
- Active instructions are indexed separately from dated audits, design plans,
  and superseded model-selection reports.

## Dataset status

The handover corpus contains 3,706 AI-only publications. The supplied curation
removed 352 non-AI records and applied 24 metadata corrections. Search-helper
fields were regenerated, all titles are populated, DOI and OpenAlex identifiers
are unique, and absolute local model paths were removed.

Public upload remains blocked until the `LicenseRef-Pending` source-specific
redistribution review is approved. The dataset is final for internal handover,
but that status does not itself grant public redistribution rights.

The model is technically ready for handover, but its public license must also
be selected before a public model-hosting release.

## Keeping the app online

The project can stay online as long as an AWS EC2 instance (or equivalent
Docker host) remains provisioned and funded. The Compose services use
`restart: unless-stopped`, and pushes to `main` can redeploy through GitHub
Actions after the required repository secrets are configured. Availability is
therefore an infrastructure/account commitment, not something guaranteed by
the repository alone.

Before enabling public access, put the frontend behind HTTPS, set
`AUTH_COOKIE_SECURE=true`, use long random secrets, restrict SSH to an operator
IP, configure backups/monitoring, and decide who will pay for and operate the
host.
