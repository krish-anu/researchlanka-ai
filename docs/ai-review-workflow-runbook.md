# AI Classification Review Workflow Runbook

This workflow keeps PostgreSQL as the source of truth. Google Sheets is a synchronized export for supervisor handover, not a database backup.

## Configuration

Set placeholders in the EC2 `.env` file using `deploy/aws.ec2.env.example`:

- `AI_REVIEWER_ACCOUNTS`: exactly three existing admin accounts, formatted as `email|user_id|display name` and separated by commas.
- `GOOGLE_SHEETS_SPREADSHEET_ID`: spreadsheet ID only.
- `GOOGLE_SHEETS_SERVICE_ACCOUNT_HOST_FILE`: path on EC2 to the service-account JSON key.
- `GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE`: container path, normally `/run/secrets/google_sheets_service_account.json`.

Do not commit service-account JSON, spreadsheet IDs for private sheets, or production passwords.

## Google Sheets Setup

1. Create or choose a Google Cloud project.
2. Enable the Google Sheets API.
3. Create a service account and download a JSON key.
4. Place the key on EC2, for example `./secrets/google_sheets_service_account.json`, readable only by the deploy user.
5. Create the target spreadsheet.
6. Share the spreadsheet with the service-account email as Editor.
7. Put the spreadsheet ID and key path into the EC2 `.env`.

The application creates or refreshes these worksheets: `Final Dataset`, `Review Audit`, `Dataset Guide`, and `Overflow`.

## Backup Before Production Migration

```bash
mkdir -p backups
docker compose -f compose.aws.yml exec -T db pg_dump \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --format=custom --file=/tmp/researchlanka-before-ai-review.dump
docker compose -f compose.aws.yml cp db:/tmp/researchlanka-before-ai-review.dump \
  backups/researchlanka-before-ai-review-$(date -u +%Y%m%dT%H%M%SZ).dump
```

Verify the backup without touching production:

```bash
docker run --rm --name researchlanka-restore-check \
  -e POSTGRES_PASSWORD=restore_check \
  -d postgres:16
docker cp backups/researchlanka-before-ai-review-YYYYMMDDTHHMMSSZ.dump \
  researchlanka-restore-check:/tmp/backup.dump
docker exec -e PGPASSWORD=restore_check researchlanka-restore-check \
  createdb -U postgres restore_check
docker exec -e PGPASSWORD=restore_check researchlanka-restore-check \
  pg_restore -U postgres -d restore_check /tmp/backup.dump
docker rm -f researchlanka-restore-check
```

## Deploy and Migrate

```bash
docker compose -f compose.aws.yml build api frontend ai-review-worker
docker compose -f compose.aws.yml up -d db
docker compose -f compose.aws.yml run --rm api python scripts/database/apply_database_migrations.py
docker compose -f compose.aws.yml run --rm api python scripts/admin/ai_review_workflow.py backfill
docker compose -f compose.aws.yml up -d api frontend ai-review-worker
```

Backfill is idempotent. It auto-accepts explicit AI records with numeric confidence `>= 0.85` or named `HIGH` confidence, sends explicit AI records with numeric confidence from `0.4` up to `< 0.85` to `pending_review`, rejects explicit AI records below `0.4`, preserves completed human decisions, and assigns unassigned pending records across configured reviewers. Sri Lanka ownership must be verified before any AI acceptance can become public.

## Health Checks

```bash
curl -i http://127.0.0.1:3000/
curl -i -H "X-ResearchLanka-Admin-Token: $RESEARCHLANKA_ADMIN_API_TOKEN" \
  http://127.0.0.1:8080/api/v1/admin/ai-review/validate-final-dataset
docker compose -f compose.aws.yml logs api --tail 120
docker compose -f compose.aws.yml logs ai-review-worker --tail 120
```

## Sheets Sync and Handover

Initial reconciliation:

```bash
docker compose -f compose.aws.yml run --rm api \
  python scripts/admin/ai_review_workflow.py reconcile-sheets
```

Validate the final dataset:

```bash
docker compose -f compose.aws.yml run --rm api \
  python scripts/admin/ai_review_workflow.py validate-final-dataset
```

Generate a dated handover snapshot:

```bash
docker compose -f compose.aws.yml run --rm api \
  python scripts/admin/ai_review_workflow.py snapshot --output-dir outputs/ai-review-snapshots
```

Review unresolved validation issues before declaring the handover dataset ready. Share the spreadsheet with the supervisor manually after explicit authorization.

## Restore and Rollback

Stop services before restoring:

```bash
docker compose -f compose.aws.yml stop api frontend ai-review-worker
docker compose -f compose.aws.yml exec -T db dropdb -U "$POSTGRES_USER" "$POSTGRES_DB"
docker compose -f compose.aws.yml exec -T db createdb -U "$POSTGRES_USER" "$POSTGRES_DB"
docker compose -f compose.aws.yml exec -T db pg_restore \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists \
  /tmp/researchlanka-before-ai-review.dump
docker compose -f compose.aws.yml up -d api frontend
```

Do not restore over production until the isolated restore check has passed.
