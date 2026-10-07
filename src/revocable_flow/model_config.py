"""Local matrix validation; no credential access or provider imports."""
from datetime import date
from urllib.parse import urlparse
from .schema import ValidationError

PROVIDERS = {"openai": {"developers.openai.com"}, "google": {"ai.google.dev"},
             "anthropic": {"platform.claude.com", "www.anthropic.com"}}
PARAMETERS = {"temperature", "top_p", "max_output_tokens", "seed"}


def validate_matrix(config: dict) -> None:
    matrix = config.get("model_matrix", [])
    if not isinstance(matrix, list):
        raise ValidationError("model_matrix must be a list")
    seen = set()
    active = []
    required = {"provider", "display_name", "model_id", "status", "verification_date",
                "documentation_source", "immutable_snapshot", "notes", "parameter_support"}
    for entry in matrix:
        if not isinstance(entry, dict) or set(entry) != required:
            raise ValidationError("invalid model matrix keys")
        provider = entry["provider"]
        if not isinstance(provider, str) or provider not in PROVIDERS or provider in seen:
            raise ValidationError("matrix requires distinct known providers")
        seen.add(provider)
        if not isinstance(entry["status"], str) or entry["status"] not in {"enabled", "verified", "unresolved", "disabled"}:
            raise ValidationError("invalid model status")
        for key in ("display_name", "documentation_source", "notes", "verification_date"):
            if not isinstance(entry[key], str) or not entry[key].strip():
                raise ValidationError(f"matrix {key} must be nonempty")
        try:
            date.fromisoformat(entry["verification_date"])
        except ValueError:
            raise ValidationError("invalid verification date") from None
        source = urlparse(entry["documentation_source"])
        if source.scheme != "https" or source.hostname not in PROVIDERS[provider] or source.username or source.password:
            raise ValidationError("matrix source must be an official documentation URL")
        if entry["immutable_snapshot"] is not None and type(entry["immutable_snapshot"]) is not bool:
            raise ValidationError("immutable_snapshot must be boolean or null")
        support = entry["parameter_support"]
        if not isinstance(support, dict) or set(support) != PARAMETERS:
            raise ValidationError("parameter support must cover all generation settings")
        if any(not isinstance(v, str) or v not in {"supported", "unsupported", "unresolved"} for v in support.values()):
            raise ValidationError("invalid parameter support status")
        model = entry["model_id"]
        if entry["status"] in {"enabled", "verified"}:
            if not isinstance(model, str) or not model.strip() or entry["immutable_snapshot"] is None:
                raise ValidationError("enabled model needs ID and snapshot/alias classification")
            if any(v == "unresolved" for v in support.values()):
                raise ValidationError("enabled model needs verified parameter support")
            active.append({"provider": provider, "model": model})
        elif model is not None and (not isinstance(model, str) or not model.strip()):
            raise ValidationError("invalid disabled model ID")
    if matrix and config["models"] != active:
        raise ValidationError("models must exactly match enabled matrix entries in order")
    pricing = config.get("pricing")
    if pricing is not None:
        if not isinstance(pricing, dict) or set(pricing) != {"input_per_million", "output_per_million"}:
            raise ValidationError("invalid pricing keys")
        for value in pricing.values():
            if value is not None and (type(value) not in (int, float) or not 0 <= value < float("inf")):
                raise ValidationError("pricing must be finite nonnegative numbers or null")
