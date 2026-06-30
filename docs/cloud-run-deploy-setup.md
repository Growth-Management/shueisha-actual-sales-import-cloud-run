# Cloud Run Deploy Setup

This repository includes `.github/workflows/deploy-cloud-run.yml` so deployments can be completed from GitHub Actions after the first-time Google Cloud authentication setup is done.

## Deployment Target

- GCP project: `ice-sh`
- Region: `asia-northeast1`
- Cloud Run service: `shueisha-actual-sales-import`
- Runtime service account: `drive-sales-import-runner@ice-sh.iam.gserviceaccount.com`
- Auth mode: unauthenticated access disabled

## Required GitHub Secrets

Configure these repository secrets before relying on agent-driven deploys:

- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_DEPLOY_SERVICE_ACCOUNT`

`GCP_DEPLOY_SERVICE_ACCOUNT` should be the deployer service account email used by GitHub Actions. Prefer a dedicated deployer account, for example:

```text
github-actions-shueisha-sales-import@ice-sh.iam.gserviceaccount.com
```

## Required Google Cloud IAM

The deployer identity used by GitHub Actions needs permissions to build from source and deploy Cloud Run.

Minimum practical roles on project `ice-sh`:

- `roles/run.admin`
- `roles/cloudbuild.builds.editor`
- `roles/storage.admin` or a narrower Cloud Build source/upload bucket role
- `roles/iam.serviceAccountUser` on `drive-sales-import-runner@ice-sh.iam.gserviceaccount.com`

The Cloud Run runtime service account still needs the pipeline runtime permissions:

- Secret Manager access to `drive-oauth-client-id`, `drive-oauth-client-secret`, `drive-oauth-refresh-token`
- Drive access through the OAuth secrets
- GCS write access to `gs://ice-sh-drive-sales-import-landing/`
- BigQuery access to staging, production, and manifest tables

## Agent-Driven Deploy Flow After Setup

1. Agent updates code and merges to `main`.
2. GitHub Actions runs `Deploy Cloud Run` automatically because `main` changed.
3. Agent checks the workflow run, job steps, and logs.
4. Workflow verifies `/readiness` with an authenticated request.
5. If the workflow passes, the new Cloud Run revision is serving traffic.

## Current Remaining Tasks

- Create or identify the GitHub Actions deployer service account.
- Configure Workload Identity Federation for this repository.
- Add repository secrets `GCP_WORKLOAD_IDENTITY_PROVIDER` and `GCP_DEPLOY_SERVICE_ACCOUNT`.
- Grant the deployer service account the IAM roles listed above.
- Run the workflow once and verify the Cloud Run revision plus `/readiness` check.
