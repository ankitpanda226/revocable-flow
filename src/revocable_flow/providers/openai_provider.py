"""OpenAI Responses REST adapter. Exact model support remains a matrix prerequisite."""
from .base import Adapter, numeric_usage


class OpenAIProvider(Adapter):
    provider = "openai"
    credential_variable = "OPENAI_API_KEY"
    endpoint = "https://api.openai.com/v1/responses"

    def payload(self, conversation, model, effective):
        return {"model": model, "input": conversation, **effective, "store": False}

    def normalize(self, reply):
        body = reply.body
        pieces = []
        for item in body["output"]:
            if item.get("type") == "message":
                for part in item.get("content", []):
                    if part.get("type") == "output_text":
                        pieces.append(part["text"])
                    elif part.get("type") == "refusal":
                        pieces.append(part["refusal"])
        return {"raw_output": "".join(pieces), "reported_model": body.get("model"),
                "usage": numeric_usage(body.get("usage")), "finish_reason": body.get("status"),
                "request_id": None}
