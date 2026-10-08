"""One authenticated read-only models.list request; never generates content."""
import json
import argparse
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000"
TARGET = "models/gemini-3.8-flash"
FLASH_LITE_TARGET = "models/gemini-3.5-flash-lite"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # No extra requests, and no forwarding the credential.


def diagnose(key, open_request=None, *, target=TARGET):
    if target not in {TARGET, FLASH_LITE_TARGET}:
        return {"status": "invalid_target", "requests_attempted": 0}
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
        matches = [m for m in models if m["name"] == target]
        if len(matches) > 1:
            raise ValueError("duplicate target")
        paginated = bool(data.get("nextPageToken"))
        report = {"status": "success", "http_status": status, "requests_attempted": 1,
                  "requested_model": target, "models": models, "list_complete": not paginated,
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


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-model", choices=(TARGET, FLASH_LITE_TARGET), default=TARGET)
    parser.add_argument("--require-target", action="store_true")
    parser.add_argument("--output", help="optional safe JSON report; exclusive write")
    args = parser.parse_args(argv)
    report = diagnose(os.environ.get("GOOGLE_API_KEY"), target=args.target_model)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        from revocable_flow.artifact_safety import _secret_material, _inspect_json, TOKEN_PATTERN
        if any(value in text for value in _secret_material()) or TOKEN_PATTERN.search(text):
            raise SystemExit("Unsafe diagnostic output; no archive authorized.")
        _inspect_json(report)
        path = Path(args.output).absolute()
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise SystemExit("Diagnostic output symlinks forbidden.")
        with path.open("x", encoding="utf-8") as stream:
            stream.write(text + "\n")
        if os.environ.get("GITHUB_OUTPUT"):
            with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
                stream.write("safe=true\n")
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as stream:
            stream.write("## Gemini models.list diagnostic\n\n```json\n" + text + "\n```\n\n")
            stream.write("One read-only request, no retries or generation. Absence from an incomplete list is inconclusive. Model listing does not establish why an earlier generation request returned HTTP 503.\n")
    valid_target = report.get("target_listed") is True and report.get("target_supports_generateContent") is True
    return 0 if report["status"] == "success" and (not args.require_target or valid_target) else 1


if __name__ == "__main__":
    raise SystemExit(main())
