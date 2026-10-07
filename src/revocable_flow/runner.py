"""Manifest-first, opt-in transcript runner. Dry planning performs no network I/O."""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import time

from .protocol import (build_messages, canonical_json, condition_order, load_protocol_benchmark,
                       load_protocol_config, make_raw_record, parse_output, scenario_order,
                       score_output, summarize_scores)
from .providers import PROVIDER_CLASSES
from .providers.base import assert_no_credentials
from .schema import ValidationError, parse_json


@dataclass
class RunPlan:
    manifest: dict
    scenarios: list
    root: Path
    config: dict
    benchmark_bytes: bytes
    metadata_bytes: bytes


def _digest(value):
    return sha256(canonical_json(value).encode()).hexdigest()


def _git(config_path):
    cwd = Path(config_path).resolve().parent
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True)
    status = subprocess.run(["git", "status", "--porcelain"], cwd=cwd, capture_output=True, text=True)
    return {"commit": head.stdout.strip() if head.returncode == 0 else None,
            "dirty": bool(status.stdout.strip()) if status.returncode == 0 else None}


def _validate_root(root):
    for path in (root, *root.parents):
        if path.is_symlink():
            raise ValidationError("artifact root/parents must not be symlinks")
    if root.exists() and not root.is_dir():
        raise ValidationError("artifact root must be a directory")
    for name in ("raw", "parsed", "summaries", "manifests"):
        path = root / name
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise ValidationError("invalid artifact layout")


def _safe_path(root, relative):
    path = root / relative
    if not path.is_relative_to(root):
        raise ValidationError("artifact path outside root")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValidationError("artifact symlinks are forbidden")
    return path


def _write(root, relative, value):
    path = _safe_path(root, relative)
    serialized = canonical_json(value) + "\n"
    assert_no_credentials(serialized)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(serialized)
        stream.flush()
        os.fsync(stream.fileno())


def _read(root, relative):
    path = _safe_path(root, relative)
    text = path.read_text(encoding="utf-8")
    assert_no_credentials(text)
    return parse_json(text)


def _write_or_match(root, relative, value):
    try:
        _write(root, relative, value)
    except FileExistsError:
        if _read(root, relative) != value:
            raise ValidationError("existing artifact differs; refusing overwrite") from None


def plan_run(config_path, *, run_id="dry-preview", provider=None, model=None,
             scenario_limit=None, condition=None) -> RunPlan:
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", run_id):
        raise ValidationError("run_id must be 1–64 safe letters/digits/underscore/hyphen")
    config_path = Path(config_path)
    config = load_protocol_config(config_path)
    scenarios = scenario_order(load_protocol_benchmark(config_path), config["execution"]["seed"])
    full_count = len(scenarios)
    if scenario_limit is not None:
        if type(scenario_limit) is not int or not 1 <= scenario_limit <= full_count:
            raise ValidationError("scenario limit must be between 1 and 40")
        scenarios = scenarios[:scenario_limit]
    if condition is not None and condition not in config["conditions"]:
        raise ValidationError("unknown condition")
    conditions = [condition] if condition else config["conditions"]
    matrix = config.get("model_matrix", [])
    if not matrix:
        raise ValidationError("runner requires a provider matrix with verification metadata")
    if provider is not None and provider not in PROVIDER_CLASSES:
        raise ValidationError("unknown provider")
    selected = [m for m in matrix if (provider is None or m["provider"] == provider)
                and (model is None or m["model_id"] == model)]
    if not selected:
        raise ValidationError("no configured model matches selection")
    enabled = [m for m in selected if m["status"] in {"enabled", "verified"}]
    parameters = {k: config["execution"][k] for k in ("temperature", "top_p", "max_output_tokens", "seed")}
    provider_checks = []
    for entry in selected:
        adapter = PROVIDER_CLASSES[entry["provider"]]
        allowed_omissions = adapter.allowed_omissions(entry["model_id"])
        supported_wire = adapter.wire_supported - allowed_omissions
        unsupported = sorted(k for k, status in entry["parameter_support"].items()
                             if status != "supported" or k not in supported_wire)
        required_ok = not ((set(unsupported) & {"temperature", "top_p", "max_output_tokens"}) - allowed_omissions)
        provider_checks.append({"provider": entry["provider"], "status": entry["status"],
                                "unsupported_or_unresolved_parameters": unsupported,
                                "required_settings_supported": not (set(unsupported) & {"temperature", "top_p", "max_output_tokens"}),
                                "settings_compatible": required_ok,
                                "requested_parameters": parameters.copy(),
                                "effective_parameters": {k: ("unsupported" if k in unsupported else v)
                                                         for k, v in parameters.items()},
                                "documented_sampling_omissions": sorted(allowed_omissions)})
        if entry["status"] in {"enabled", "verified"} and any(status == "supported" and k not in supported_wire
                for k, status in entry["parameter_support"].items()):
            raise ValidationError("matrix capability conflicts with adapter API transport")
        if entry["status"] in {"enabled", "verified"} and not required_ok:
            raise ValidationError("verified model cannot execute frozen required generation settings")
    root = config_path.absolute().parent / config["artifacts"]["root"]
    # Normalize '..' without resolving away symlinks before validation.
    root = Path(os.path.abspath(root))
    _validate_root(root)
    catalog, requests = [], []
    for index, scenario in enumerate(scenarios, 1):
        for c in condition_order(index):
            if c not in conditions:
                continue
            messages = build_messages(scenario, c)
            prompt = {"execution_index": index, "condition": c, "messages": messages, "prompt_hash": _digest(messages)}
            catalog.append(prompt)
            for entry in enabled:
                model_index = matrix.index(entry) + 1
                requests.append({"request_key": f"model-{model_index:02d}/{c}/{index:03d}",
                                 "execution_index": index, "condition": c, "provider": entry["provider"],
                                 "model": entry["model_id"], "model_index": model_index,
                                 "parameters": parameters.copy(), "prompt_hash": prompt["prompt_hash"]})
    git = _git(config_path)
    manifest = {"run_id": run_id, "benchmark": config["benchmark"], "commit": git["commit"],
                "git_dirty": git["dirty"], "python_version": platform.python_version(),
                "provider_transport": "standard-library REST; no SDK", "protocol_version": config["protocol_version"],
                "configuration": config, "config_hash": sha256(config_path.read_bytes()).hexdigest(),
                "config_bytes_utf8": config_path.read_bytes().decode("utf-8"),
                "benchmark_artifact": f"parsed/{run_id}/benchmark.jsonl",
                "benchmark_metadata_artifact": f"parsed/{run_id}/benchmark_metadata.json",
                "seed": config["execution"]["seed"], "model_matrix": selected, "conditions": conditions,
                "scenario_order": [{"execution_index": i, "scenario_id": s.scenario_id} for i, s in enumerate(scenarios, 1)],
                "generation_parameters": parameters, "expected_request_count": len(requests),
                "expected_if_all_selected_enabled": len(scenarios)*len(conditions)*len(selected),
                "configured_models": len(matrix), "selected_models": len(selected), "enabled_models": len(enabled),
                "scenario_count": len(scenarios), "provider_checks": provider_checks,
                "primary_complete_design": len(scenarios) == full_count and conditions == config["conditions"],
                "prompt_catalog": catalog, "requests": requests}
    assert_no_credentials(canonical_json(manifest))
    manifest["manifest_hash"] = _digest(manifest)
    benchmark_path = config_path.parent / config["benchmark"]["path"]
    return RunPlan(manifest, scenarios, root, config, benchmark_path.read_bytes(),
                   benchmark_path.with_name("metadata.json").read_bytes())


def preview(plan):
    m = plan.manifest
    characters = sum(len(canonical_json(p["messages"])) for p in m["prompt_catalog"])
    # Approximation only; it is neither a provider tokenizer nor a billing cap.
    input_tokens = (characters + 3)//4 * m["selected_models"]
    maximum_output = m["expected_if_all_selected_enabled"] * m["generation_parameters"]["max_output_tokens"]
    pricing = plan.config.get("pricing", {})
    rates = (pricing.get("input_per_million"), pricing.get("output_per_million"))
    cost = None if any(v is None for v in rates) else (input_tokens*rates[0] + maximum_output*rates[1])/1_000_000
    return {"mode": "dry_run", "scenario_count": m["scenario_count"], "conditions": m["conditions"],
            "configured_models": m["configured_models"], "selected_models": m["selected_models"],
            "enabled_models": m["enabled_models"], "expected_requests": m["expected_request_count"],
            "expected_requests_if_all_selected_enabled": m["expected_if_all_selected_enabled"],
            "prompts_constructed": len(m["prompt_catalog"]), "manifest_hash": m["manifest_hash"],
            "provider_checks": m["provider_checks"], "network_requests": 0,
            "approximate_input_tokens_if_all_enabled": input_tokens,
            "maximum_output_tokens_if_all_enabled": maximum_output,
            "approximate_cost_if_all_enabled": cost,
            "cost_note": "cost estimate unavailable" if cost is None else "manually configured uniform rates; character-based input estimate, no billing guarantee",
            "artifact_root": str(plan.root), "artifacts_written": False}


def persist_manifest(plan, *, resume=False):
    relative = f"manifests/{plan.manifest['run_id']}.json"
    try:
        _write(plan.root, relative, plan.manifest)
    except FileExistsError:
        if not resume or _read(plan.root, relative) != plan.manifest:
            raise ValidationError("run manifest exists or differs; use exact same plan with resume") from None


def _copy_frozen_bytes(root, relative, data):
    path = _safe_path(root, relative)
    assert_no_credentials(data.decode("utf-8"))
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        if path.read_bytes() != data:
            raise ValidationError("frozen artifact differs; refusing overwrite") from None


def _now():
    return datetime.now(timezone.utc).isoformat()


def _deferred(record):
    delay = record["provider_error"]["retry_after_seconds"] or 0
    if delay <= 60:
        return False
    received = datetime.fromisoformat(record["timestamp"])
    current = datetime.fromisoformat(_now())
    return (current - received).total_seconds() < delay


def execute_plan(plan, *, execute_live=False, resume=False, adapters=None, sleep=time.sleep):
    """Opt-in execution. Tests inject mock adapters; no live execution in this milestone."""
    if execute_live is not True:
        raise ValidationError("live execution requires --execute-live")
    identity = dict(plan.manifest)
    expected_hash = identity.pop("manifest_hash")
    if _digest(identity) != expected_hash:
        raise ValidationError("run plan changed after manifest construction")
    if not plan.manifest["requests"]:
        raise ValidationError("no verified enabled models; live execution refused")
    if plan.manifest["git_dirty"] is not False or not plan.manifest["commit"]:
        raise ValidationError("live execution requires committed, clean execution code")
    # Credentials are checked without recording values and before any research writes.
    used = {r["provider"] for r in plan.manifest["requests"]}
    for provider in used:
        if not os.environ.get(PROVIDER_CLASSES[provider].credential_variable):
            raise ValidationError(f"missing credential environment variable for {provider}")
    if _git(Path(plan.root).parent / "configs/pilot_eval.yaml") != {"commit": plan.manifest["commit"], "dirty": False}:
        raise ValidationError("Git state changed since manifest planning")
    persist_manifest(plan, resume=resume)  # Must precede all provider calls.
    _copy_frozen_bytes(plan.root, plan.manifest["benchmark_artifact"], plan.benchmark_bytes)
    _copy_frozen_bytes(plan.root, plan.manifest["benchmark_metadata_artifact"], plan.metadata_bytes)
    run_id = plan.manifest["run_id"]
    active = {m["provider"]: m for m in plan.manifest["model_matrix"] if m["status"] in {"enabled", "verified"}}
    adapters = adapters if adapters is not None else {p: PROVIDER_CLASSES[p]() for p in used}
    catalog = {(p["execution_index"], p["condition"]): p for p in plan.manifest["prompt_catalog"]}
    completed, failures, ambiguous = [], [], []
    for request in plan.manifest["requests"]:
        index, condition, provider = request["execution_index"], request["condition"], request["provider"]
        scenario = plan.scenarios[index-1]
        prefix = f"raw/{run_id}/{request['request_key']}"
        prompt = catalog[index, condition]
        entry = active[provider]
        previous = None
        terminal = None
        for attempt in range(1, plan.config["retry"]["max_attempts"] + 1):
            started_path = f"{prefix}/attempt-{attempt:02d}.started.json"
            response_path = f"{prefix}/attempt-{attempt:02d}.response.json"
            if _safe_path(plan.root, response_path).exists():
                record = _read(plan.root, response_path)
                if record.get("manifest_hash") != plan.manifest["manifest_hash"] or record.get("attempt") != attempt:
                    raise ValidationError("response provenance mismatch")
                if record.get("parse_status") in {"valid", "invalid"}:
                    terminal = record
                    break
                previous = record
                error = record["provider_error"]
                if not error["retryable"] or _deferred(record):
                    break
                continue
            if _safe_path(plan.root, started_path).exists():
                ambiguous.append(request["request_key"])
                break  # Unknown outcome: no automatic duplicate or retry.
            if previous:
                delay = plan.config["retry"]["backoff_seconds"][attempt-2]
                retry_after = previous["provider_error"]["retry_after_seconds"] or 0
                sleep(max(delay, retry_after if retry_after <= 60 else 0))
            started = {**request, "attempt": attempt, "timestamp": _now(),
                       "manifest_hash": plan.manifest["manifest_hash"], "messages": prompt["messages"]}
            try:
                _write(plan.root, started_path, started)  # Exclusive claim before a possible billable call.
            except FileExistsError:
                ambiguous.append(request["request_key"])
                break
            response = adapters[provider].generate(prompt["messages"], model=request["model"],
                parameters=request["parameters"], supported_parameters={k for k, v in entry["parameter_support"].items()
                if v == "supported"}, execute_live=True)
            if response.provider != provider or response.requested_model != request["model"]:
                raise ValidationError("adapter response model/provider mismatch")
            metadata = {"scenario_anonymous_index": index, "requested_model": response.requested_model, "reported_model": response.reported_model,
                        "usage": response.usage, "finish_reason": response.finish_reason,
                        "requested_parameters": response.requested_parameters,
                        "effective_parameters": response.effective_parameters,
                        "unsupported_parameters": list(response.unsupported_parameters),
                        "structured_output_enforced": response.structured_output_enforced,
                        "attempt": attempt, "manifest_hash": plan.manifest["manifest_hash"]}
            if response.error:
                error = {**asdict(response.error), "retryable": response.error.retryable}
                record = {**started, **metadata, "provider_error": error, "raw_output": None,
                          "parse_status": "provider_error", "parsed_output": None, "timestamp": _now(),
                          "benchmark_version": plan.config["benchmark"]["version"],
                          "benchmark_hash": plan.config["benchmark"]["hash"],
                          "benchmark_commit": plan.config["benchmark"]["commit"],
                          "latency_ms": response.latency_ms, "request_id": response.request_id}
                _write(plan.root, response_path, record)
                previous = record
                if not response.error.retryable or _deferred(record):
                    break
                continue
            effective = {k: response.effective_parameters.get(k) for k in ("temperature", "top_p", "max_output_tokens", "seed")}
            record = make_raw_record(scenario=scenario, raw_output=response.raw_output, execution_index=index,
                provider=provider, model=request["model"], timestamp=_now(), condition=condition,
                parameters=effective, latency_ms=response.latency_ms, request_id=response.request_id,
                unsupported_parameters=tuple(k for k in response.unsupported_parameters if k in {"temperature", "top_p"}))
            record.update(metadata)
            record["provider_error"] = None
            _write(plan.root, response_path, record)
            terminal = record
            break
        if terminal is None:
            failures.append(request["request_key"])
            continue
        parsed = parse_output(terminal["raw_output"], scenario)
        score = score_output(scenario, condition, parsed)
        parsed_record = {"request_key": request["request_key"], "manifest_hash": plan.manifest["manifest_hash"],
                         "raw_hash": _digest(terminal), "score": asdict(score)}
        _write_or_match(plan.root, f"parsed/{run_id}/{request['request_key']}.json", parsed_record)
        completed.append((request, score))
    # Gold metadata belongs in the offline parsed analysis index, never request artifacts.
    index = [{"execution_index": i, "scenario_id": s.scenario_id, "family_id": s.family_id,
              "expected_action": s.expected_action.value, "pre_update_expected_action": s.pre_update_expected_action.value}
             for i, s in enumerate(plan.scenarios, 1)]
    _write_or_match(plan.root, f"parsed/{run_id}/analysis_index.json", index)
    summary = {"manifest_hash": plan.manifest["manifest_hash"], "planned": len(plan.manifest["requests"]),
               "completed": len(completed), "infrastructure_missing": failures, "ambiguous_attempts": ambiguous,
               "complete": not failures, "primary_complete_design": plan.manifest["primary_complete_design"]}
    if not failures and plan.manifest["primary_complete_design"]:
        summary["metrics_by_model"] = {p: summarize_scores(plan.scenarios, [s for r, s in completed if r["provider"] == p])
                                       for p in sorted(used)}
    _write_or_match(plan.root, f"summaries/{run_id}/completion-{_digest(summary)[:16]}.json", summary)
    return summary
