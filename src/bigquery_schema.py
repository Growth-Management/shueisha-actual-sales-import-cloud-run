from __future__ import annotations

from typing import Any

from file_normalization import PROVIDER_RULES


BIGQUERY_TYPE_BY_NORMALIZATION_TYPE = {
    "date": "DATE",
    "integer": "INT64",
    "decimal": "NUMERIC",
}


def schema_for_provider(provider: str) -> list[dict[str, str]]:
    rule = PROVIDER_RULES.get(provider)
    if rule is None:
        raise ValueError("provider must be apple or googleplay")

    types: dict[str, Any] = rule.get("types", {})
    return [
        {
            "name": column,
            "type": BIGQUERY_TYPE_BY_NORMALIZATION_TYPE.get(types.get(column), "STRING"),
            "mode": "NULLABLE",
        }
        for column in rule["columns"]
    ]
