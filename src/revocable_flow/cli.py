"""Local validation and evaluation commands. Never calls a model provider."""
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
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
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
