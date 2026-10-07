"""Anthropic Messages REST adapter; does not guess model identifiers."""
from .base import Adapter, numeric_usage


class AnthropicProvider(Adapter):
    provider = "anthropic"
    credential_variable = "ANTHROPIC_API_KEY"
    endpoint = "https://api.anthropic.com/v1/messages"

    def headers(self, key):
        return {"Content-Type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"}

    def payload(self, conversation, model, effective):
        return {"model": model, "system": conversation[0]["content"], "messages": conversation[1:],
                "temperature": effective["temperature"], "top_p": effective["top_p"],
                "max_tokens": effective["max_output_tokens"]}

    def normalize(self, reply):
        body = reply.body
        return {"raw_output": "".join(p["text"] for p in body["content"] if p.get("type") == "text"),
                "reported_model": body.get("model"), "request_id": None,
                "usage": numeric_usage(body.get("usage")), "finish_reason": body.get("stop_reason")}
