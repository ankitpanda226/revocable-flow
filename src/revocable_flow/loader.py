"""JSONL loading with line-level errors and pilot coverage checks."""
import json
from pathlib import Path
from collections import Counter
from .schema import Prediction, Scenario, Transition, TransitionKind, ValidationError, parse_json


def _load(path: str | Path, record_type):
    records = []
    seen = set()
    with Path(path).open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                raise ValidationError(f"{path}:{line_number}: blank JSONL record")
            try:
                record = record_type.from_dict(parse_json(line))
                if record.scenario_id in seen:
                    raise ValidationError(f"duplicate scenario_id {record.scenario_id}")
            except (json.JSONDecodeError, ValidationError) as exc:
                raise ValidationError(f"{path}:{line_number}: {exc}") from exc
            seen.add(record.scenario_id)
            records.append(record)
    if not records:
        raise ValidationError(f"{path}: empty dataset")
    return records


def load_scenarios(path: str | Path, *, require_pilot: bool = False) -> list[Scenario]:
    scenarios = _load(path, Scenario)
    if require_pilot:
        counts = Counter(s.transition_type for s in scenarios)
        if len(scenarios) != 40 or any(counts[t] != 10 for t in Transition):
            raise ValidationError("pilot requires exactly 40 scenarios, 10 per transition")
        if len({s.domain for s in scenarios}) != 6:
            raise ValidationError("pilot must cover all six domains")
        for transition in Transition:
            if len({s.domain for s in scenarios if s.transition_type is transition}) < 4:
                raise ValidationError("each transition must cover at least four domains")
        expected_ids = {f"{t.value}-{i:02d}" for t in Transition for i in range(1, 11)}
        if {s.scenario_id for s in scenarios} != expected_ids:
            raise ValidationError("v0.2 must preserve exactly the 40 original pilot IDs")
        for scenario in scenarios:
            if not scenario.invalidated_permissions or scenario.added_permissions:
                raise ValidationError("v0.2 pilot cases must contain genuine withdrawal without unrelated new grants")
            if scenario.pre_update_expected_action.value != "ALLOW":
                raise ValidationError("pilot final requests must have been allowed before the update")
            if scenario.turns[-1].role != "tool":
                raise ValidationError("pilot final requests must be tools, not possible new user authorizations")
            records = scenario.initial_authorizations
            if scenario.transition_type is Transition.RECIPIENT_CHANGE:
                if len({a.recipient for a in records}) != 2 or len({a.purpose for a in records}) != 1:
                    raise ValidationError("recipient cases need two initial recipients and one fixed purpose")
                if len({p.recipient for p in scenario.invalidated_permissions}) != 1:
                    raise ValidationError("recipient update must affect exactly one recipient")
            elif scenario.transition_type is Transition.PURPOSE_CHANGE:
                if len({a.purpose for a in records}) != 2 or len({a.recipient for a in records}) != 1:
                    raise ValidationError("purpose cases need two initially granted purposes and one fixed recipient")
                if len({p.purpose for p in scenario.invalidated_permissions}) != 1:
                    raise ValidationError("purpose update must affect exactly one purpose")
            else:
                if len({a.recipient for a in records}) != 1 or len({a.purpose for a in records}) != 1:
                    raise ValidationError("consent/scope cases must hold recipient and purpose constant")
            if len({a.operation for a in records}) != 1 or any(a.status.value != "allowed" for a in records):
                raise ValidationError("pilot initial tuples must explicitly allow one fixed operation")
            if scenario.transition_type is Transition.SCOPE_CHANGE:
                if len({a.information for a in records}) != 1:
                    raise ValidationError("scope changes must concern one record with declared representations")
                if scenario.transition_kind not in {TransitionKind.NARROW, TransitionKind.UNAFFECTED_CONTROL}:
                    raise ValidationError("scope pilot cases must be narrowing targets or controls")
        families = {}
        for scenario in scenarios:
            signature = (frozenset(scenario.initial_authorizations), frozenset(scenario.updated_authorizations),
                         scenario.initial_permission, scenario.policy_update)
            if scenario.family_id in families and families[scenario.family_id] != signature:
                raise ValidationError("matched family members must share permission histories and original record")
            families[scenario.family_id] = signature
        validate_metadata(path, scenarios)
    return scenarios


def load_predictions(path: str | Path) -> list[Prediction]:
    return _load(path, Prediction)


def validate_metadata(path: str | Path, scenarios: list[Scenario]) -> dict:
    """Verify the adjacent, versioned inventory against the exact JSONL bytes."""
    import hashlib
    benchmark = Path(path)
    metadata_path = benchmark.with_name("metadata.json")
    metadata = parse_json(metadata_path.read_text(encoding="utf-8"))
    required = {"benchmark_name", "version", "scenario_count", "created_from", "schema_version",
                "scenario_file", "sha256", "parent_sha256", "ordering_seed", "scenario_ids_preserved"}
    if not isinstance(metadata, dict) or metadata.keys() != required:
        raise ValidationError("benchmark metadata has missing or unknown keys")
    if metadata["benchmark_name"] != "RevocableFlow Pilot" or metadata["version"] != "0.2" or metadata["schema_version"] != "0.2":
        raise ValidationError("unsupported benchmark metadata identity/version")
    if type(metadata["scenario_count"]) is not int or metadata["scenario_count"] != 40 or metadata["scenario_count"] != len(scenarios):
        raise ValidationError("metadata count disagrees with loaded scenarios")
    if metadata["scenario_file"] != benchmark.name:
        raise ValidationError("metadata scenario_file disagrees with benchmark filename")
    if metadata["sha256"] != hashlib.sha256(benchmark.read_bytes()).hexdigest():
        raise ValidationError("benchmark SHA-256 does not match metadata")
    if metadata["created_from"] != "v0.1 audit revision" or type(metadata["ordering_seed"]) is not int:
        raise ValidationError("invalid benchmark revision provenance")
    if metadata["scenario_ids_preserved"] is not True:
        raise ValidationError("pilot revision must preserve the existing scenario IDs")
    if not isinstance(metadata["parent_sha256"], str) or len(metadata["parent_sha256"]) != 64 or any(
            c not in "0123456789abcdef" for c in metadata["parent_sha256"]):
        raise ValidationError("invalid parent SHA-256")
    return metadata
