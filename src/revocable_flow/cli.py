"""Offline commands and an explicitly gated pilot runner."""
import argparse
import json
from collections import Counter
from .evaluator import evaluate_files
from .loader import load_scenarios


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="revocable-flow")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="validate benchmark JSONL")
    validate.add_argument("benchmark")
    validate.add_argument("--pilot", action="store_true")
    evaluate = sub.add_parser("evaluate", help="score supplied annotated predictions")
    evaluate.add_argument("--benchmark", required=True)
    evaluate.add_argument("--predictions", required=True)
    evaluate.add_argument("--config", required=True)
    evaluate.add_argument("--output-dir", required=True)
    pilot = sub.add_parser("pilot-run", help="preview or explicitly execute a frozen pilot plan")
    pilot.add_argument("--config", default="configs/pilot_eval.yaml")
    pilot.add_argument("--provider", choices=("openai", "google", "anthropic"))
    pilot.add_argument("--model")
    pilot.add_argument("--scenario-limit", type=int)
    pilot.add_argument("--condition", choices=("pre_update", "post_update"))
    gate = pilot.add_mutually_exclusive_group(required=True)
    gate.add_argument("--dry-run", action="store_true")
    gate.add_argument("--execute-live", action="store_true")
    pilot.add_argument("--run-id")
    pilot.add_argument("--resume", action="store_true")
    pilot.add_argument("--manifest-preview", action="store_true")
    pilot.add_argument("--write-manifest", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "pilot-run":
            from .runner import execute_plan, persist_manifest, plan_run, preview
            if (args.execute_live or args.write_manifest or args.resume) and not args.run_id:
                raise ValueError("a unique --run-id is required for persistence/execution/resume")
            if args.execute_live and (args.manifest_preview or args.write_manifest):
                raise ValueError("manifest preview/write options are dry-run only")
            plan = plan_run(args.config, run_id=args.run_id or "dry-preview", provider=args.provider,
                            model=args.model, scenario_limit=args.scenario_limit, condition=args.condition)
            if args.dry_run:
                report = preview(plan)
                if args.write_manifest:
                    persist_manifest(plan, resume=args.resume)
                    report["artifacts_written"] = True
                if args.manifest_preview:
                    report["manifest_preview"] = plan.manifest
            else:
                execution_preview = preview(plan)
                execution_preview["mode"] = "pre_execution_preview"
                print(json.dumps({"execution_preview": execution_preview}, indent=2), flush=True)
                report = execute_plan(plan, execute_live=args.execute_live, resume=args.resume)
            print(json.dumps(report, indent=2))
        elif args.command == "validate":
            scenarios = load_scenarios(args.benchmark, require_pilot=args.pilot)
            print(json.dumps({"count": len(scenarios), "by_transition_type":
                              dict(Counter(s.transition_type.value for s in scenarios)),
                              "by_expected_action": dict(Counter(s.expected_action.value for s in scenarios)),
                              "by_transition_kind": dict(Counter(s.transition_kind.value for s in scenarios)),
                              "salr_eligible": sum(s.salr_eligible for s in scenarios),
                              "families": len({s.family_id for s in scenarios}),
                              "turn_lengths": dict(Counter(len(s.turns) for s in scenarios)),
                              "by_domain": dict(Counter(s.domain.value for s in scenarios))}, indent=2))
        else:
            print(json.dumps(evaluate_files(args.benchmark, args.predictions, args.config, args.output_dir), indent=2))
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
