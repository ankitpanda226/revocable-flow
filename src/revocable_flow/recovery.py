"""Fail-closed recovery planning from a preserved three-case sanity artifact."""
import argparse
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import re
import urllib.request

from .artifact_safety import stage_archive
from .providers import GoogleProvider
from .providers.base import http_transport
from .protocol import make_raw_record, parse_output, score_output
from .runner import RunPlan, _deferred, _digest, _read, _write, execute_plan, plan_run
from .schema import ValidationError

BENCHMARK_HASH = "17e4da22029b31b280fcf711bec9c88f261f01ee40dd45137a2ad2540ed4c80d"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def recovery_transport(url, headers, payload):
    # One HTTP dispatch per adapter call; do not forward credentials on redirects.
    return http_transport(url, headers, payload,
                          open_request=urllib.request.build_opener(NoRedirect()).open)


def prepare(source, source_run_id, source_commit, recovery_id, *, config="configs/pilot_eval.yaml"):
    """Validate all source evidence before returning a two-request plan; no networking."""
    source = Path(source)
    if not re.fullmatch(r"gh-gemini-[1-9][0-9]*-[1-9][0-9]*", source_run_id):
        raise ValidationError("invalid source run identity")
    if not isinstance(source_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValidationError("invalid source commit")
    reference = plan_run(config, run_id=source_run_id, provider="google", model="gemini-3.8-flash",
                         condition="post_update", scenario_limit=3,
                         max_provider_requests=3, max_attempts_per_request=1)
    if sha256(reference.benchmark_bytes).hexdigest() != BENCHMARK_HASH:
        raise ValidationError("frozen benchmark changed")
    original = _read(source, f"manifests/{source_run_id}.json")
    identity = deepcopy(original)
    digest = identity.pop("manifest_hash")
    if _digest(identity) != digest or original["commit"] != source_commit or original["git_dirty"] is not False:
        raise ValidationError("source manifest provenance mismatch")
    expected = deepcopy(reference.manifest)
    # Execution provenance can differ; experiment inputs must be byte-for-byte equivalent.
    for field in ("commit", "git_dirty", "python_version", "manifest_hash"):
        identity.pop(field, None)
        expected.pop(field, None)
    if identity != expected:
        raise ValidationError("source manifest does not match frozen sanity plan")
    if (source / original["benchmark_artifact"]).read_bytes() != reference.benchmark_bytes or (source / original["benchmark_metadata_artifact"]).read_bytes() != reference.metadata_bytes:
        raise ValidationError("source benchmark copy differs")
    files = {str(p.relative_to(source)): sha256(p.read_bytes()).hexdigest()
             for p in source.rglob("*") if p.is_file()}
    for request in original["requests"]:
        key, index = request["request_key"], request["execution_index"]
        prefix = f"raw/{source_run_id}/{key}/attempt-01"
        started = _read(source, prefix + ".started.json")
        record = _read(source, prefix + ".response.json")
        prompt = next(p for p in original["prompt_catalog"] if p["execution_index"] == index)
        if any(started.get(k) != v for k, v in {**request, "attempt": 1, "manifest_hash": digest, "messages": prompt["messages"]}.items()):
            raise ValidationError("started request differs from manifest")
        common = {"provider": "google", "requested_model": "gemini-3.8-flash", "condition": "post_update",
                  "attempt": 1, "manifest_hash": digest, "messages": prompt["messages"],
                  "prompt_hash": request["prompt_hash"], "requested_parameters": request["parameters"],
                  "effective_parameters": original["provider_checks"][0]["effective_parameters"],
                  "benchmark_hash": BENCHMARK_HASH}
        if any(record.get(k) != v for k, v in common.items()):
            raise ValidationError("response provenance/settings mismatch")
        parsed_path = source / f"parsed/{source_run_id}/{key}.json"
        if index in (1, 2):
            error = record.get("provider_error") or {}
            if (record.get("parse_status") != "provider_error" or error.get("category") != "http_error"
                    or error.get("http_status") != 503 or error.get("retryable") is not True
                    or record.get("raw_output") is not None or record.get("parsed_output") is not None
                    or parsed_path.exists() or _deferred(record)):
                raise ValidationError("only confirmed terminal HTTP 503 failures may be retried")
        else:
            if record.get("provider_error") is not None or not isinstance(record.get("raw_output"), str):
                raise ValidationError("third request is not a completed provider response")
            scenario = reference.scenarios[2]
            parsed = parse_output(record["raw_output"], scenario)
            reproduced = make_raw_record(scenario=scenario, raw_output=record["raw_output"], execution_index=3,
                provider="google", model="gemini-3.8-flash", timestamp=record["timestamp"], condition="post_update",
                parameters=record["parameters"], latency_ms=record["latency_ms"], request_id=record["request_id"],
                unsupported_parameters=tuple(k for k in record["unsupported_parameters"] if k in {"temperature", "top_p"}))
            if any(record.get(k) != v for k, v in reproduced.items()):
                raise ValidationError("third raw/parsed response is inconsistent")
            expected_parsed = {"request_key": key, "manifest_hash": digest, "raw_hash": _digest(record),
                               "score": asdict(score_output(scenario, "post_update", parsed))}
            if _read(source, f"parsed/{source_run_id}/{key}.json") != expected_parsed:
                raise ValidationError("third request score differs from frozen scorer")
    summaries = list((source / f"summaries/{source_run_id}").glob("completion-*.json"))
    if len(summaries) != 1:
        raise ValidationError("source must have one unambiguous completion summary")
    summary = _read(source, str(summaries[0].relative_to(source)))
    expected_summary = {"manifest_hash": digest, "planned": 3, "completed": 1,
                        "infrastructure_missing": [r["request_key"] for r in original["requests"][:2]],
                        "ambiguous_attempts": [], "complete": False, "primary_complete_design": False,
                        "attempted_provider_requests": 3, "execution_limits": original["execution_limits"]}
    if summary != expected_summary or summaries[0].name != f"completion-{_digest(summary)[:16]}.json":
        raise ValidationError("source completion/dispatch count is inconsistent")
    index = [{"execution_index": i, "scenario_id": s.scenario_id, "family_id": s.family_id,
              "expected_action": s.expected_action.value, "pre_update_expected_action": s.pre_update_expected_action.value}
             for i, s in enumerate(reference.scenarios, 1)]
    if _read(source, f"parsed/{source_run_id}/analysis_index.json") != index:
        raise ValidationError("source analysis mapping differs")
    # Validate the recovery run ID using the existing runner, then narrow the immutable plan.
    fresh = plan_run(config, run_id=recovery_id, provider="google", model="gemini-3.8-flash",
                     condition="post_update", scenario_limit=3, max_provider_requests=3, max_attempts_per_request=1)
    manifest = fresh.manifest
    manifest.update(requests=manifest["requests"][:2], prompt_catalog=manifest["prompt_catalog"][:2],
                    scenario_order=manifest["scenario_order"][:2], scenario_count=2,
                    expected_request_count=2, expected_if_all_selected_enabled=2,
                    execution_limits={"max_provider_requests": 2, "max_attempts_per_request": 1},
                    recovery={"source_run_id": source_run_id, "source_commit": source_commit,
                              "source_manifest_hash": digest, "source_file_hashes": files,
                              "retry_indices": [1, 2], "preserved_index": 3,
                              "source_failure_status": 503, "maximum_new_requests": 2})
    manifest.pop("manifest_hash")
    manifest["manifest_hash"] = _digest(manifest)
    if (fresh.root / f"manifests/{recovery_id}.json").exists():
        raise ValidationError("recovery already exists; replay forbidden")
    return RunPlan(manifest, fresh.scenarios[:2], fresh.root, fresh.config, fresh.benchmark_bytes, fresh.metadata_bytes)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--source-run-id", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--execute-live", action="store_true")
    parser.add_argument("--from-recovery", action="store_true", help="validate first-recovery bundle and dispatch only original index 2")
    args = parser.parse_args()
    try:
        # Validate the narrowly allowlisted original archive before reading its evidence.
        if args.from_recovery:
            from .chained_recovery import prepare_chained, preserve_bundle
            preserved = Path(args.destination)
            preserve_bundle(args.source, args.source_run_id, preserved)
            plan = prepare_chained(preserved, args.source_run_id, args.source_commit, args.run_id)
            print("Chained recovery preflight passed: index 2 only; indices 1 and 3 preserved; maximum 1 new request.")
        else:
            preserved = Path(args.destination) / "source"
            stage_archive(args.source, args.source_run_id, preserved)
            plan = prepare(preserved, args.source_run_id, args.source_commit, args.run_id)
            print("Recovery preflight passed: indices 1 and 2 only; third response preserved; maximum 2 new requests.")
        if not args.execute_live:
            return 0
        summary = execute_plan(plan, execute_live=True,
                               adapters={"google": GoogleProvider(transport=recovery_transport)})
        audit = {"source_manifest_hash": plan.manifest["recovery"]["source_manifest_hash"],
                "manifest_hash": plan.manifest["manifest_hash"], "maximum_new_requests": 2,
                "new_requests_attempted": summary["attempted_provider_requests"],
                "retry_indices": [1, 2], "preserved_index": 3}
        if args.from_recovery:
            audit.update(maximum_new_requests=1,retry_indices=[2],preserved_indices=[1,3],
                         original_manifest_hash=plan.manifest["recovery"]["original_manifest_hash"],
                         prior_trial_attempts=plan.manifest["recovery"]["prior_trial_attempts"],next_trial_attempt=3)
            audit.pop("preserved_index")
        _write(plan.root, f"summaries/{args.run_id}/dispatch-audit.json", audit)
        print(json.dumps(summary, indent=2))
        return 0 if summary["complete"] else 1
    except (ValueError, OSError, KeyError, TypeError):
        raise SystemExit("Recovery validation/execution failed; no replay authorized. Inspect safe artifacts.") from None


if __name__ == "__main__":
    raise SystemExit(main())
