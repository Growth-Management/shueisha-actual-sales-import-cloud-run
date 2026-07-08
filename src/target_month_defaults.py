from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from payload_builder import PROVIDER_CONFIG
from pipeline_clients import DriveClient, GoogleDriveClient


TARGET_MONTH_RE = re.compile(r"(?<!\d)(20\d{4})(?!\d)")
TARGET_MONTH_MODE_AUTO_LATEST = "auto_latest"


def apply_target_month_defaults(request_body: dict[str, Any], *, drive_client: DriveClient | None = None) -> dict[str, Any]:
    if not isinstance(request_body, dict):
        raise ValueError("request body must be a JSON object")

    body = deepcopy(request_body)
    if _has_explicit_sales_yyyymm(body):
        return body
    if body.get("target_month_mode") != TARGET_MONTH_MODE_AUTO_LATEST:
        return body

    provider = body.get("provider")
    if provider not in PROVIDER_CONFIG:
        raise ValueError("provider must be apple or googleplay")

    drive_client = drive_client or GoogleDriveClient()
    folder_id = _folder_id_for_provider(provider)
    files = drive_client.list_files(folder_id=folder_id)
    months = sorted({_sales_month_for_file(file_obj) for file_obj in files if _sales_month_for_file(file_obj)})
    if not months:
        raise ValueError("target_month_mode auto_latest could not detect a target month from Drive files")

    body["sales_yyyymm"] = [months[-1]]
    return body


def _has_explicit_sales_yyyymm(body: dict[str, Any]) -> bool:
    sales_yyyymm = body.get("sales_yyyymm")
    return isinstance(sales_yyyymm, list) and bool(sales_yyyymm)


def _folder_id_for_provider(provider: str) -> str:
    folder_url = PROVIDER_CONFIG[provider]["folder_url"]
    return folder_url.rstrip("/").split("/")[-1]


def _sales_month_for_file(file_obj: dict[str, Any]) -> str | None:
    file_name = _file_value(file_obj, "name", "file_name")
    if not file_name:
        return None
    match = TARGET_MONTH_RE.search(str(file_name))
    return match.group(1) if match else None


def _file_value(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in source:
            return source[key]
    return None
