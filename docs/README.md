# Documentation Index

This directory contains active cross-project documentation. Component-specific
guides remain beside their code in `backend/`, `frontend/`, and
`researchlanka-ai-dataset/`.

## Start here

- [`../README.md`](../README.md) - installation and local start.
- [`../HANDOVER.md`](../HANDOVER.md) - current readiness and publication
  blockers.
- [`../PROJECT_OVERVIEW.md`](../PROJECT_OVERVIEW.md) - architecture and
  repository orientation.
- [`../backend/docs/README.md`](../backend/docs/README.md) - backend technical
  documentation.
- [`../researchlanka-ai-dataset/README.md`](../researchlanka-ai-dataset/README.md)
  - dataset package status.

## Active operations

- [`aws-ec2-app-deployment.md`](aws-ec2-app-deployment.md) - deploy the app on
  EC2 with Docker Compose.
- [`ci-cd-ec2.md`](ci-cd-ec2.md) - GitHub Actions deployment flow.
- [`aws-monthly-automation.md`](aws-monthly-automation.md) - scheduled data and
  model refresh operations.
- [`ai-review-workflow-runbook.md`](ai-review-workflow-runbook.md) - operate the
  AI review workflow.

## Product-specific deployment

- [`cse-uom-site.md`](cse-uom-site.md) - build and deploy the separately scoped
  University of Moratuwa CSE site.
- [`cse-uom-validation-2026-10-20.md`](cse-uom-validation-2026-10-20.md) - dated
  CSE author-attribution validation results, corrections, and review queue.

## Historical evidence

Point-in-time audits, design plans, and presentations live in
[`archive/`](archive/README.md). They are retained for traceability but do not
define current behavior.

## Documentation rules

1. The source code and checked-in manifests override historical reports.
2. Active instructions must use repository-relative paths and link to related
   documents.
3. Date point-in-time findings and move superseded material to `archive/`.
4. Do not publish credentials, private review data, or unapproved dataset/model
   artifacts in documentation.
5. Update this index when adding, moving, or retiring an active document.
