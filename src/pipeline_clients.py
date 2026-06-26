from __future__ import annotations

import os
from typing import Any, Protocol


class DriveClient(Protocol):
    def list_files(self, *, folder_id: str) -> list[dict[str, Any]]:
        ...


class BigQueryClient(Protocol):
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

            self._service = build("drive", "v3", cache_discovery=False)
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


class GoogleBigQueryClient:
    def __init__(self, client: Any | None = None):
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            from google.cloud import bigquery

            self._client = bigquery.Client()
        return self._client

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
                delete_job.result()
                insert_job = self.client.query(operation["insert_sql"])
                insert_job.result()
                results.append(
                    {
                        "sales_yyyymm": operation.get("sales_yyyymm"),
                        "delete_job": delete_job,
                        "insert_job": insert_job,
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

        return bigquery.LoadJobConfig(
            source_format=source_format,
            autodetect=options.pop("autodetect", None),
            skip_leading_rows=options.pop("skip_leading_rows", None),
            write_disposition=options.pop("write_disposition", None),
            **options,
        )


class TroccoApiClient:
    def __init__(self, *, base_url: str | None = None, api_key: str | None = None, session: Any | None = None):
        self.base_url = (base_url or os.environ.get("TROCCO_API_BASE_URL") or "https://trocco.io").rstrip("/")
        self.api_key = api_key or os.environ.get("TROCCO_API_KEY")
        self.session = session

    def trigger_workflow(self, *, workflow_id: int, payload: dict[str, Any]) -> Any:
        if not self.api_key:
            raise ValueError("TROCCO_API_KEY is required")
        if self.session is None:
            import requests

            self.session = requests.Session()

        url = f"{self.base_url}/api/workflows/{workflow_id}/runs"
        return self.session.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Token {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=60,
        )


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


def _failed_load_job(config: dict[str, Any], exc: Exception) -> dict[str, Any]:
    return {
        "job_id": config.get("job_id"),
        "file_id": config.get("file_id"),
        "sales_yyyymm": config.get("sales_yyyymm"),
        "status": "failed",
        "loaded_row_count": 0,
        "error_message": str(exc),
    }
