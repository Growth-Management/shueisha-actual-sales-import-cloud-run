from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
import os
from typing import Any, Protocol


MANIFEST_TABLE = "ice-sh.ice_sh_process.drive_sales_import_manifest"
PROJECT_ID = os.environ.get("PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")

SECRET_CLIENT_ID = os.environ.get("DRIVE_OAUTH_CLIENT_ID_SECRET", "drive-oauth-client-id")
SECRET_CLIENT_SECRET = os.environ.get("DRIVE_OAUTH_CLIENT_SECRET_SECRET", "drive-oauth-client-secret")
SECRET_REFRESH_TOKEN = os.environ.get("DRIVE_OAUTH_REFRESH_TOKEN_SECRET", "drive-oauth-refresh-token")
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


class DriveClient(Protocol):
    def list_files(self, *, folder_id: str) -> list[dict[str, Any]]:
        ...

    def download_file(self, *, file_id: str) -> bytes:
        ...


class StorageClient(Protocol):
    def upload_bytes(
        self,
        *,
        bucket_name: str,
        object_name: str,
        data: bytes,
        content_type: str | None = None,
    ) -> str:
        ...


class BigQueryClient(Protocol):
    def fetch_manifest_existing_rows(
        self,
        *,
        provider: str,
        sales_yyyymm: list[str],
        table: str = MANIFEST_TABLE,
    ) -> list[dict[str, Any]]:
        ...

    def write_manifest_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        table: str = MANIFEST_TABLE,
        run_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...

    def run_load_jobs(self, load_jobs: list[dict[str, Any]]) -> list[Any]:
        ...

    def run_promotion(self, operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ...

    def run_verification(self, checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ...


class TroccoClient(Protocol):
    def trigger_workflow(self, *, workflow_id: int, payload: dict[str, Any]) -> Any:
        ...


class GoogleDriveClient:
    def __init__(self, service: Any | None = None):
        self._service = service

    @property
    def service(self) -> Any:
        if self._service is None:
            from googleapiclient.discovery import build

            self._service = build(
                "drive",
                "v3",
                credentials=_drive_credentials_from_secret_manager(),
                cache_discovery=False,
            )
        return self._service

    def list_files(self, *, folder_id: str) -> list[dict[str, Any]]:
        query = f"'{folder_id}' in parents and trashed = false"
        fields = "nextPageToken, files(id, name, mimeType, md5Checksum, modifiedTime)"
        files: list[dict[str, Any]] = []
        page_token = None

        while True:
            response = (
                self.service.files()
                .list(q=query, fields=fields, pageToken=page_token, supportsAllDrives=True, includeItemsFromAllDrives=True)
                .execute()
            )
            files.extend(response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                return files

    def download_file(self, *, file_id: str) -> bytes:
        from googleapiclient.http import MediaIoBaseDownload

        request = self.service.files().get_media(fileId=file_id)
        buffer = BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buffer.getvalue()


class GoogleCloudStorageClient:
    def __init__(self, client: Any | None = None):
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            from google.cloud import storage

            self._client = storage.Client()
        return self._client

    def upload_bytes(
        self,
        *,
        bucket_name: str,
        object_name: str,
        data: bytes,
        content_type: str | None = None,
    ) -> str:
        bucket = self.client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        blob.upload_from_string(data, content_type=content_type)
        return f"gs://{bucket_name}/{object_name}"


class GoogleBigQueryClient:
    def __init__(self, client: Any | None = None):
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            from google.cloud import bigquery

            self._client = bigquery.Client()
        return self._client

    def fetch_manifest_existing_rows(
        self,
        *,
        provider: str,
        sales_yyyymm: list[str],
        table: str = MANIFEST_TABLE,
    ) -> list[dict[str, Any]]:
        from google.cloud import bigquery

        sql = f"""
            SELECT *
            FROM `{table}`
            WHERE provider = @provider
              AND sales_yyyymm IN UNNEST(@sales_yyyymm)
              AND COALESCE(is_active_after, is_active, FALSE) = TRUE
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("provider", "STRING", provider),
                bigquery.ArrayQueryParameter("sales_yyyymm", "STRING", sales_yyyymm),
            ]
        )
        rows = self.client.query(sql, job_config=job_config).result()
        return [_row_to_dict(row) for row in rows]

    def write_manifest_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        table: str = MANIFEST_TABLE,
        run_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not rows:
            return {"status": "skipped", "inserted_count": 0, "table": table, "error_message": None}

        try:
            inserted_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            rows_to_insert = [
                {
                    **row,
                    "run_id": (run_context or {}).get("run_id"),
                    "manifest_written_at": inserted_at,
                }
                for row in rows
            ]
            errors = self.client.insert_rows_json(table, rows_to_insert, ignore_unknown_values=True)
            if errors:
                return {
                    "status": "failed",
                    "inserted_count": 0,
                    "table": table,
                    "error_message": str(errors),
                }
            return {
                "status": "success",
                "inserted_count": len(rows_to_insert),
                "table": table,
                "error_message": None,
            }
        except Exception as exc:
            return {
                "status": "failed",
                "inserted_count": 0,
                "table": table,
                "error_message": str(exc),
            }

    def run_load_jobs(self, load_jobs: list[dict[str, Any]]) -> list[Any]:
        results: list[Any] = []
        for config in load_jobs:
            try:
                job_config = self._build_load_job_config(config)
                job = self.client.load_table_from_uri(
                    config["source_uris"],
                    config["destination_table"],
                    job_config=job_config,
                    job_id=config.get("job_id"),
                )
                completed_job = job.result()
                results.append(
                    {
                        "job_id": getattr(completed_job, "job_id", getattr(job, "job_id", config.get("job_id"))),
                        "file_id": config.get("file_id"),
                        "sales_yyyymm": config.get("sales_yyyymm"),
                        "output_rows": getattr(completed_job, "output_rows", getattr(job, "output_rows", 0)),
                        "status": "success",
                    }
                )
            except Exception as exc:
                results.append(_failed_load_job(config, exc))
        return results

    def run_promotion(self, operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for operation in operations:
            try:
                delete_job = self.client.query(operation["delete_sql"])
                completed_delete_job = delete_job.result()
                insert_job = self.client.query(operation["insert_sql"])
                completed_insert_job = insert_job.result()
                results.append(
                    {
                        "sales_yyyymm": operation.get("sales_yyyymm"),
                        "status": "success",
                        "delete_job_id": _job_id(completed_delete_job, delete_job),
                        "insert_job_id": _job_id(completed_insert_job, insert_job),
                        "deleted_row_count": _affected_row_count(completed_delete_job, delete_job),
                        "inserted_row_count": _affected_row_count(completed_insert_job, insert_job),
                        "error_message": None,
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "sales_yyyymm": operation.get("sales_yyyymm"),
                        "status": "failed",
                        "deleted_row_count": 0,
                        "inserted_row_count": 0,
                        "error_message": str(exc),
                    }
                )
        return results

    def run_verification(self, checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for check in checks:
            try:
                rows = list(self.client.query(check["sql"]).result())
                actual = _first_row_value(rows)
                expected = check.get("expected")
                results.append(
                    {
                        "name": check["name"],
                        "status": "passed" if actual == expected else "failed",
                        "expected": expected,
                        "actual": actual,
                        "sql": check["sql"],
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "name": check["name"],
                        "status": "failed",
                        "expected": check.get("expected"),
                        "actual": None,
                        "sql": check.get("sql"),
                        "error_message": str(exc),
                    }
                )
        return results

    def _build_load_job_config(self, config: dict[str, Any]) -> Any:
        from google.cloud import bigquery

        options = dict(config.get("job_config") or {})
        source_format = options.pop("source_format", None)
        if isinstance(source_format, str):
            source_format = getattr(bigquery.SourceFormat, source_format)
        schema = options.pop("schema", None)
        if schema is not None:
            schema = [
                bigquery.SchemaField(
                    field["name"],
                    field["type"],
                    mode=field.get("mode", "NULLABLE"),
                    description=field.get("description"),
                )
                for field in schema
            ]

        return bigquery.LoadJobConfig(
            source_format=source_format,
            autodetect=options.pop("autodetect", None),
            schema=schema,
            skip_leading_rows=options.pop("skip_leading_rows", None),
            write_disposition=options.pop("write_disposition", None),
            **options,
        )


class TroccoApiClient:
    def __init__(self, *, base_url: str | None = None, api_key: str | None = None, session: Any | None = None):
        self.base_url = (base_url or os.environ.get("TROCCO_API_BASE_URL") or "https://trocco.io").rstrip("/")
        self.api_key = api_key or os.environ.get("TROCCO_API_KEY")
        self.session = session

    def trigger_workflow(self, *, workflow_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            raise ValueError("TROCCO_API_KEY is required")
        if self.session is None:
            import requests

            self.session = requests.Session()

        url = f"{self.base_url}/api/workflows/{workflow_id}/runs"
        response = self.session.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Token {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=60,
        )
        return {
            "status_code": getattr(response, "status_code", None),
            "body": _response_body(response),
        }


def _drive_credentials_from_secret_manager() -> Any:
    from google.oauth2.credentials import Credentials

    return Credentials(
        token=None,
        refresh_token=_get_secret(SECRET_REFRESH_TOKEN),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=_get_secret(SECRET_CLIENT_ID),
        client_secret=_get_secret(SECRET_CLIENT_SECRET),
        scopes=DRIVE_SCOPES,
    )


def _get_secret(secret_id: str) -> str:
    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{_project_id()}/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("utf-8").strip()


def _project_id() -> str:
    if PROJECT_ID:
        return PROJECT_ID
    raise ValueError("PROJECT_ID, GOOGLE_CLOUD_PROJECT, or GCLOUD_PROJECT is required for Drive OAuth secrets")


def _first_row_value(rows: list[Any]) -> Any:
    if not rows:
        return None
    row = rows[0]
    if isinstance(row, dict):
        return next(iter(row.values()), None)
    try:
        return row[0]
    except Exception:
        return getattr(row, "value", None)


def _row_to_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    if hasattr(row, "items"):
        return dict(row.items())
    return dict(row)


def _failed_load_job(config: dict[str, Any], exc: Exception) -> dict[str, Any]:
    return {
        "job_id": config.get("job_id"),
        "file_id": config.get("file_id"),
        "sales_yyyymm": config.get("sales_yyyymm"),
        "status": "failed",
        "loaded_row_count": 0,
        "error_message": str(exc),
    }


def _job_id(*jobs: Any) -> str | None:
    for job in jobs:
        job_id = getattr(job, "job_id", None)
        if job_id is not None:
            return str(job_id)
    return None


def _affected_row_count(*jobs: Any) -> int:
    for job in jobs:
        row_count = getattr(job, "num_dml_affected_rows", None)
        if row_count is not None:
            return int(row_count)
    return 0


def _response_body(response: Any) -> Any:
    try:
        return response.json()
    except Exception:
        return getattr(response, "text", None)
