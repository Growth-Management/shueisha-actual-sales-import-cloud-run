from __future__ import annotations

from copy import deepcopy
import os
from typing import Any

from payload_builder import PROVIDER_CONFIG
from promotion_sql import build_schema_safe_promotion_operations


LANDING_BUCKET_ENV = "LANDING_BUCKET"
LANDING_PREFIX_ENV = "LANDING_PREFIX"
DEFAULT_LANDING_PREFIX = "landing/drive-sales-import"


def apply_execution_defaults(request_body: dict[str, Any]) -> dict[str, Any]:
    """Fill operational defaults without mutating the caller's request body."""
    if not isinstance(request_body, dict):
        raise ValueError("request body must be a JSON object")

    body = deepcopy(request_body)
    _copy_execution_mode_from_run_context(body)
    _apply_landing_defaults(body)
    _apply_schema_safe_promotion_defaults(body)
    return body


def execution_mode_from_request(request_body: dict[str, Any], default: str = "full") -> str:
    value = request_body.get("execution_mode")
    if isinstance(value, str) and value:
        return value

    run_context = request_body.get("run_context")
    if isinstance(run_context, dict):
        value = run_context.get("execution_mode")
        if isinstance(value, str) and value:
            return value

    return default


def has_landing_bucket(request_body: dict[str, Any]) -> bool:
    landing = request_body.get("landing")
    return isinstance(landing, dict) and isinstance(landing.get("bucket"), str) and bool(landing["bucket"].strip())


def _copy_execution_mode_from_run_context(body: dict[str, Any]) -> None:
    if "execution_mode" in body:
        return

    run_context = body.get("run_context")
    if isinstance(run_context, dict) and isinstance(run_context.get("execution_mode"), str):
        body["execution_mode"] = run_context["execution_mode"]


def _apply_landing_defaults(body: dict[str, Any]) -> None:
    bucket = os.environ.get(LANDING_BUCKET_ENV)
    prefix = os.environ.get(LANDING_PREFIX_ENV, DEFAULT_LANDING_PREFIX)

    if not bucket and not prefix:
        return

    landing = body.get("landing")
    if landing is None:
        landing = {}
        body["landing"] = landing
    if not isinstance(landing, dict):
        raise ValueError("landing must be a JSON object")

    if bucket and not landing.get("bucket"):
        landing["bucket"] = bucket
    if prefix and not landing.get("prefix"):
        landing["prefix"] = prefix


def _apply_schema_safe_promotion_defaults(body: dict[str, Any]) -> None:
    provider = body.get("provider")
    sales_yyyymm = body.get("sales_yyyymm")
    if provider not in PROVIDER_CONFIG or not isinstance(sales_yyyymm, list):
        return

    bigquery = body.get("bigquery")
    if bigquery is None:
        bigquery = {}
        body["bigquery"] = bigquery
    if not isinstance(bigquery, dict):
        raise ValueError("bigquery must be a JSON object")
    if bigquery.get("promotion_operations") or bigquery.get("operations"):
        return

    config = PROVIDER_CONFIG[provider]
    staging_table = bigquery.get("staging_table") or f"{config['staging_dataset']}.{config['staging_table']}"
    production_table = bigquery.get("production_table") or f"{config['production_dataset']}.{config['production_table']}"
    bigquery["promotion_operations"] = build_schema_safe_promotion_operations(
        provider=provider,
        sales_yyyymm=sales_yyyymm,
        staging_table=staging_table,
        production_table=production_table,
    )
