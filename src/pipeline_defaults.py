from __future__ import annotations

from copy import deepcopy
import os
from typing import Any


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
