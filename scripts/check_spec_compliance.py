from __future__ import annotations

from pathlib import Path
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _load(relative: str) -> dict:
    path = ROOT / relative
    if not path.is_file():
        raise ValueError(f"missing required file: {relative}")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected mapping: {relative}")
    return value


def validate() -> list[str]:
    errors: list[str] = []
    try:
        index = _load("docs/spec-index.yaml")
        trace = _load("docs/traceability.yaml")
    except (OSError, UnicodeError, yaml.YAMLError, ValueError) as exc:
        return [str(exc)]
    if index.get("version") != 1 or index.get("project_status") != "configured":
        errors.append("spec index must be version 1 and configured")
    if trace.get("version") != 1:
        errors.append("traceability must be version 1")
    specifications = index.get("specifications") or []
    requirements = trace.get("requirements") or []
    spec_by_id = {item.get("id"): item for item in specifications if isinstance(item, dict)}
    req_by_id = {item.get("id"): item for item in requirements if isinstance(item, dict)}
    for conflict in index.get("conflicts") or []:
        if conflict.get("status") == "unresolved":
            errors.append(f"unresolved conflict: {conflict.get('id')}")
    for spec_id, spec in spec_by_id.items():
        if spec.get("status") != "authoritative":
            continue
        if not (ROOT / str(spec.get("path", ""))).is_file():
            errors.append(f"missing specification: {spec_id}")
        declared = set(spec.get("requirements") or [])
        traced = {req_id for req_id, req in req_by_id.items() if req.get("specification") == spec_id}
        if declared != traced:
            errors.append(f"requirement coverage mismatch: {spec_id}")
    for req_id, req in req_by_id.items():
        if req.get("specification") not in spec_by_id:
            errors.append(f"unknown specification for {req_id}")
        implementations = req.get("implementation")
        implementations = implementations if isinstance(implementations, list) else [implementations]
        if not implementations or any(not (ROOT / str(path)).is_file() for path in implementations):
            errors.append(f"invalid implementation evidence: {req_id}")
        tests = req.get("tests")
        tests = tests if isinstance(tests, list) else [tests]
        if not tests or any(item.get("type") != "executable-test" or not (ROOT / str(item.get("path", ""))).is_file() for item in tests if isinstance(item, dict)):
            errors.append(f"invalid executable test evidence: {req_id}")
        acceptance = req.get("acceptance")
        acceptance = acceptance if isinstance(acceptance, list) else [acceptance]
        types = {item.get("type") for item in acceptance if isinstance(item, dict) and (ROOT / str(item.get("path", ""))).is_file()}
        if "semantic-acceptance" not in types or "independent-review" not in types:
            errors.append(f"incomplete acceptance evidence: {req_id}")
    return sorted(errors)


if __name__ == "__main__":
    failures = validate()
    if failures:
        print("Specification compliance failed:", *failures, sep="\n", file=sys.stderr)
        raise SystemExit(1)
    print("Specification compliance passed.")
