"""Offline fixtures only; no diagnostic is executed against Google."""
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
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

    def test_flash_lite_uses_one_get_and_unknown_target_never_dispatches(self):
        transport = self.transport({"models": [{"name": diagnostic.FLASH_LITE_TARGET,
            "supportedGenerationMethods": ["generateContent"]}]})
        report = diagnostic.diagnose(KEY, transport, target=diagnostic.FLASH_LITE_TARGET)
        transport.assert_called_once()
        request = transport.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.full_url, diagnostic.ENDPOINT)
        self.assertIsNone(request.data)
        self.assertNotIn(KEY, request.full_url)
        self.assertEqual(report["requested_model"], diagnostic.FLASH_LITE_TARGET)
        self.assertTrue(report["target_supports_generateContent"])
        transport.reset_mock()
        self.assertEqual(diagnostic.diagnose(KEY, transport, target="models/SYN-unapproved"),
                         {"status": "invalid_target", "requests_attempted": 0})
        transport.assert_not_called()

    def test_require_target_fails_closed_without_followup_requests(self):
        for data in ({"models": []}, {"models": [], "nextPageToken": "SYN-page"},
                     {"models": [{"name": diagnostic.FLASH_LITE_TARGET,
                                  "supportedGenerationMethods": ["countTokens"]}]}):
            transport = self.transport(data)
            with patch.dict(os.environ, {"GOOGLE_API_KEY": KEY}, clear=True), \
                 patch.object(diagnostic.urllib.request, "build_opener") as opener, \
                 patch("sys.stdout", new_callable=io.StringIO):
                opener.return_value.open = transport
                self.assertEqual(diagnostic.main(["--target-model", diagnostic.FLASH_LITE_TARGET,
                                                  "--require-target"]), 1)
            transport.assert_called_once()

    def test_safe_output_exclusive_write_and_upload_authorization(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            github_output = Path(directory) / "github-output"
            report = {"status": "success", "requested_model": diagnostic.FLASH_LITE_TARGET,
                      "target_listed": True, "target_supports_generateContent": True,
                      "requests_attempted": 1}
            with patch.dict(os.environ, {"GOOGLE_API_KEY": KEY,
                                        "GITHUB_OUTPUT": str(github_output)}, clear=True), \
                 patch.object(diagnostic, "diagnose", return_value=report) as diagnose, \
                 patch("sys.stdout", new_callable=io.StringIO) as stdout:
                args = ["--target-model", diagnostic.FLASH_LITE_TARGET, "--require-target",
                        "--output", str(output)]
                self.assertEqual(diagnostic.main(args), 0)
                diagnose.assert_called_once_with(KEY, target=diagnostic.FLASH_LITE_TARGET)
                self.assertEqual(json.loads(output.read_text()), report)
                self.assertNotIn(KEY, stdout.getvalue() + output.read_text())
                self.assertEqual(github_output.read_text(), "safe=true\n")
                original = output.read_bytes()
                with self.assertRaises(FileExistsError):
                    diagnostic.main(args)
                self.assertEqual(output.read_bytes(), original)
                self.assertEqual(github_output.read_text(), "safe=true\n")

    def test_unsafe_or_symlink_output_never_authorizes_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            github_output = Path(directory) / "github-output"
            with patch.dict(os.environ, {"GOOGLE_API_KEY": KEY,
                                        "GITHUB_OUTPUT": str(github_output)}, clear=True), \
                 patch.object(diagnostic, "diagnose", return_value={"status": "success", "unsafe": KEY}), \
                 patch("sys.stdout", new_callable=io.StringIO) as stdout:
                with self.assertRaises(SystemExit):
                    diagnostic.main(["--output", str(output)])
                self.assertFalse(output.exists())
                self.assertFalse(github_output.exists())
                self.assertEqual(stdout.getvalue(), "")
            target = Path(directory) / "target"
            target.write_text("SYN-preserve")
            output.symlink_to(target)
            with patch.dict(os.environ, {"GITHUB_OUTPUT": str(github_output)}, clear=True), \
                 patch.object(diagnostic, "diagnose", return_value={"status": "missing_secret"}), \
                 patch("sys.stdout", new_callable=io.StringIO):
                with self.assertRaises(SystemExit):
                    diagnostic.main(["--output", str(output)])
            self.assertEqual(target.read_text(), "SYN-preserve")
            self.assertFalse(github_output.exists())

    def test_flash_lite_workflow_is_manual_read_only_and_uploads_one_safe_file(self):
        workflow = json.loads((ROOT / ".github/workflows/flash-lite-availability.yml").read_text())
        self.assertEqual(workflow["on"], {"workflow_dispatch": {}})
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        job = workflow["jobs"]["diagnostic"]
        self.assertEqual(job["if"], "github.ref == 'refs/heads/main'")
        steps = job["steps"]
        self.assertFalse(steps[0]["with"]["persist-credentials"])
        self.assertEqual(steps[1]["with"]["python-version"], "3.12")
        secret_steps = [step for step in steps if "GOOGLE_API_KEY" in step.get("env", {})]
        self.assertEqual(len(secret_steps), 1)
        self.assertEqual(secret_steps[0]["env"], {"GOOGLE_API_KEY": "${{ secrets.GOOGLE_API_KEY }}"})
        self.assertEqual(secret_steps[0]["run"],
            'python .github/scripts/gemini_models_diagnostic.py --target-model models/gemini-3.5-flash-lite --require-target --output "$RUNNER_TEMP/flash-lite-availability.json"')
        uploads = [step for step in steps if step.get("uses", "").startswith("actions/upload-artifact@")]
        self.assertEqual(len(uploads), 1)
        self.assertEqual(uploads[0]["if"], "${{ always() && steps.verify.outputs.safe == 'true' }}")
        self.assertEqual(uploads[0]["with"]["path"], "${{ runner.temp }}/flash-lite-availability.json")
        self.assertEqual(uploads[0]["with"]["name"], "flash-lite-availability")
        for forbidden in ("generateContent", "execute-live", "pilot-run", "curl", "printenv", KEY,
                          "free_tier_campaign", "run_free_tier_phase"):
            self.assertNotIn(forbidden, json.dumps(workflow))
