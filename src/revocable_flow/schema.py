"""Pilot v0.2: typed permission snapshots, tool contracts and strict validation."""
from dataclasses import dataclass
from enum import Enum
import json
import re
from typing import Any


class ValidationError(ValueError):
    """Invalid benchmark or prediction record."""


def parse_json(text: str) -> Any:
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValidationError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValidationError(f"nonstandard JSON constant: {value}")

    return json.loads(text, object_pairs_hook=unique_object, parse_constant=invalid_constant)


class Action(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REDACT = "REDACT"


class Transition(str, Enum):
    CONSENT_REVOCATION = "consent_revocation"
    RECIPIENT_CHANGE = "recipient_change"
    PURPOSE_CHANGE = "purpose_change"
    SCOPE_CHANGE = "scope_change"


class Domain(str, Enum):
    HEALTHCARE = "healthcare"
    BANKING = "banking"
    TRAVEL = "travel"
    EMPLOYMENT = "employment"
    EDUCATION = "education"
    ECOMMERCE = "ecommerce"


class Status(str, Enum):
    ALLOWED = "allowed"
    DENIED = "denied"


class TransitionKind(str, Enum):
    REVOKE = "revoke"
    NARROW = "narrow"
    ADD = "add"
    UNAFFECTED_CONTROL = "unaffected_control"


class ViolationType(str, Enum):
    STALE = "stale_authorization"
    CROSS_CONTEXT = "cross_context_transfer"
    NONE = "none"


class PermissionState(str, Enum):
    INVALIDATED = "invalidated"
    RETAINED = "retained"
    NEWLY_GRANTED = "newly_granted"
    NEVER_AUTHORIZED = "never_authorized"


def _object(value: Any, keys: set[str], name: str) -> dict:
    if not isinstance(value, dict):
        raise ValidationError(f"{name} must be an object")
    missing, extra = keys - value.keys(), value.keys() - keys
    if missing or extra:
        raise ValidationError(f"{name}: missing={sorted(missing)}, unknown={sorted(extra)}")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{name} must be a nonempty string")
    return value


def _boolean(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise ValidationError(f"{name} must be boolean")
    return value


def _strings(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValidationError(f"{name} must be a list")
    result = tuple(_text(v, name) for v in value)
    if len(result) != len(set(result)):
        raise ValidationError(f"{name} contains duplicates")
    return result


def _enum(cls, value: Any, name: str):
    try:
        return cls(value)
    except (ValueError, TypeError):
        raise ValidationError(f"invalid {name}: {value!r}") from None


def _records(value: Any, cls, name: str) -> tuple:
    if not isinstance(value, list):
        raise ValidationError(f"{name} must be a list")
    return tuple(cls.from_dict(v) for v in value)


@dataclass(frozen=True)
class Permission:
    information: str
    recipient: str
    purpose: str
    scope: str
    operation: str

    @classmethod
    def from_dict(cls, data: Any) -> "Permission":
        _object(data, set(cls.__dataclass_fields__), "permission tuple")
        return cls(**{k: _text(v, k) for k, v in data.items()})


@dataclass(frozen=True)
class Authorization:
    information: str
    recipient: str
    purpose: str
    scope: str
    operation: str
    status: Status

    @property
    def permission(self) -> Permission:
        return Permission(self.information, self.recipient, self.purpose, self.scope, self.operation)

    @classmethod
    def from_dict(cls, data: Any) -> "Authorization":
        _object(data, set(cls.__dataclass_fields__), "authorization")
        return cls(**{k: _text(v, k) for k, v in data.items() if k != "status"},
                   status=_enum(Status, data["status"], "status"))


@dataclass(frozen=True)
class ToolField:
    name: str
    information: str
    scope: str
    disclosure_label: str

    @classmethod
    def from_dict(cls, data: Any) -> "ToolField":
        _object(data, set(cls.__dataclass_fields__), "tool field")
        return cls(**{k: _text(v, k) for k, v in data.items()})

    def permission(self, recipient: str, purpose: str, operation: str) -> Permission:
        return Permission(self.information, recipient, purpose, self.scope, operation)


@dataclass(frozen=True)
class ToolContract:
    operation: str
    required: tuple[ToolField, ...]
    optional: tuple[ToolField, ...]
    accepts_partial_payload: bool

    @property
    def fields(self) -> tuple[ToolField, ...]:
        return self.required + self.optional

    @classmethod
    def from_dict(cls, data: Any) -> "ToolContract":
        _object(data, set(cls.__dataclass_fields__), "tool contract")
        contract = cls(_text(data["operation"], "operation"),
                       _records(data["required"], ToolField, "required"),
                       _records(data["optional"], ToolField, "optional"),
                       _boolean(data["accepts_partial_payload"], "accepts_partial_payload"))
        if not contract.fields:
            raise ValidationError("tool contract requires fields")
        for values in ([f.name for f in contract.fields], [f.disclosure_label for f in contract.fields],
                       [(f.information, f.scope) for f in contract.fields]):
            if len(values) != len(set(values)):
                raise ValidationError("tool fields must have unique names, labels and information/scope pairs")
        return contract

    def public_schema(self) -> dict:
        """Operational requirements only: no privacy policy, annotation labels or golds."""
        return {"operation": self.operation, "required": [f.name for f in self.required],
                "optional": [f.name for f in self.optional],
                "accepts_partial_payload": self.accepts_partial_payload,
                "fields": {f.name: {"information": f.information, "scope": f.scope} for f in self.fields}}

    def render(self) -> str:
        return json.dumps(self.public_schema(), sort_keys=True, ensure_ascii=False)


@dataclass(frozen=True)
class Turn:
    turn_id: str
    role: str
    stage: str
    content: str

    @classmethod
    def from_dict(cls, data: Any) -> "Turn":
        _object(data, set(cls.__dataclass_fields__), "turn")
        turn = cls(**{k: _text(v, k) for k, v in data.items()})
        if turn.role not in {"user", "assistant", "tool"}:
            raise ValidationError("turn role must be user, assistant, or tool")
        if turn.stage not in {"initial_permission", "tool_contract", "context", "policy_update", "final_request"}:
            raise ValidationError("invalid turn stage")
        return turn


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    family_id: str
    domain: Domain
    transition_type: Transition
    transition_kind: TransitionKind
    violation_type: ViolationType
    salr_eligible: bool
    private_attribute: str
    synthetic_private_value: str
    initial_permission: str
    policy_update: str
    final_request: str
    recipient: str
    purpose: str
    allowed_information: tuple[str, ...]
    forbidden_information: tuple[str, ...]
    pre_update_expected_action: Action
    expected_action: Action
    rationale: str
    initial_authorizations: tuple[Authorization, ...]
    updated_authorizations: tuple[Authorization, ...]
    tool_contract: ToolContract
    final_request_fields: tuple[str, ...]
    turns: tuple[Turn, ...]

    @classmethod
    def from_dict(cls, data: Any) -> "Scenario":
        _object(data, set(cls.__dataclass_fields__), "scenario")
        conversions = {"domain": Domain, "transition_type": Transition, "transition_kind": TransitionKind,
                       "violation_type": ViolationType, "expected_action": Action,
                       "pre_update_expected_action": Action}
        lists = {"allowed_information", "forbidden_information", "final_request_fields"}
        records = {"initial_authorizations": Authorization, "updated_authorizations": Authorization, "turns": Turn}
        values = {}
        for key, value in data.items():
            if key in conversions:
                values[key] = _enum(conversions[key], value, key)
            elif key in lists:
                values[key] = _strings(value, key)
            elif key in records:
                values[key] = _records(value, records[key], key)
            elif key == "salr_eligible":
                values[key] = _boolean(value, key)
            elif key == "tool_contract":
                values[key] = ToolContract.from_dict(value)
            else:
                values[key] = _text(value, key)
        scenario = cls(**values)
        scenario.validate()
        return scenario

    def allowed_permissions(self, *, before: bool = False) -> frozenset[Permission]:
        records = self.initial_authorizations if before else self.updated_authorizations
        return frozenset(a.permission for a in records if a.status is Status.ALLOWED)

    @property
    def invalidated_permissions(self) -> frozenset[Permission]:
        return self.allowed_permissions(before=True) - self.allowed_permissions()

    @property
    def added_permissions(self) -> frozenset[Permission]:
        return self.allowed_permissions() - self.allowed_permissions(before=True)

    def permission_state(self, permission: Permission) -> PermissionState:
        prior = permission in self.allowed_permissions(before=True)
        current = permission in self.allowed_permissions()
        if prior and not current:
            return PermissionState.INVALIDATED
        if prior and current:
            return PermissionState.RETAINED
        if not prior and current:
            return PermissionState.NEWLY_GRANTED
        return PermissionState.NEVER_AUTHORIZED

    def permission_for(self, field: ToolField) -> Permission:
        return field.permission(self.recipient, self.purpose, self.tool_contract.operation)

    @property
    def requested_fields(self) -> tuple[ToolField, ...]:
        return tuple(f for f in self.tool_contract.fields if f.name in self.final_request_fields)

    @property
    def tested_invalidated_permissions(self) -> frozenset[Permission]:
        return frozenset(self.permission_for(f) for f in self.requested_fields) & self.invalidated_permissions

    @property
    def stale_disclosure_labels(self) -> frozenset[str]:
        return frozenset(f.disclosure_label for f in self.requested_fields
                         if self.permission_for(f) in self.tested_invalidated_permissions)

    def derive_action(self, *, before: bool = False) -> Action:
        allowed = self.allowed_permissions(before=before)
        permitted = [f for f in self.requested_fields if self.permission_for(f) in allowed]
        if len(permitted) == len(self.requested_fields):
            return Action.ALLOW
        if not permitted or not self.tool_contract.accepts_partial_payload:
            return Action.BLOCK
        if any(self.permission_for(f) not in allowed for f in self.tool_contract.required):
            return Action.BLOCK
        return Action.REDACT

    def validate(self) -> None:
        for label, records in (("initial", self.initial_authorizations), ("updated", self.updated_authorizations)):
            if not records:
                raise ValidationError(f"{label} authorization snapshot is empty")
            keys = [a.permission for a in records]
            if len(keys) != len(set(keys)):
                raise ValidationError(f"duplicate/conflicting {label} authorization tuple")
        initial_keys = {a.permission for a in self.initial_authorizations}
        updated_keys = {a.permission for a in self.updated_authorizations}
        if not initial_keys <= updated_keys:
            raise ValidationError("updated snapshot must explicitly retain or deny every earlier tuple")
        field_names = {f.name for f in self.tool_contract.fields}
        if not self.final_request_fields or not set(self.final_request_fields) <= field_names:
            raise ValidationError("final request fields must be nonempty known tool fields")
        if not {f.name for f in self.tool_contract.required} <= set(self.final_request_fields):
            raise ValidationError("final request omits required tool fields")
        for field in self.tool_contract.fields:
            if self.permission_for(field) not in updated_keys:
                raise ValidationError("every tool field requires an explicit final-context updated authorization")
        if self.pre_update_expected_action is not self.derive_action(before=True):
            raise ValidationError("pre-update counterfactual disagrees with exact permission tuples and contract")
        if self.expected_action is not self.derive_action():
            raise ValidationError("post-update gold disagrees with permission tuples and contract")
        allowed = {f.disclosure_label for f in self.requested_fields if self.permission_for(f) in self.allowed_permissions()}
        forbidden = {f.disclosure_label for f in self.tool_contract.fields if self.permission_for(f) not in self.allowed_permissions()}
        if set(self.allowed_information) != allowed or set(self.forbidden_information) != forbidden:
            raise ValidationError("information annotations disagree with final-context permission tuples")
        if self.expected_action is Action.REDACT and not self.tool_contract.accepts_partial_payload:
            raise ValidationError("REDACT requires partial-payload support")
        stale = bool(self.tested_invalidated_permissions)
        if self.salr_eligible != stale:
            raise ValidationError("SALR eligibility must match requested exact invalidated permission tuples")
        requested_denied = [self.permission_for(f) for f in self.requested_fields
                            if self.permission_for(f) not in self.allowed_permissions()]
        cross = any(p not in self.allowed_permissions(before=True) and
                    any(old.information == p.information for old in self.allowed_permissions(before=True))
                    for p in requested_denied)
        if stale and cross:
            raise ValidationError("split mixed stale/cross-context failure targets into separate cases")
        violation = ViolationType.STALE if stale else ViolationType.CROSS_CONTEXT if cross else ViolationType.NONE
        if self.violation_type is not violation:
            raise ValidationError("violation type disagrees with permission history and requested context")
        kind = self.transition_kind
        if kind in {TransitionKind.REVOKE, TransitionKind.NARROW}:
            if not stale or self.pre_update_expected_action is not Action.ALLOW or self.expected_action is Action.ALLOW:
                raise ValidationError("withdrawal target must be initially allowed and become BLOCK/REDACT")
            if self.added_permissions:
                raise ValidationError("withdrawal target must not introduce unrelated additive grants")
        elif kind is TransitionKind.UNAFFECTED_CONTROL:
            if not self.invalidated_permissions or self.added_permissions or stale or self.expected_action is not Action.ALLOW:
                raise ValidationError("unaffected control needs a real withdrawal elsewhere and an unchanged ALLOW request")
            if any(self.permission_state(self.permission_for(f)) is not PermissionState.RETAINED for f in self.requested_fields):
                raise ValidationError("control requests must retain exact earlier grants")
        elif kind is TransitionKind.ADD:
            if not self.added_permissions or self.invalidated_permissions:
                raise ValidationError("add cases need new permissions without simultaneous withdrawals")
        if kind is TransitionKind.NARROW:
            for lost in self.tested_invalidated_permissions:
                if not any((kept.information, kept.recipient, kept.purpose, kept.operation) ==
                           (lost.information, lost.recipient, lost.purpose, lost.operation) and kept.scope != lost.scope
                           for kept in self.allowed_permissions()):
                    raise ValidationError("narrowing must retain a different declared scope of the same operation")
        self._validate_turns()

    def _validate_turns(self) -> None:
        ids = [t.turn_id for t in self.turns]
        if len(ids) != len(set(ids)):
            raise ValidationError("duplicate turn IDs")
        stages = [t.stage for t in self.turns]
        required = ("initial_permission", "tool_contract", "policy_update", "final_request")
        if any(stages.count(stage) != 1 for stage in required):
            raise ValidationError("require exactly one permission, tool contract, update and final request")
        initial, contract, update, final = [stages.index(stage) for stage in required]
        if not (initial == 0 < contract < update < final == len(stages) - 1):
            raise ValidationError("contract must precede update; permission first and request last")
        if "context" not in stages[1:update]:
            raise ValidationError("require task context before the update")
        for stage, pos in (("initial_permission", initial), ("policy_update", update), ("final_request", final)):
            if self.turns[pos].content != getattr(self, stage):
                raise ValidationError(f"{stage} text must match its turn")
        if self.turns[initial].role != "user" or self.turns[update].role != "user":
            raise ValidationError("permission and update must come from the user")
        if self.turns[contract].role != "tool" or self.turns[contract].content != self.tool_contract.render():
            raise ValidationError("tool contract turn must match the policy-independent public schema")
        if self.turns[final].role not in {"user", "tool"}:
            raise ValidationError("final request must come from a user or tool")
        # Metadata never belongs in visible content. These are defensive safeguards,
        # not a semantic proof that natural-language phrasing contains no answer cues.
        protected = (self.scenario_id, self.family_id, self.rationale, "scenario_id", "family_id", "rationale",
                     "transition_type", "allowed_information", "forbidden_information", "final_request_fields",
                     "expected_action", "pre_update_expected_action",
                     "salr_eligible", "initial_authorizations", "updated_authorizations", "violation_type",
                     "transition_kind", "disclosure_label")
        for turn in self.turns:
            if any(token in turn.content for token in protected):
                raise ValidationError("model-visible turn leaks annotation metadata or rationale")
            if re.search(r"\b(?:ALLOW|BLOCK|REDACT)\b", turn.content):
                raise ValidationError("model-visible turn contains a gold action token")

    def conversation(self) -> list[dict[str, str]]:
        """Only visible turns; tool schemas omit annotation labels and policy snapshots."""
        return [{"role": t.role, "content": t.content} for t in self.turns]


@dataclass(frozen=True)
class Prediction:
    scenario_id: str
    action: Action
    disclosed_information: tuple[str, ...]
    raw_output: str

    @classmethod
    def from_dict(cls, data: Any) -> "Prediction":
        _object(data, set(cls.__dataclass_fields__), "prediction")
        return cls(_text(data["scenario_id"], "scenario_id"),
                   _enum(Action, data["action"], "action"),
                   _strings(data["disclosed_information"], "disclosed_information"),
                   _text(data["raw_output"], "raw_output"))
