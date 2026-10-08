"""Static GitHub workflow checks and synthetic archive/preflight fixtures; no APIs."""
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import patch

from revocable_flow.artifact_safety import stage_archive
from revocable_flow.runner import plan_run
from revocable_flow.schema import ValidationError

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/gemini-sanity.yml"
DUMMY_SECRET = "SYN-fixture-secret-not-a-real-key"
EXPECTED_HASH = "17e4da22029b31b280fcf711bec9c88f261f01ee40dd45137a2ad2540ed4c80d"


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Workflow uses the JSON subset of YAML 1.2: exact, dependency-free parsing.
        cls.workflow = json.loads(WORKFLOW.read_text())
        cls.job = cls.workflow["jobs"]["sanity"]
        cls.steps = cls.job["steps"]

    def step(self, step_id):
        return next(s for s in self.steps if s.get("id") == step_id)

    def test_manual_only_main_branch_read_only_checkout(self):
        self.assertEqual(self.workflow["on"], {"workflow_dispatch": {}})
        self.assertEqual(self.workflow["permissions"], {"contents": "read"})
        self.assertEqual(self.job["if"], "github.ref == 'refs/heads/main'")
        checkout = next(s for s in self.steps if s.get("uses", "").startswith("actions/checkout@"))
        self.assertFalse(checkout["with"]["persist-credentials"])
        self.assertEqual(checkout["with"]["fetch-depth"], 0)
        self.assertFalse(self.workflow["concurrency"]["cancel-in-progress"])

    def test_python_install_and_offline_checks_precede_live(self):
        setup = next(s for s in self.steps if s.get("uses", "").startswith("actions/setup-python@"))
        self.assertEqual(setup["with"]["python-version"], "3.12")
        install = next(s for s in self.steps if s.get("run") == "python -m pip install .")
        self.assertLess(self.steps.index(install), self.steps.index(self.step("preflight")))
        self.assertLess(self.steps.index(self.step("preflight")), self.steps.index(self.step("sanity")))
        self.assertTrue(any("unittest discover" in s.get("run", "") for s in self.steps))

    def test_secret_only_from_github_secrets_and_never_shell_expanded(self):
        self.assertNotIn("GOOGLE_API_KEY", self.job["env"])
        for step in self.steps:
            if "GOOGLE_API_KEY" in step.get("env", {}):
                self.assertEqual(step["env"]["GOOGLE_API_KEY"], "${{ secrets.GOOGLE_API_KEY }}")
            script = step.get("run", "")
            for forbidden in ("$GOOGLE_API_KEY", "${GOOGLE_API_KEY}", "printenv", "set -x", "generateContent", "curl"):
                self.assertNotIn(forbidden, script)
        self.assertEqual(self.step("sanity")["env"], {"GOOGLE_API_KEY": "${{ secrets.GOOGLE_API_KEY }}"})
        self.assertNotRegex(WORKFLOW.read_text(), r"AIza[A-Za-z0-9_-]{30,}|sk-[A-Za-z0-9_-]{20,}")

    def test_existing_runner_exact_google_selection_and_hard_caps(self):
        tokens = shlex.split(self.step("sanity")["run"].replace("\\\n", " "))
        self.assertEqual(tokens[:4], ["python", "-m", "revocable_flow.cli", "pilot-run"])
        for flag, value in (("--provider", "google"), ("--model", "gemini-3.8-flash"),
                            ("--condition", "post_update"), ("--scenario-limit", "3"),
                            ("--max-provider-requests", "3"), ("--max-attempts-per-request", "1")):
            self.assertEqual(tokens[tokens.index(flag)+1], value)
        self.assertIn("--execute-live", tokens)
        self.assertIn("--require-complete", tokens)
        self.assertNotIn("--resume", tokens)
        self.assertNotIn("openai", tokens)
        self.assertNotIn("anthropic", tokens)

    def test_upload_only_inspected_staging_directory_even_on_failure(self):
        stage = self.step("artifacts")
        self.assertIn("always()", stage["if"])
        self.assertIn("steps.preflight.outcome == 'success'", stage["if"])
        self.assertIn("revocable_flow.artifact_safety", stage["run"])
        upload = next(s for s in self.steps if s.get("uses", "").startswith("actions/upload-artifact@"))
        self.assertEqual(upload["with"]["name"], "gemini-sanity-results")
        self.assertEqual(upload["with"]["path"], "${{ runner.temp }}/gemini-sanity-results/")
        self.assertIn("steps.artifacts.outputs.safe == 'true'", upload["if"])
        self.assertNotIn("overwrite", upload["with"])

    def test_benchmark_and_request_plan_unchanged_without_network(self):
        self.assertEqual(sha256((ROOT / "data/pilot/scenarios.jsonl").read_bytes()).hexdigest(), EXPECTED_HASH)
        with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")) as network:
            plan = plan_run(ROOT / "configs/pilot_eval.yaml", run_id="gh-gemini-fixture", provider="google",
                            model="gemini-3.8-flash", condition="post_update", scenario_limit=3,
                            max_provider_requests=3, max_attempts_per_request=1)
        network.assert_not_called()
        self.assertEqual(plan.manifest["expected_request_count"], 3)
        self.assertEqual(plan.config["execution"]["repetitions"], 1)

    def test_preflight_missing_key_and_wrong_repetitions_fail_without_network(self):
        spec = importlib.util.spec_from_file_location("gemini_preflight", ROOT / ".github/scripts/gemini_sanity_preflight.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.dict(os.environ, {}, clear=True), patch("urllib.request.urlopen") as network:
            with self.assertRaises(ValidationError):
                module.check("gh-gemini-fixture")
            network.assert_not_called()
        with patch.dict(os.environ, {"GOOGLE_API_KEY": DUMMY_SECRET}), \
             patch.object(module, "plan_run") as planner, patch("urllib.request.urlopen") as network:
            planner.return_value = plan_run(ROOT / "configs/pilot_eval.yaml", run_id="gh-gemini-fixture",
                provider="google", model="gemini-3.8-flash", condition="post_update", scenario_limit=3,
                max_provider_requests=3, max_attempts_per_request=1)
            planner.return_value.manifest["git_dirty"] = False
            planner.return_value.config["execution"]["repetitions"] = 2
            with self.assertRaises(ValidationError):
                module.check("gh-gemini-fixture")
            network.assert_not_called()

    def test_preflight_rejects_bad_hash_or_selection_without_network(self):
        spec = importlib.util.spec_from_file_location("gemini_preflight", ROOT / ".github/scripts/gemini_sanity_preflight.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.dict(os.environ, {"GOOGLE_API_KEY": DUMMY_SECRET}), \
             patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")) as network:
            with patch.object(module, "sha256") as digest:
                digest.return_value.hexdigest.return_value = "changed"
                with self.assertRaises(ValidationError):
                    module.check("gh-gemini-fixture")
            for kind in ("provider", "condition", "count"):
                plan = plan_run(ROOT / "configs/pilot_eval.yaml", run_id="gh-gemini-fixture",
                    provider="google", model="gemini-3.8-flash", condition="post_update", scenario_limit=3,
                    max_provider_requests=3, max_attempts_per_request=1)
                plan.manifest["git_dirty"] = False
                if kind == "provider":
                    plan.manifest["requests"][0]["provider"] = "openai"
                elif kind == "condition":
                    plan.manifest["conditions"] = ["pre_update"]
                else:
                    plan.manifest["expected_request_count"] = 4
                with patch.object(module, "plan_run", return_value=plan), self.assertRaises(ValidationError):
                    module.check("gh-gemini-fixture")
            network.assert_not_called()


class ArchiveTests(unittest.TestCase):
    def fixture(self, root):
        run_id = "gh-gemini-fixture"
        manifest = {"run_id": run_id, "expected_request_count": 3,
                    "execution_limits": {"max_provider_requests": 3, "max_attempts_per_request": 1},
                    "requests": [{"provider": "google", "model": "gemini-3.8-flash", "condition": "post_update",
                                  "execution_index": i, "request_key": f"model-02/post_update/{i:03d}"} for i in (1, 2, 3)]}
        path = root / "manifests" / f"{run_id}.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(manifest))
        record = root / "raw" / run_id / "model-02/post_update/001/attempt-01.response.json"
        record.parent.mkdir(parents=True)
        record.write_text('{"raw_output":"synthetic dummy output only","parse_status":"invalid"}\n')
        return run_id, record

    def test_exact_safe_bytes_copied_and_existing_destination_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            run_id, record = self.fixture(root)
            destination = Path(directory) / "upload"
            self.assertEqual(stage_archive(root, run_id, destination), 2)
            self.assertEqual((destination / record.relative_to(root)).read_bytes(), record.read_bytes())
            with self.assertRaises(ValidationError):
                stage_archive(root, run_id, destination)

    def test_api_key_and_github_token_never_staged(self):
        for name in ("GOOGLE_API_KEY", "GITHUB_TOKEN", "ACTIONS_RUNTIME_TOKEN"):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "results"
                run_id, record = self.fixture(root)
                record.write_text(json.dumps({"raw_output": DUMMY_SECRET}))
                destination = Path(directory) / "upload"
                with patch.dict(os.environ, {name: DUMMY_SECRET}), self.assertRaises(ValidationError):
                    stage_archive(root, run_id, destination)
                self.assertFalse(destination.exists())

    def test_env_file_unexpected_retry_and_symlink_are_rejected(self):
        for kind in ("env", "retry", "symlink"):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "results"
                run_id, record = self.fixture(root)
                if kind == "env":
                    (record.parent / ".env").write_text("DUMMY=value")
                elif kind == "retry":
                    (record.parent / "attempt-02.response.json").write_text("{}")
                else:
                    (record.parent / "unexpected.json").symlink_to(record)
                with self.assertRaises(ValidationError):
                    stage_archive(root, run_id, Path(directory) / "upload")

    def test_credentials_fields_and_other_provider_manifest_are_rejected(self):
        for kind in ("field", "provider"):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "results"
                run_id, record = self.fixture(root)
                if kind == "field":
                    record.write_text('{"headers":{"x-goog-api-key":"dummy"}}')
                else:
                    path = root / "manifests" / f"{run_id}.json"
                    manifest = json.loads(path.read_text())
                    manifest["requests"][0]["provider"] = "openai"
                    path.write_text(json.dumps(manifest))
                with self.assertRaises(ValidationError):
                    stage_archive(root, run_id, Path(directory) / "upload")
