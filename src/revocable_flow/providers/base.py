"""Provider-neutral response and injected HTTP boundary; standard library only."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import math
import os
import time
from typing import Any, Callable, Protocol
import urllib.error
import urllib.request

from ..schema import ValidationError

CREDENTIAL_VARIABLES = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY")


@dataclass(frozen=True)
class ProviderError:
    category: str
    http_status: int | None = None
    retry_after_seconds: float | None = None

    @property
    def retryable(self):
        return self.category in {"timeout", "connection_reset"} or self.http_status in {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class ProviderResponse:
    provider: str
    requested_model: str
    reported_model: str | None = None
    raw_output: str | None = None
    request_id: str | None = None
    latency_ms: float | None = None
    usage: dict = field(default_factory=dict)
    finish_reason: str | None = None
    error: ProviderError | None = None
    requested_parameters: dict = field(default_factory=dict)
    effective_parameters: dict = field(default_factory=dict)
    unsupported_parameters: tuple[str, ...] = ()
    structured_output_enforced: bool = False


class ModelProvider(Protocol):
    def generate(self, conversation: list[dict[str, str]], *, model: str, parameters: dict,
                 supported_parameters: set[str], execute_live: bool = False) -> ProviderResponse: ...


@dataclass(frozen=True)
class HTTPReply:
    status: int
    body: Any
    headers: dict = field(default_factory=dict)


class TransportFailure(Exception):
    def __init__(self, category: str):
        super().__init__(category)
        self.category = category


Transport = Callable[[str, dict, dict], HTTPReply]


def http_transport(url: str, headers: dict, payload: dict) -> HTTPReply:
    """Only invoked after a live gate. Never surface upstream bodies/errors/keys."""
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return HTTPReply(response.status, json.loads(response.read()), dict(response.headers))
    except urllib.error.HTTPError as exc:
        return HTTPReply(exc.code, None, dict(exc.headers))
    except (TimeoutError, ConnectionResetError) as exc:
        raise TransportFailure("timeout" if isinstance(exc, TimeoutError) else "connection_reset") from None
    except urllib.error.URLError as exc:
        reason = exc.reason
        category = "timeout" if isinstance(reason, TimeoutError) else "connection_reset" if isinstance(reason, ConnectionResetError) else "transport_error"
        raise TransportFailure(category) from None
    except (ValueError, OSError):
        raise TransportFailure("invalid_provider_response") from None


def assert_no_credentials(value: str) -> None:
    # Stop rather than alter raw output if a provider unexpectedly echoes a credential.
    if any(os.environ.get(name) and os.environ[name] in value for name in CREDENTIAL_VARIABLES):
        raise ValidationError("artifact contains credential material; refusing to persist")


def _retry_after(headers: dict) -> float | None:
    value = {str(k).lower(): v for k, v in headers.items()}.get("retry-after")
    if value is None:
        return None
    try:
        seconds = float(value)
        return seconds if math.isfinite(seconds) and seconds >= 0 else None
    except (ValueError, TypeError):
        try:
            return max(0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return None


def numeric_usage(value: Any) -> dict:
    if not isinstance(value, dict):
        return {}
    return {k: v for k, v in value.items() if k in {"input_tokens", "output_tokens", "total_tokens",
            "prompt_tokens", "completion_tokens", "promptTokenCount", "candidatesTokenCount", "totalTokenCount"}
            and type(v) is int and v >= 0}


class Adapter:
    provider = ""
    credential_variable = ""
    endpoint = ""
    wire_supported = {"temperature", "top_p", "max_output_tokens"}

    def __init__(self, *, transport: Transport = http_transport):
        self.transport = transport

    def headers(self, key):
        return {"Content-Type": "application/json", "Authorization": "Bearer " + key}

    def payload(self, conversation, model, effective):
        raise NotImplementedError

    def normalize(self, reply: HTTPReply) -> dict:
        raise NotImplementedError

    def generate(self, conversation, *, model, parameters, supported_parameters, execute_live=False):
        if execute_live is not True:
            raise ValidationError("provider calls require explicit execute_live")
        if (not isinstance(parameters, dict) or set(parameters) != {"temperature", "top_p", "max_output_tokens", "seed"}
                or type(parameters["temperature"]) not in (int, float) or type(parameters["top_p"]) not in (int, float)
                or parameters["temperature"] != 0 or parameters["top_p"] != 1
                or type(parameters["max_output_tokens"]) is not int or parameters["max_output_tokens"] != 512
                or type(parameters["seed"]) is not int or parameters["seed"] != 20261007):
            raise ValidationError("adapter requires frozen generation parameters")
        if (not isinstance(conversation, list) or len(conversation) != 2
                or any(not isinstance(m, dict) or set(m) != {"role", "content"}
                       or not isinstance(m["content"], str) for m in conversation)
                or conversation[0]["role"] != "system" or conversation[1]["role"] != "user"):
            raise ValidationError("adapter requires exactly the frozen system/user messages")
        if not isinstance(model, str) or not model.strip():
            raise ValidationError("requested model must be nonempty")
        requested = dict(parameters)
        supported = set(supported_parameters) & self.wire_supported
        unsupported = tuple(sorted(set(requested) - supported))
        effective = {k: v for k, v in requested.items() if k in supported}
        metadata = dict(provider=self.provider, requested_model=model, requested_parameters=requested,
                        effective_parameters=effective, unsupported_parameters=unsupported)
        if any(k in unsupported for k in ("temperature", "top_p", "max_output_tokens")):
            return ProviderResponse(**metadata, error=ProviderError("unsupported_required_parameters"))
        key = os.environ.get(self.credential_variable)
        if not key:
            return ProviderResponse(**metadata, error=ProviderError("missing_credentials"))
        started = time.monotonic()
        try:
            reply = self.transport(self.endpoint_for(model), self.headers(key), self.payload(conversation, model, effective))
        except TransportFailure as exc:
            return ProviderResponse(**metadata, latency_ms=(time.monotonic()-started)*1000,
                                    error=ProviderError(exc.category))
        except Exception:
            # Do not let arbitrary SDK/transport exception messages expose headers or keys.
            return ProviderResponse(**metadata, latency_ms=(time.monotonic()-started)*1000,
                                    error=ProviderError("transport_error"))
        latency = (time.monotonic()-started)*1000
        headers = {str(k).lower(): v for k, v in reply.headers.items()}
        request_id = headers.get("x-request-id") or headers.get("request-id")
        if not 200 <= reply.status < 300:
            return ProviderResponse(**metadata, request_id=request_id, latency_ms=latency,
                                    error=ProviderError("http_error", reply.status, _retry_after(reply.headers)))
        try:
            data = self.normalize(reply)
            if not isinstance(data.get("raw_output"), str):
                raise ValueError("missing text")
            for field_name in ("reported_model", "request_id", "finish_reason"):
                if data.get(field_name) is not None and not isinstance(data[field_name], str):
                    raise ValueError("invalid metadata")
        except (ValueError, TypeError, KeyError, IndexError, AttributeError):
            return ProviderResponse(**metadata, request_id=request_id, latency_ms=latency,
                                    error=ProviderError("invalid_provider_response"))
        data["request_id"] = request_id or data.get("request_id")
        return ProviderResponse(**metadata, latency_ms=latency, **data)

    def endpoint_for(self, model):
        return self.endpoint
