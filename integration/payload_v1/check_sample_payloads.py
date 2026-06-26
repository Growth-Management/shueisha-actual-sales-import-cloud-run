from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path

from payload_builder import SCHEMA_VERSION, validate_payload


DEFAULT_SAMPLE_DIR = Path(__file__).resolve().parent / "samples"
SAMPLE_DIR = Path(os.environ.get("PAYLOAD_SAMPLE_DIR", DEFAULT_SAMPLE_DIR))
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
    if not SAMPLE_DIR.exists():
        raise FileNotFoundError(
            f"sample directory not found: {SAMPLE_DIR}. "
            "Set PAYLOAD_SAMPLE_DIR to the directory containing sample payload JSON files."
        )

    checked: list[str] = []
    for file_name in SAMPLE_FILES:
        payload = load_sample(SAMPLE_DIR / file_name)
        validate_payload(payload)
        checked.append(file_name)
    return checked


if __name__ == "__main__":
    for checked_file in check_samples():
        print(f"ok: {checked_file}")
