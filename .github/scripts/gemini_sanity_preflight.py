"""Read-only GitHub sanity preflight. Never imports a client to make an API call."""
import os
from hashlib import sha256
from pathlib import Path

from revocable_flow.runner import plan_run, preview
from revocable_flow.schema import ValidationError

EXPECTED_HASH = "17e4da22029b31b280fcf711bec9c88f261f01ee40dd45137a2ad2540ed4c80d"


def check(run_id):
    if not os.environ.get("GOOGLE_API_KEY"):
        raise ValidationError("required GitHub secret is unavailable")
    if sha256(Path("data/pilot/scenarios.jsonl").read_bytes()).hexdigest() != EXPECTED_HASH:
        raise ValidationError("frozen benchmark hash mismatch")
    plan = plan_run("configs/pilot_eval.yaml", run_id=run_id, provider="google", model="gemini-3.8-flash",
                    condition="post_update", scenario_limit=3, max_provider_requests=3,
                    max_attempts_per_request=1)
    manifest = plan.manifest
    if manifest["git_dirty"] is not False or not manifest["commit"]:
        raise ValidationError("checkout must be clean and committed")
    if (len(plan.scenarios) != 3 or plan.config["execution"]["repetitions"] != 1
            or manifest["conditions"] != ["post_update"] or manifest["enabled_models"] != 1
            or manifest["expected_request_count"] != 3 or len(manifest["requests"]) != 3):
        raise ValidationError("sanity plan must have exactly three single-repetition post-update requests")
    if any(r["provider"] != "google" or r["model"] != "gemini-3.8-flash" or r["condition"] != "post_update"
           for r in manifest["requests"]):
        raise ValidationError("unexpected provider, model or condition")
    settings = preview(plan)["provider_checks"][0]
    if settings["effective_parameters"]["temperature"] != "unsupported" or settings["effective_parameters"]["top_p"] != "unsupported":
        raise ValidationError("Gemini sampling omissions must remain explicit")
    if (plan.root / f"manifests/{run_id}.json").exists():
        raise ValidationError("run ID already exists; refusing accidental replay")
    return plan


if __name__ == "__main__":
    try:
        check(os.environ.get("RUN_ID"))
    except (ValueError, OSError):
        raise SystemExit("Gemini sanity preflight failed; no model request was made.") from None
    print("Preflight passed: google / gemini-3.8-flash / post_update / 3 requests / 1 repetition.")
