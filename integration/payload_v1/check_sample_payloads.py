from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from payload_builder import SCHEMA_VERSION, validate_payload


SAMPLE_DIR = Path("/workspace/agent_files/docs")
SAMPLE_FILES = [
    "sample-payload-apple.json",
    "sample-payload-googleplay.json",
    "sample-payload-failure-format-error.json",
    "sample-payload-failure-staging.json",
    "sample-payload-failure-verification.json",
    "sample-payload-failure-trocco.json",
]


def load_sample(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        payload = json.load(f)
    normalized = deepcopy(payload)
    normalized.setdefault("schema_version", SCHEMA_VERSION)
    return normalized


def check_samples() -> list[str]:
    checked: list[str] = []
    for file_name in SAMPLE_FILES:
        payload = load_sample(SAMPLE_DIR / file_name)
        validate_payload(payload)
        checked.append(file_name)
    return checked


if __name__ == "__main__":
    for checked_file in check_samples():
        print(f"ok: {checked_file}")
