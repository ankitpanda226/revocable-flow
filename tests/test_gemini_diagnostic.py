"""Offline fixtures only; no diagnostic is executed against Google."""
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gemini_models_diagnostic", ROOT / ".github/scripts/gemini_models_diagnostic.py")
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)
KEY = "SYN-dummy-diagnostic-credential"


class DiagnosticTests(unittest.TestCase):
    def transport(self, data):
        response = Mock(status=200)
        response.read.return_value = json.dumps(data).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return Mock(return_value=response)

    def test_one_authenticated_get_reports_models_and_capability(self):
        transport = self.transport({"models": [
            {"name": diagnostic.TARGET, "supportedGenerationMethods": ["generateContent", "countTokens"]},
            {"name": "models/SYN-other", "supportedGenerationMethods": ["embedContent"]}]})
        report = diagnostic.diagnose(KEY, transport)
        transport.assert_called_once()
        request = transport.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.full_url, diagnostic.ENDPOINT)
        self.assertIsNone(request.data)
        self.assertEqual(request.get_header("X-goog-api-key"), KEY)
        self.assertTrue(report["target_supports_generateContent"])
        self.assertEqual(len(report["models"]), 2)
        self.assertNotIn(KEY, json.dumps(report))

    def test_capability_absence_and_pagination_are_distinct(self):
        report = diagnostic.diagnose(KEY, self.transport({"models": [{"name": diagnostic.TARGET, "supportedGenerationMethods": ["countTokens"]}]}))
        self.assertFalse(report["target_supports_generateContent"])
        report = diagnostic.diagnose(KEY, self.transport({"models": []}))
        self.assertFalse(report["target_listed"])
        self.assertIsNone(report["target_supports_generateContent"])
        transport = self.transport({"models": [], "nextPageToken": "SYN-token"})
        report = diagnostic.diagnose(KEY, transport)
        self.assertIsNone(report["target_listed"])
        self.assertFalse(report["list_complete"])
        transport.assert_called_once()
        self.assertNotIn("SYN-token", json.dumps(report))

    def test_http503_is_not_retried_or_exposed(self):
        transport = Mock(side_effect=urllib.error.HTTPError(diagnostic.ENDPOINT, 503, KEY, {}, io.BytesIO(KEY.encode())))
        report = diagnostic.diagnose(KEY, transport)
        self.assertEqual(report, {"status": "http_failure", "http_status": 503, "requests_attempted": 1})
        transport.assert_called_once()
        self.assertNotIn(KEY, json.dumps(report))

    def test_missing_secret_and_network_failure(self):
        transport = Mock(side_effect=urllib.error.URLError(KEY))
        self.assertEqual(diagnostic.diagnose(None, transport)["requests_attempted"], 0)
        transport.assert_not_called()
        report = diagnostic.diagnose(KEY, transport)
        self.assertEqual(report["status"], "network_failure")
        self.assertNotIn(KEY, json.dumps(report))
        transport.assert_called_once()

    def test_untrusted_response_never_leaks_key_or_text(self):
        for data in ({"models": [{"name": "models/" + KEY}]},
                     {"models": [{"name": "models/valid", "supportedGenerationMethods": [KEY]}]},
                     {"models": [{"name": "models/<script>"}]},
                     {"models": "invalid"}):
            report = diagnostic.diagnose(KEY, self.transport(data))
            self.assertEqual(report["status"], "invalid_or_unsafe_response")
            self.assertNotIn(KEY, json.dumps(report))

    def test_redirects_never_forward_credentials_or_make_followup(self):
        self.assertIsNone(diagnostic.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.invalid"))
        transport = Mock(side_effect=urllib.error.HTTPError(diagnostic.ENDPOINT, 302, "redirect", {}, None))
        self.assertEqual(diagnostic.diagnose(KEY, transport)["http_status"], 302)
        transport.assert_called_once()

    def test_manual_workflow_has_only_diagnostic_network_step(self):
        workflow = json.loads((ROOT / ".github/workflows/gemini-models-diagnostic.yml").read_text())
        self.assertEqual(workflow["on"], {"workflow_dispatch": {}})
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        job = workflow["jobs"]["diagnostic"]
        self.assertEqual(job["if"], "github.ref == 'refs/heads/main'")
        steps = job["steps"]
        self.assertEqual(steps[1]["with"]["python-version"], "3.12")
        self.assertFalse(steps[0]["with"]["persist-credentials"])
        self.assertEqual(steps[-1]["env"], {"GOOGLE_API_KEY": "${{ secrets.GOOGLE_API_KEY }}"})
        self.assertEqual(steps[-1]["run"], "python .github/scripts/gemini_models_diagnostic.py")
        text = json.dumps(workflow)
        for forbidden in ("pilot-run", "execute-live", "generateContent", "curl", "printenv", "upload-artifact", KEY):
            self.assertNotIn(forbidden, text)
        self.assertIn("unittest discover", steps[-2]["run"])
        self.assertEqual(diagnostic.ENDPOINT, "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000")
