"""One authenticated read-only models.list request; never generates content."""
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000"
TARGET = "models/gemini-3.8-flash"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # No extra requests, and no forwarding the credential.


def diagnose(key, open_request=None):
    if not key:
        return {"status": "missing_secret", "requests_attempted": 0}
    request = urllib.request.Request(ENDPOINT, method="GET", headers={"x-goog-api-key": key})
    if open_request is None:
        open_request = urllib.request.build_opener(NoRedirect()).open
    try:
        with open_request(request, timeout=30) as response:
            status = response.status
            if status != 200:
                return {"status": "http_failure", "http_status": status, "requests_attempted": 1}
            body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError("oversized response")
        data = json.loads(body)
        if not isinstance(data, dict) or not isinstance(data.get("models"), list):
            raise ValueError("invalid models list")
        models = []
        for model in data["models"]:
            name = model["name"]
            methods = model.get("supportedGenerationMethods", [])
            if (not isinstance(name, str) or not re.fullmatch(r"models/[A-Za-z0-9._-]+", name)
                    or not isinstance(methods, list) or any(not isinstance(m, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", m) for m in methods)):
                raise ValueError("invalid model metadata")
            models.append({"name": name, "supported_methods": methods})
        matches = [m for m in models if m["name"] == TARGET]
        if len(matches) > 1:
            raise ValueError("duplicate target")
        paginated = bool(data.get("nextPageToken"))
        report = {"status": "success", "http_status": status, "requests_attempted": 1,
                  "requested_model": TARGET, "models": models, "list_complete": not paginated,
                  "target_listed": bool(matches) if matches or not paginated else None,
                  "target_supports_generateContent": "generateContent" in matches[0]["supported_methods"] if matches else None}
        if key in json.dumps(report):
            raise ValueError("unsafe response")
        return report
    except urllib.error.HTTPError as exc:
        # Never print or persist provider bodies, URLs, headers or exception messages.
        return {"status": "http_failure", "http_status": exc.code, "requests_attempted": 1}
    except (urllib.error.URLError, TimeoutError, OSError):
        return {"status": "network_failure", "requests_attempted": 1}
    except (ValueError, KeyError, TypeError):
        return {"status": "invalid_or_unsafe_response", "requests_attempted": 1}


def main():
    report = diagnose(os.environ.get("GOOGLE_API_KEY"))
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as stream:
            stream.write("## Gemini models.list diagnostic\n\n```json\n" + text + "\n```\n\n")
            stream.write("One read-only request, no retries or generation. Absence from an incomplete list is inconclusive. Model listing does not establish why an earlier generation request returned HTTP 503.\n")
    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
