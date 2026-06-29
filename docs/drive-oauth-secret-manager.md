# Drive OAuth Secret Manager setup

This service uses the same Drive OAuth token storage pattern as `Growth-Management/drive-tsv-sync`.

Cloud Run reads these Secret Manager secrets at runtime:

- `drive-oauth-client-id`
- `drive-oauth-client-secret`
- `drive-oauth-refresh-token`

The runtime service account needs `roles/secretmanager.secretAccessor`.

## Cloud Shell setup

```bash
PROJECT_ID=ice-sh
REGION=asia-northeast1
SERVICE_NAME=shueisha-actual-sales-import
SA_NAME=drive-sales-import-runner
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
BUCKET=ice-sh-drive-sales-import-landing
```

Enable Secret Manager if needed:

```bash
gcloud services enable secretmanager.googleapis.com --project="$PROJECT_ID"
```

Create or update the OAuth secrets. Enter the actual values when prompted:

```bash
printf '%s' 'PASTE_CLIENT_ID_HERE' | gcloud secrets create drive-oauth-client-id \
  --project="$PROJECT_ID" \
  --data-file=-

printf '%s' 'PASTE_CLIENT_SECRET_HERE' | gcloud secrets create drive-oauth-client-secret \
  --project="$PROJECT_ID" \
  --data-file=-

printf '%s' 'PASTE_REFRESH_TOKEN_HERE' | gcloud secrets create drive-oauth-refresh-token \
  --project="$PROJECT_ID" \
  --data-file=-
```

If a secret already exists, add a new version instead:

```bash
printf '%s' 'PASTE_CLIENT_ID_HERE' | gcloud secrets versions add drive-oauth-client-id \
  --project="$PROJECT_ID" \
  --data-file=-

printf '%s' 'PASTE_CLIENT_SECRET_HERE' | gcloud secrets versions add drive-oauth-client-secret \
  --project="$PROJECT_ID" \
  --data-file=-

printf '%s' 'PASTE_REFRESH_TOKEN_HERE' | gcloud secrets versions add drive-oauth-refresh-token \
  --project="$PROJECT_ID" \
  --data-file=-
```

Grant the Cloud Run runtime service account access to the secrets:

```bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor"
```

Deploy with `PROJECT_ID` available as an environment variable:

```bash
gcloud run deploy "$SERVICE_NAME" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --source=. \
  --service-account="$SA_EMAIL" \
  --set-env-vars="PROJECT_ID=${PROJECT_ID}" \
  --no-allow-unauthenticated
```

## Staging load only request

Use `execution_mode: "staging_load_only"` to stop before production replacement, verification, and TROCCO.

```json
{
  "provider": "apple",
  "sales_yyyymm": ["202604"],
  "execution_mode": "staging_load_only",
  "run_context": {
    "environment": "prod",
    "trigger_source": "cloud_shell_manual",
    "run_id": "manual__apple__202604",
    "run_started_at": "2026-06-29T00:00:00Z",
    "run_finished_at": null,
    "is_test": false
  },
  "manifest": {
    "table": "ice-sh.ice_sh_process.drive_sales_import_manifest",
    "fetch_existing_rows": true,
    "write_enabled": true
  },
  "landing": {
    "bucket": "ice-sh-drive-sales-import-landing",
    "prefix": "drive-sales-import"
  },
  "bigquery": {
    "load_jobs": [],
    "promotion_operations": [],
    "verification_checks": []
  },
  "trocco_payload": {}
}
```

Expected result:

- `staging.status`: `success`
- `promotion.status`: `not_started`
- `verification.status`: `not_started`
- `trocco.status`: `not_triggered`
