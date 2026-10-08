"""Stage a narrowly allowlisted sanity archive; no networking or model execution."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import urllib.parse

from .schema import ValidationError, parse_json

SECRET_ENV_NAMES = ("GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GITHUB_TOKEN",
                    "ACTIONS_RUNTIME_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_TOKEN")
SECRET_KEYS = {"api_key", "google_api_key", "openai_api_key", "anthropic_api_key", "authorization",
               "headers", "env", "environment", "secrets", "credentials", "github_token", "access_token"}
TOKEN_PATTERN = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{30,})\b")


def _secret_material():
    variants = set()
    for name in SECRET_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            variants.update((value, urllib.parse.quote(value, safe=""),
                             base64.b64encode(value.encode()).decode(), json.dumps(value)[1:-1]))
    return variants


def _inspect_json(value):
    if isinstance(value, dict):
        if any(k.lower() in SECRET_KEYS for k in value):
            raise ValidationError("unsafe credential/environment field in artifacts")
        for child in value.values():
            _inspect_json(child)
    elif isinstance(value, list):
        for child in value:
            _inspect_json(child)


def stage_archive(root: str | Path, run_id: str, destination: str | Path, *, recovery=False, chained=False, pilot_phase=None) -> int:
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", run_id):
        raise ValidationError("invalid archive run ID")
    root, destination = Path(root).absolute(), Path(destination).absolute()
    if destination.exists() or any(p.is_symlink() for p in (root, destination, *root.parents, *destination.parents)):
        raise ValidationError("archive destination must be new; symlinks forbidden")
    manifest_path = root / "manifests" / f"{run_id}.json"
    if manifest_path.is_symlink() or any(p.is_symlink() for p in manifest_path.parents):
        raise ValidationError("artifact symlinks forbidden")
    manifest = parse_json(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValidationError("invalid archive manifest")
    requests = manifest.get("requests", [])
    if not isinstance(requests, list) or any(not isinstance(r, dict) for r in requests):
        raise ValidationError("invalid archive request records")
    if sum((bool(recovery), bool(chained), pilot_phase is not None)) > 1:
        raise ValidationError("select one archive mode")
    count = 1 if chained else (2 if recovery else 3)
    indices = {2} if chained else set(range(1, count + 1))
    condition, expected_model = "post_update", "gemini-3.8-flash"
    if pilot_phase is not None:
        from .free_tier_campaign import PHASES, MODEL
        if pilot_phase not in PHASES or manifest.get("pilot_phase") != pilot_phase or manifest.get("campaign_version") != "flash-lite-v1":
            raise ValidationError("invalid pilot phase")
        condition, scope = PHASES[pilot_phase]
        indices, count, expected_model = set(scope), len(scope), MODEL
    if recovery or chained:
        lineage = manifest.get("recovery", {})
        preserved = lineage.get("preserved_indices") == [1, 3] if chained else lineage.get("preserved_index") == 3
        if (lineage.get("retry_indices") != sorted(indices) or not preserved
                or lineage.get("maximum_new_requests") != count or lineage.get("source_failure_status") != 503
                or not re.fullmatch(r"[0-9a-f]{64}", lineage.get("source_manifest_hash", ""))):
            raise ValidationError("invalid recovery lineage")
    if (manifest.get("run_id") != run_id or manifest.get("expected_request_count") != count or len(requests) != count
            or manifest.get("execution_limits") != ({"max_provider_requests": count, "max_attempts_per_request": 1,
                  "stop_on_http_statuses": [429], "stop_after_consecutive_http_503": 2, "stop_on_ambiguous": True}
                  if pilot_phase is not None else {"max_provider_requests": count, "max_attempts_per_request": 1})
            or any(r.get("provider") != "google" or r.get("model") != expected_model
                   or r.get("condition") != condition for r in requests)
            or {r.get("execution_index") for r in requests} != indices):
        raise ValidationError("archive is not the approved bounded Gemini plan")
    request_keys = [r.get("request_key", "") for r in requests]
    index_pattern = "(?:" + "|".join(f"{i:03d}" for i in sorted(indices)) + ")"
    if any(not re.fullmatch(r"model-0[1-3]/" + condition + "/" + index_pattern, k) for k in request_keys) or len(set(request_keys)) != count:
        raise ValidationError("unexpected request artifact keys")
    selected = []
    # Select only this run, never the repository, home, runner environment or other runs.
    candidates = [root / "manifests" / f"{run_id}.json"]
    for section in ("raw", "parsed", "summaries"):
        directory = root / section / run_id
        if directory.is_symlink():
            raise ValidationError("artifact symlinks forbidden")
        if directory.exists():
            candidates.extend(directory.rglob("*"))
    variants = _secret_material()
    patterns = {
        "manifests": re.compile(r"^" + re.escape(run_id) + r"\.json$"),
        "raw": re.compile(r"^(?:" + "|".join(re.escape(k) for k in request_keys) + r")/attempt-01\.(started|response)\.json$"),
        "parsed": re.compile(r"^(benchmark\.jsonl|benchmark_metadata\.json|analysis_index\.json|(?:" + "|".join(re.escape(k) for k in request_keys) + r")\.json)$"),
        "summaries": re.compile(r"^(completion-[a-f0-9]{16}\.json" + (r"|dispatch-audit\.json" if recovery or chained or pilot_phase is not None else "") + r")$"),
    }
    for path in candidates:
        if path.is_symlink():
            raise ValidationError("artifact symlinks forbidden")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValidationError("required manifest/artifact missing")
        relative = path.relative_to(root)
        section = relative.parts[0]
        short = str(Path(*relative.parts[1 if section == "manifests" else 2:]))
        if not patterns[section].fullmatch(short):
            raise ValidationError("unexpected file in sanity artifact set")
        data = path.read_bytes()
        text = data.decode("utf-8")
        if any(secret in text for secret in variants) or TOKEN_PATTERN.search(text):
            raise ValidationError("credential material detected; archive refused")
        records = [parse_json(line) for line in text.splitlines()] if path.suffix == ".jsonl" else [parse_json(text)]
        for record in records:
            _inspect_json(record)
        selected.append((relative, data))
    if not selected:
        raise ValidationError("no safe artifacts")
    # Validate all content before creating anything; copy exact bytes, never redact raw data.
    destination.mkdir(parents=True, exist_ok=False)
    for relative, data in selected:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
    return len(selected)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()
    try:
        count = stage_archive("results", args.run_id, args.destination)
    except (ValueError, OSError, RecursionError):
        raise SystemExit("Safe artifact inspection failed; nothing is authorized for upload.") from None
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as stream:
            stream.write("safe=true\n")
    print(f"Safe sanity archive prepared: {count} files.")


if __name__ == "__main__":
    main()
