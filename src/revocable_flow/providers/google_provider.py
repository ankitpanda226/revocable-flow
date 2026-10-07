"""Google generateContent REST adapter; uses a header, never a URL key."""
from urllib.parse import quote
from .base import Adapter, numeric_usage


class GoogleProvider(Adapter):
    provider = "google"
    credential_variable = "GOOGLE_API_KEY"
    wire_supported = {"temperature", "top_p", "max_output_tokens", "seed"}

    @classmethod
    def allowed_omissions(cls, model):
        # Explicit researcher-authorized compatibility exception, not tuning.
        return frozenset({"temperature", "top_p"}) if model == "gemini-3.8-flash" else frozenset()

    def endpoint_for(self, model):
        return "https://generativelanguage.googleapis.com/v1beta/models/" + quote(model, safe="") + ":generateContent"

    def headers(self, key):
        return {"Content-Type": "application/json", "x-goog-api-key": key}

    def payload(self, conversation, model, effective):
        names = {"temperature": "temperature", "top_p": "topP", "max_output_tokens": "maxOutputTokens", "seed": "seed"}
        return {"systemInstruction": {"parts": [{"text": conversation[0]["content"]}]},
                "contents": [{"role": "user", "parts": [{"text": conversation[1]["content"]}]}],
                "generationConfig": {names[k]: v for k, v in effective.items()}}

    def normalize(self, reply):
        body = reply.body
        candidate = body["candidates"][0]
        return {"raw_output": "".join(p["text"] for p in candidate.get("content", {}).get("parts", [])
                                       if "text" in p and not p.get("thought", False)),
                "reported_model": body.get("modelVersion"), "request_id": body.get("responseId"),
                "usage": numeric_usage(body.get("usageMetadata")), "finish_reason": candidate.get("finishReason")}
