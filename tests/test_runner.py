"""Mock execution only. No real credentials or provider/network calls."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from hashlib import sha256
import io
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from revocable_flow.cli import main
from revocable_flow.protocol import canonical_json, load_protocol_config
from revocable_flow.providers import OpenAIProvider
from revocable_flow.providers.base import HTTPReply
from revocable_flow.runner import execute_plan, persist_manifest, plan_run, preview
from revocable_flow.schema import ValidationError

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/pilot_eval.yaml"
DUMMY_KEY = "SYN-fixture-credential-not-a-real-api-key"
GIT = {"commit": "dummy-committed-fixture", "dirty": False}


class RunnerTests(unittest.TestCase):
    def fixture(self, directory, *, enabled=True, provider="openai"):
        root = Path(directory)
        (root / "configs").mkdir(exist_ok=True)
        config = deepcopy(load_protocol_config(CONFIG))
        config["benchmark"]["path"] = str(ROOT / "data/pilot/scenarios.jsonl")
        if enabled:
            entry = next(m for m in config["model_matrix"] if m["provider"] == provider)
            entry.update(model_id="dummy-fixture-model", status="verified", immutable_snapshot=False,
                         notes="Synthetic mock fixture only; NOT an officially verified model.",
                         parameter_support={"temperature": "supported", "top_p": "supported",
                                            "max_output_tokens": "supported", "seed": "unsupported"})
            config["models"] = [{"provider": provider, "model": entry["model_id"]}]
        path = root / "configs/pilot_eval.yaml"
        path.write_text(json.dumps(config), encoding="utf-8")
        return path

    def plan(self, path, **kwargs):
        with patch("revocable_flow.runner._git", return_value=GIT):
            return plan_run(path, run_id="dummy-run", **kwargs)

    def adapter(self, replies=None, text=' {"action":"BLOCK","release_fields":[]}\n'):
        success = HTTPReply(200, {"model": "dummy-reported-snapshot", "status": "completed",
                         "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
                         "usage": {"input_tokens": 11, "output_tokens": 7}}, {"x-request-id": "dummy-id"})
        transport = Mock(return_value=success)
        if replies is not None:
            transport.side_effect = replies + [success]
        return OpenAIProvider(transport=transport), transport

    def execute(self, plan, adapter, **kwargs):
        with patch.dict(os.environ, {"OPENAI_API_KEY": DUMMY_KEY}), patch("revocable_flow.runner._git", return_value=GIT):
            return execute_plan(plan, execute_live=True, adapters={"openai": adapter}, **kwargs)

    def test_actual_matrix_all_unresolved_and_disabled(self):
        plan = plan_run(CONFIG)
        report = preview(plan)
        self.assertEqual(report["scenario_count"], 40)
        self.assertEqual(report["configured_models"], 3)
        self.assertEqual(report["prompts_constructed"], 80)
        self.assertEqual(report["enabled_models"], 0)
        self.assertEqual(report["expected_requests"], 0)
        self.assertEqual(report["expected_requests_if_all_selected_enabled"], 240)
        self.assertTrue(all(m["model_id"] is None for m in plan.manifest["model_matrix"]))
        self.assertEqual(report["cost_note"], "cost estimate unavailable")

    def test_dry_run_blocks_network_and_does_not_create_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self.fixture(directory)
            with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")) as network, \
                 patch("socket.socket", side_effect=AssertionError("network forbidden")), \
                 patch.dict(os.environ, {}, clear=True), redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["pilot-run", "--config", str(config), "--dry-run"]), 0)
            network.assert_not_called()
            self.assertFalse((Path(directory) / "results").exists())
            report = json.loads(output.getvalue())
            self.assertEqual(report["network_requests"], 0)
            self.assertEqual(report["expected_requests"], 80)

    def test_cli_missing_live_flag_and_conflicting_flags_refuse(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")) as network:
            for argv in (["pilot-run"], ["pilot-run", "--dry-run", "--execute-live"]):
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as result:
                    main(argv)
                self.assertEqual(result.exception.code, 2)
            network.assert_not_called()

    def test_direct_execute_requires_literal_true(self):
        plan = plan_run(CONFIG)
        for value in (False, None, "yes"):
            with self.assertRaises(ValidationError):
                execute_plan(plan, execute_live=value)

    def test_unresolved_model_refuses_live_without_network(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")) as network:
            with self.assertRaisesRegex(ValidationError, "no verified"):
                execute_plan(plan_run(CONFIG), execute_live=True)
            network.assert_not_called()

    def test_missing_credentials_do_not_create_results(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = self.plan(self.fixture(directory), scenario_limit=1, condition="post_update")
            with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(ValidationError, "missing credential"):
                execute_plan(plan, execute_live=True)
            self.assertFalse(plan.root.exists())

    def test_dirty_tree_refuses_live(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = self.plan(self.fixture(directory), scenario_limit=1)
            plan.manifest["git_dirty"] = True
            plan.manifest["manifest_hash"] = sha256(canonical_json(
                {k: v for k, v in plan.manifest.items() if k != "manifest_hash"}).encode()).hexdigest()
            with self.assertRaisesRegex(ValidationError, "clean"):
                execute_plan(plan, execute_live=True)

    def test_manifest_is_deterministic_and_prompt_hashes_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self.fixture(directory)
            first, second = self.plan(config), self.plan(config)
            self.assertEqual(first.manifest, second.manifest)
            self.assertEqual(first.manifest["expected_request_count"], 80)
            for prompt in first.manifest["prompt_catalog"]:
                self.assertEqual(prompt["prompt_hash"], sha256(canonical_json(prompt["messages"]).encode()).hexdigest())
                self.assertNotIn("scenario_id", prompt["messages"][1]["content"])
            stripped = dict(first.manifest)
            recorded = stripped.pop("manifest_hash")
            self.assertEqual(recorded, sha256(canonical_json(stripped).encode()).hexdigest())
            self.assertEqual(first.manifest["scenario_order"], second.manifest["scenario_order"])

    def test_selection_and_three_scenario_sanity_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self.fixture(directory)
            plan = self.plan(config, provider="openai", model="dummy-fixture-model", scenario_limit=3, condition="post_update")
            self.assertEqual(plan.manifest["expected_request_count"], 3)
            self.assertEqual(len(plan.manifest["prompt_catalog"]), 3)
            self.assertFalse(plan.manifest["primary_complete_design"])
            self.assertEqual(plan.manifest["conditions"], ["post_update"])
            with self.assertRaises(ValidationError):
                self.plan(config, model="unconfigured")
            with self.assertRaises(ValidationError):
                self.plan(config, scenario_limit=41)

    def test_preview_pricing_is_optional_and_explicit_approximation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.fixture(directory)
            config = json.loads(path.read_text())
            config["pricing"] = {"input_per_million": 1, "output_per_million": 2}
            path.write_text(json.dumps(config))
            report = preview(self.plan(path, provider="openai", scenario_limit=1, condition="post_update"))
            self.assertGreater(report["approximate_cost_if_all_enabled"], 0)
            self.assertIn("no billing guarantee", report["cost_note"])

    def test_matrix_rejects_guessed_or_inconsistent_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.fixture(directory)
            original = json.loads(path.read_text())
            for key, value in (("model_id", None), ("documentation_source", "https://unofficial.example/models"),
                               ("immutable_snapshot", None), ("verification_date", "not-date"),
                               ("status", "guessed")):
                config = deepcopy(original)
                config["model_matrix"][0][key] = value
                path.write_text(json.dumps(config))
                with self.subTest(key=key), self.assertRaises(ValidationError):
                    self.plan(path)

    def test_fully_enabled_synthetic_matrix_counts_and_same_order_across_models(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.fixture(directory, enabled=False)
            config = json.loads(path.read_text())
            for entry in config["model_matrix"]:
                entry.update(model_id="dummy-fixture", status="verified", immutable_snapshot=False,
                    notes="Synthetic unit fixture, not official verification.",
                    parameter_support={"temperature": "supported", "top_p": "supported",
                                       "max_output_tokens": "supported", "seed": "unsupported"})
            config["models"] = [{"provider": e["provider"], "model": e["model_id"]} for e in config["model_matrix"]]
            path.write_text(json.dumps(config))
            plan = self.plan(path)
            self.assertEqual(plan.manifest["expected_request_count"], 240)
            orders = [[(r["execution_index"], r["condition"]) for r in plan.manifest["requests"]
                       if r["provider"] == p] for p in ("openai", "google", "anthropic")]
            self.assertEqual(orders[0], orders[1])
            self.assertEqual(orders[1], orders[2])

    def test_complete_paired_mock_run_uses_frozen_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = self.plan(self.fixture(directory), provider="openai")
            adapter, transport = self.adapter()
            summary = self.execute(plan, adapter)
            self.assertTrue(summary["complete"])
            self.assertTrue(summary["primary_complete_design"])
            self.assertEqual(summary["planned"], 80)
            self.assertEqual(transport.call_count, 80)
            overall = summary["metrics_by_model"]["openai"]["overall"]
            self.assertEqual(overall["post_action_accuracy"]["numerator"], 20)
            self.assertEqual(overall["post_action_accuracy"]["denominator"], 40)
            self.assertEqual(overall["pre_action_accuracy"]["numerator"], 0)
            self.assertEqual(overall["salr"]["denominator"], 32)
            self.assertEqual(overall["over_refusal_rate"]["denominator"], 20)
            self.assertEqual(len(list((plan.root / "raw").rglob("*.response.json"))), 80)

    def test_required_unsupported_parameter_refuses_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.fixture(directory)
            config = json.loads(path.read_text())
            config["model_matrix"][0]["parameter_support"]["top_p"] = "unsupported"
            path.write_text(json.dumps(config))
            with self.assertRaisesRegex(ValidationError, "required generation"):
                self.plan(path)

    def test_manifest_precedes_first_mock_request_and_no_gold_in_raw(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = self.plan(self.fixture(directory), scenario_limit=1, condition="post_update")
            adapter, transport = self.adapter()
            success = transport.return_value
            def reply(*args):
                self.assertTrue((plan.root / "manifests/dummy-run.json").exists())
                self.assertTrue(list((plan.root / "raw").rglob("*.started.json")))
                return success
            transport.side_effect = reply
            summary = self.execute(plan, adapter)
            self.assertEqual(summary["completed"], 1)
            self.assertNotIn("metrics_by_model", summary)  # Partial sanity test, not primary.
            raw = json.loads(next((plan.root / "raw").rglob("*.response.json")).read_text())
            for key in ("expected_action", "pre_update_expected_action", "family_id", "rationale", "scenario_id"):
                self.assertNotIn(key, raw)
            self.assertEqual(raw["reported_model"], "dummy-reported-snapshot")
            self.assertEqual(raw["requested_model"], "dummy-fixture-model")
            self.assertEqual(raw["requested_parameters"]["seed"], 20261007)
            self.assertIsNone(raw["parameters"]["seed"])
            self.assertEqual(raw["unsupported_parameters"], ["seed"])
            self.assertEqual(raw["finish_reason"], "completed")
            self.assertEqual(raw["usage"]["input_tokens"], 11)
            self.assertEqual((plan.root / plan.manifest["benchmark_artifact"]).read_bytes(),
                             (ROOT / "data/pilot/scenarios.jsonl").read_bytes())
            for path in plan.root.rglob("*.json"):
                self.assertNotIn(DUMMY_KEY, path.read_text())

    def test_invalid_response_preserved_and_never_semantically_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = self.plan(self.fixture(directory), scenario_limit=1, condition="post_update")
            text = "bad JSON\n\t{\r\n"
            adapter, transport = self.adapter(text=text)
            summary = self.execute(plan, adapter)
            self.assertTrue(summary["complete"])
            transport.assert_called_once()
            raw = json.loads(next((plan.root / "raw").rglob("*.response.json")).read_text())
            self.assertEqual(raw["raw_output"], text)
            self.assertEqual(raw["parse_status"], "invalid")
            self.execute(plan, adapter, resume=True)
            transport.assert_called_once()

    def test_retry_failure_preservation_and_frozen_backoff(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = self.plan(self.fixture(directory), scenario_limit=1, condition="post_update")
            adapter, transport = self.adapter([HTTPReply(429, None), HTTPReply(503, None)])
            sleep = Mock()
            summary = self.execute(plan, adapter, sleep=sleep)
            self.assertEqual(summary["completed"], 1)
            self.assertEqual(transport.call_count, 3)
            self.assertEqual([c.args[0] for c in sleep.call_args_list], [2, 4])
            records = sorted((plan.root / "raw").rglob("*.response.json"))
            self.assertEqual(len(records), 3)
            first = json.loads(records[0].read_text())
            self.assertEqual(first["parse_status"], "provider_error")
            self.assertEqual(first["provider_error"]["http_status"], 429)
            self.assertIsNone(first["raw_output"])
            self.assertEqual([json.loads(p.read_text())["attempt"] for p in records], [1, 2, 3])

    def test_retry_after_is_honored_and_long_delay_deferred(self):
        for retry_after, expected_calls in (("6", 2), ("61", 1)):
            with tempfile.TemporaryDirectory() as directory:
                plan = self.plan(self.fixture(directory), scenario_limit=1, condition="post_update")
                adapter, transport = self.adapter([HTTPReply(429, None, {"Retry-After": retry_after})])
                sleep = Mock()
                summary = self.execute(plan, adapter, sleep=sleep)
                self.assertEqual(transport.call_count, expected_calls)
                if retry_after == "6":
                    sleep.assert_called_once_with(6)
                else:
                    sleep.assert_not_called()
                    self.assertFalse(summary["complete"])

    def test_deferred_resume_after_retry_after_expiry_keeps_attempt_history(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = self.plan(self.fixture(directory), scenario_limit=1, condition="post_update")
            adapter, transport = self.adapter([HTTPReply(429, None, {"Retry-After": "61"})])
            self.assertFalse(self.execute(plan, adapter, sleep=Mock())["complete"])
            future = (datetime.now(timezone.utc) + timedelta(seconds=120)).isoformat()
            sleep = Mock()
            with patch("revocable_flow.runner._now", return_value=future):
                self.assertTrue(self.execute(plan, adapter, resume=True, sleep=sleep)["complete"])
            self.assertEqual(transport.call_count, 2)
            sleep.assert_called_once_with(2)
            self.assertEqual(len(list((plan.root / "raw").rglob("*.response.json"))), 2)

    def test_live_cli_shows_cost_count_preview_before_refusing_unresolved_matrix(self):
        with redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()), \
                patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")) as network:
            with self.assertRaises(SystemExit):
                main(["pilot-run", "--config", str(CONFIG), "--execute-live", "--run-id", "not-executed"])
        self.assertIn('"execution_preview"', output.getvalue())
        self.assertIn('"expected_requests_if_all_selected_enabled": 240', output.getvalue())
        network.assert_not_called()

    def test_nonretryable_and_exhausted_failure_do_not_restart_attempt_count(self):
        for statuses in ([401], [503, 503, 503]):
            with tempfile.TemporaryDirectory() as directory:
                plan = self.plan(self.fixture(directory), scenario_limit=1, condition="post_update")
                adapter, transport = self.adapter([HTTPReply(s, None) for s in statuses])
                summary = self.execute(plan, adapter, sleep=Mock())
                self.assertFalse(summary["complete"])
                self.assertEqual(transport.call_count, len(statuses))
                summary = self.execute(plan, adapter, resume=True, sleep=Mock())
                self.assertEqual(transport.call_count, len(statuses))
                self.assertNotIn("metrics_by_model", summary)

    def test_resume_does_not_duplicate_completed_response_or_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = self.plan(self.fixture(directory), scenario_limit=1, condition="post_update")
            adapter, transport = self.adapter()
            self.execute(plan, adapter)
            path = next((plan.root / "raw").rglob("*.response.json"))
            before = path.read_bytes()
            self.execute(plan, adapter, resume=True)
            transport.assert_called_once()
            self.assertEqual(path.read_bytes(), before)
            with self.assertRaises(ValidationError):
                self.execute(plan, adapter)  # Existing run requires explicit resume.
            transport.assert_called_once()

    def test_crash_after_start_is_ambiguous_and_never_automatically_repeated(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = self.plan(self.fixture(directory), scenario_limit=1, condition="post_update")
            adapter, transport = self.adapter()
            transport.side_effect = KeyboardInterrupt()
            with self.assertRaises(KeyboardInterrupt):
                self.execute(plan, adapter)
            transport.side_effect = None
            summary = self.execute(plan, adapter, resume=True)
            transport.assert_called_once()
            self.assertEqual(len(summary["ambiguous_attempts"]), 1)
            self.assertFalse(summary["complete"])

    def test_resume_recovers_missing_parsed_record_without_provider_call(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = self.plan(self.fixture(directory), scenario_limit=1, condition="post_update")
            adapter, transport = self.adapter()
            self.execute(plan, adapter)
            path = next(p for p in (plan.root / "parsed").rglob("*.json") if "model-01" in p.parts)
            path.unlink()
            self.execute(plan, adapter, resume=True)
            self.assertTrue(path.exists())
            transport.assert_called_once()

    def test_changed_manifest_refuses_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.fixture(directory)
            first = self.plan(path, scenario_limit=1, condition="post_update")
            persist_manifest(first)
            changed = self.plan(path, scenario_limit=2, condition="post_update")
            with self.assertRaises(ValidationError):
                persist_manifest(changed, resume=True)

    def test_credentials_echoed_in_output_are_not_written_or_repaired(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = self.plan(self.fixture(directory), scenario_limit=1, condition="post_update")
            adapter, transport = self.adapter(text=DUMMY_KEY)
            with self.assertRaisesRegex(ValidationError, "credential material"):
                self.execute(plan, adapter)
            transport.assert_called_once()
            for path in plan.root.rglob("*.json"):
                self.assertNotIn(DUMMY_KEY, path.read_text())
            self.assertFalse(list((plan.root / "raw").rglob("*.response.json")))

    def test_artifact_path_rejects_symlinks_and_unsafe_run_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.fixture(directory)
            for run_id in ("../bad", "a/b", "", "x" * 65):
                with self.assertRaises(ValidationError):
                    plan_run(path, run_id=run_id)
            (Path(directory) / "results").symlink_to(ROOT)
            with self.assertRaises(ValidationError):
                self.plan(path)

    def test_explicit_dry_manifest_persistence_is_local_and_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.fixture(directory, enabled=False)
            with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")) as network, \
                    redirect_stdout(io.StringIO()):
                main(["pilot-run", "--config", str(path), "--dry-run", "--write-manifest", "--run-id", "dummy-preview"])
            network.assert_not_called()
            self.assertTrue((Path(directory) / "results/manifests/dummy-preview.json").exists())
            self.assertFalse((Path(directory) / "results/raw").exists())
