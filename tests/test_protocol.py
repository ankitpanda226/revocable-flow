"""Synthetic dummy outputs only: no provider SDK or model calls."""
from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from revocable_flow.protocol import (
    BENCHMARK_COMMIT, BENCHMARK_HASH, SYSTEM_PROMPT, build_messages, build_transcript,
    canonical_json, condition_order, load_protocol_benchmark, load_protocol_config,
    make_raw_record, parse_output, require_frozen_models, scenario_order, score_output,
    summarize_scores, write_raw_record,
)
from revocable_flow.schema import Action, ValidationError

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/pilot_eval.yaml"
DATA = ROOT / "data/pilot/scenarios.jsonl"


class ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenarios = load_protocol_benchmark(CONFIG)
        cls.config = load_protocol_config(CONFIG)
        cls.block = next(s for s in cls.scenarios if s.expected_action is Action.BLOCK)
        cls.redact = next(s for s in cls.scenarios if s.expected_action is Action.REDACT)
        cls.allow = next(s for s in cls.scenarios if s.expected_action is Action.ALLOW)

    def output(self, scenario, action, fields):
        return parse_output(json.dumps({"action": action, "release_fields": fields}), scenario)

    def gold(self, scenario, condition):
        before = condition == "pre_update"
        fields = [f.name for f in scenario.requested_fields
                  if scenario.permission_for(f) in scenario.allowed_permissions(before=before)]
        action = scenario.pre_update_expected_action if before else scenario.expected_action
        return self.output(scenario, action.value, fields)

    def scores(self):
        return [score_output(s, c, self.gold(s, c)) for s in self.scenarios
                for c in ("pre_update", "post_update")]

    def config_change(self, mutate):
        config = deepcopy(self.config)
        mutate(config)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text(json.dumps(config), encoding="utf-8")
            return load_protocol_config(path)

    def test_benchmark_hash_unchanged(self):
        self.assertEqual(sha256(DATA.read_bytes()).hexdigest(), BENCHMARK_HASH)
        # Also assert bytes equal the frozen original Git blob, not just a metadata claim.
        original = subprocess.run(["git", "show", f"{BENCHMARK_COMMIT}:data/pilot/scenarios.jsonl"],
                                  cwd=ROOT, check=True, capture_output=True).stdout
        self.assertEqual(DATA.read_bytes(), original)

    def test_frozen_design_counts(self):
        self.assertEqual(len(self.scenarios), 40)
        self.assertEqual(Counter(s.transition_type.value for s in self.scenarios),
                         {"consent_revocation": 10, "recipient_change": 10,
                          "purpose_change": 10, "scope_change": 10})
        self.assertEqual(Counter(s.expected_action.value for s in self.scenarios),
                         {"BLOCK": 20, "REDACT": 12, "ALLOW": 8})
        self.assertEqual(sum(s.salr_eligible for s in self.scenarios), 32)
        self.assertEqual(len({s.family_id for s in self.scenarios}), 32)
        self.assertTrue(all(s.pre_update_expected_action is Action.ALLOW for s in self.scenarios))
        self.assertTrue(all(not any(s.permission_for(f) in s.allowed_permissions()
                                   for f in s.requested_fields)
                            for s in self.scenarios if s.expected_action is Action.BLOCK))

    def test_default_config_and_model_gate(self):
        self.assertEqual(self.config["models"], [])
        with self.assertRaises(ValidationError):
            require_frozen_models(self.config)

    def test_future_model_list_schema(self):
        def legacy_config(c):
            c.pop("model_matrix", None)
            c.update(models=[{"provider": "dummy", "model": "dummy-model"}])
        config = self.config_change(legacy_config)
        require_frozen_models(config)  # Necessary gate only; does not execute anything.

    def test_config_rejects_drift_and_credentials(self):
        mutations = [
            lambda c: c.update(api_key="dummy"),
            lambda c: c["benchmark"].update(hash="changed"),
            lambda c: c["benchmark"].update(commit="changed"),
            lambda c: c["execution"].update(seed=True),
            lambda c: c["execution"].update(temperature=True),
            lambda c: c["execution"].update(repetitions=2),
            lambda c: c.update(models={}),
            lambda c: c.update(models=[{"provider": "dummy", "model": "dummy", "token": "dummy"}]),
            lambda c: c.update(models=[{"provider": "dummy", "model": "dummy"}] * 2),
            lambda c: c.update(conditions=["post_update"]),
            lambda c: c.update(ablation={"enabled": True}),
            lambda c: c.update(ablation={"enabled": 0}),
            lambda c: c["retry"].update(backoff_seconds=[True, 4]),
            lambda c: c["retry"].update(max_attempts=9),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(ValidationError):
                self.config_change(mutation)

    def test_config_rejects_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text('{"models":[],"models":[]}', encoding="utf-8")
            with self.assertRaises(ValidationError):
                load_protocol_config(path)

    def test_benchmark_loader_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scenarios.jsonl").write_bytes(DATA.read_bytes() + b"\n")
            config = deepcopy(self.config)
            config["benchmark"]["path"] = "scenarios.jsonl"
            path = root / "config.yaml"
            path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "hash mismatch"):
                load_protocol_benchmark(path)

    def test_post_input_is_only_conversation(self):
        prohibited = {"expected_action", "pre_update_expected_action", "rationale", "salr_eligible",
                      "family_id", "transition_kind", "violation_type", "scenario_id", "annotations",
                      "initial_authorizations", "updated_authorizations", "stage", "turn_id"}
        for scenario in self.scenarios:
            messages = build_messages(scenario, "post_update")
            self.assertEqual(messages[0], {"role": "system", "content": SYSTEM_PROMPT})
            transcript = json.loads(messages[1]["content"])
            self.assertEqual(transcript, scenario.conversation())
            self.assertTrue(all(set(t) == {"role", "content"} for t in transcript))
            self.assertTrue(all(not (set(t) & prohibited) for t in transcript))
            self.assertNotIn(scenario.scenario_id, canonical_json(messages))
            self.assertNotIn(scenario.family_id, canonical_json(messages))
            self.assertNotIn(scenario.rationale, canonical_json(messages))

    def test_prompt_document_matches_exact_string(self):
        document = (ROOT / "docs/prompting_protocol.md").read_text(encoding="utf-8")
        block = document.split("```text\n", 1)[1].split("\n```", 1)[0]
        self.assertEqual(SYSTEM_PROMPT, block)
        self.assertNotIn("RevocableFlow", SYSTEM_PROMPT)
        self.assertNotIn("stale authorization", SYSTEM_PROMPT.lower())
        for category in {s.transition_type.value for s in self.scenarios}:
            self.assertNotIn(category, SYSTEM_PROMPT)

    def test_pre_prefix_and_identical_request(self):
        for scenario in self.scenarios:
            update = next(i for i, t in enumerate(scenario.turns) if t.stage == "policy_update")
            visible = scenario.conversation()
            pre = build_transcript(scenario, "pre_update")
            self.assertEqual(pre, visible[:update] + [visible[-1]])
            self.assertNotIn(visible[update], pre)
            self.assertEqual(pre[-1], visible[-1])
            self.assertTrue(any(t.stage == "tool_contract" for t in scenario.turns[:update]))

    def test_recent_context_literal_selection(self):
        for scenario in self.scenarios:
            recent = build_transcript(scenario, "post_update", history="recent_context")
            selected = [i for i, t in enumerate(scenario.turns)
                        if t.stage in {"tool_contract", "policy_update", "final_request"}]
            self.assertEqual(recent, [scenario.conversation()[i] for i in selected])
            self.assertEqual(len(recent), 3)
        with self.assertRaises(ValidationError):
            build_transcript(self.allow, "pre_update", history="recent_context")
        with self.assertRaises(ValidationError):
            build_transcript(self.allow, "unknown")

    def test_order_is_fixed_input_order_independent(self):
        order = scenario_order(self.scenarios)
        self.assertEqual(order, scenario_order(list(reversed(self.scenarios))))
        self.assertEqual(order, self.scenarios)  # Frozen dataset was shuffled by this rule.
        self.assertNotEqual(order, scenario_order(self.scenarios, seed=1))
        self.assertEqual(Counter(condition_order(i)[0] for i in range(1, 41)),
                         {"pre_update": 20, "post_update": 20})
        with self.assertRaises(ValidationError):
            scenario_order([self.allow, self.allow])
        with self.assertRaises(ValidationError):
            condition_order(True)

    def test_invalid_output_is_deterministic_and_unmodified(self):
        malformed = ["not json", "```json\n{}\n```", '{"action":', "{}{}", "NaN", '{"action":1e999,"release_fields":[]}',
                     '{"action":"ALLOW","action":"BLOCK","release_fields":[]}']
        for text in malformed:
            with self.subTest(text=text):
                first = parse_output(text, self.allow)
                self.assertEqual(first, parse_output(text, self.allow))
                self.assertEqual(first.raw_output, text)
                self.assertFalse(first.valid)
                self.assertEqual(first.errors, ("invalid_json",))

    def test_invalid_response_schema(self):
        bad = [[], {}, {"action": "ALLOW"}, {"action": "OTHER", "release_fields": []},
               {"action": ["ALLOW"], "release_fields": []},
               {"action": "ALLOW", "release_fields": "field"},
               {"action": "ALLOW", "release_fields": [1]},
               {"action": "ALLOW", "release_fields": [""]},
               {"action": "ALLOW", "release_fields": ["unknown"]},
               {"action": "ALLOW", "release_fields": [], "rationale": "dummy"}]
        field = self.allow.requested_fields[0].name
        bad.append({"action": "ALLOW", "release_fields": [field, field]})
        for decoded in bad:
            with self.subTest(decoded=decoded):
                output = parse_output(json.dumps(decoded), self.allow)
                self.assertFalse(output.valid)
                self.assertEqual(output.parsed_output, decoded)

    def test_valid_json_whitespace_is_preserved(self):
        text = ' \n{"action":"BLOCK","release_fields":[]}\t'
        parsed = parse_output(text, self.block)
        self.assertTrue(parsed.valid)
        self.assertEqual(parsed.raw_output, text)

    def test_all_gold_fields_score_correctly(self):
        for scenario in self.scenarios:
            for condition in ("pre_update", "post_update"):
                score = score_output(scenario, condition, self.gold(scenario, condition))
                self.assertTrue(score.joint_correct)
                self.assertFalse(score.privacy_violation)
                self.assertFalse(score.stale_leak)
                self.assertFalse(score.over_refusal)

    def test_redact_label_can_still_leak(self):
        output = self.output(self.redact, "REDACT", list(self.redact.final_request_fields))
        score = score_output(self.redact, "post_update", output)
        self.assertTrue(score.action_correct)
        self.assertTrue(score.privacy_violation)
        self.assertTrue(score.stale_leak)
        self.assertFalse(score.field_correct)
        self.assertFalse(score.consistent)

    def test_redact_proper_subset_can_leak_and_omit(self):
        scenario = self.redact
        forbidden = next(f.name for f in scenario.requested_fields
                         if scenario.permission_for(f) not in scenario.allowed_permissions())
        output = self.output(scenario, "REDACT", [forbidden])
        score = score_output(scenario, "post_update", output)
        self.assertTrue(score.action_correct)
        self.assertTrue(score.consistent)
        self.assertTrue(score.privacy_violation)
        self.assertTrue(score.stale_leak)
        self.assertTrue(score.over_refusal)
        self.assertFalse(score.field_correct)

    def test_allow_authorizes_request_even_with_empty_fields(self):
        output = self.output(self.block, "ALLOW", [])
        score = score_output(self.block, "post_update", output)
        self.assertTrue(score.privacy_violation)
        self.assertTrue(score.stale_leak)
        self.assertFalse(score.consistent)
        self.assertTrue(score.field_correct)  # Empty allowed set; keep action separate.
        self.assertFalse(score.joint_correct)

    def test_block_can_leak_and_refuse_simultaneously(self):
        output = self.output(self.redact, "BLOCK", list(self.redact.final_request_fields))
        score = score_output(self.redact, "post_update", output)
        self.assertTrue(score.privacy_violation)
        self.assertFalse(score.action_correct)
        self.assertFalse(score.consistent)
        output = self.output(self.redact, "BLOCK", [])
        self.assertTrue(score_output(self.redact, "post_update", output).over_refusal)

    def test_allow_with_empty_fields_is_over_refusal_not_field_success(self):
        score = score_output(self.allow, "post_update", self.output(self.allow, "ALLOW", []))
        self.assertTrue(score.action_correct)
        self.assertTrue(score.over_refusal)
        self.assertFalse(score.joint_correct)

    def test_unsolicited_known_forbidden_field_control(self):
        for scenario in self.scenarios:
            extras = [f.name for f in scenario.tool_contract.fields
                      if f.name not in scenario.final_request_fields
                      and scenario.permission_for(f) not in scenario.allowed_permissions()]
            if scenario.expected_action is Action.ALLOW and extras:
                output = self.output(scenario, "ALLOW", list(scenario.final_request_fields) + extras)
                self.assertTrue(output.valid)
                score = score_output(scenario, "post_update", output)
                self.assertTrue(score.privacy_violation)
                self.assertFalse(score.stale_leak)
                self.assertFalse(scenario.salr_eligible)
                self.assertFalse(score.field_correct)
                return
        self.fail("frozen pilot must contain a control with a forbidden contract extra")

    def test_invalid_score_unknown_not_safe(self):
        score = score_output(self.allow, "post_update", parse_output("broken", self.allow))
        self.assertFalse(score.action_correct)
        self.assertFalse(score.field_correct)
        self.assertIsNone(score.privacy_violation)
        self.assertIsNone(score.over_refusal)
        self.assertIsNone(score.stale_leak)

    def test_dummy_perfect_paired_summary(self):
        result = summarize_scores(self.scenarios, self.scores())
        overall = result["overall"]
        self.assertEqual(overall["post_action_accuracy"], {"numerator": 40, "denominator": 40, "rate": 1})
        self.assertEqual(overall["salr"]["denominator"], 32)
        self.assertEqual(overall["over_refusal_rate"]["denominator"], 20)
        self.assertEqual(overall["transition_adaptation_rate"]["denominator"], 32)
        self.assertEqual(overall["unaffected_control_retention_rate"]["denominator"], 8)
        self.assertEqual(len(result["by_family_id"]), 32)
        for group in result["by_transition_type"].values():
            self.assertEqual(group["post_action_accuracy"]["denominator"], 10)
            self.assertEqual(group["salr"]["denominator"], 8)
        self.assertIsNone(result["by_expected_action"]["ALLOW"]["salr"]["rate"])

    def test_dummy_always_initial_allow_summary(self):
        scores = [score_output(s, c, self.gold(s, "pre_update")) for s in self.scenarios
                  for c in ("pre_update", "post_update")]
        overall = summarize_scores(self.scenarios, scores)["overall"]
        self.assertEqual(overall["pre_action_accuracy"]["rate"], 1)
        self.assertEqual(overall["post_action_accuracy"]["numerator"], 8)
        self.assertEqual(overall["salr"]["numerator"], 32)
        self.assertEqual(overall["privacy_violation_rate"]["numerator"], 32)
        self.assertEqual(overall["transition_adaptation_rate"]["rate"], 0)
        self.assertEqual(overall["unaffected_control_retention_rate"]["rate"], 1)

    def test_dummy_invalid_bounds_and_adaptation(self):
        scores = self.scores()
        target = self.redact
        scores = [score_output(target, "post_update", parse_output("broken", target))
                  if s.scenario_id == target.scenario_id and s.condition == "post_update" else s
                  for s in scores]
        overall = summarize_scores(self.scenarios, scores)["overall"]
        self.assertEqual(overall["post_action_accuracy"]["numerator"], 39)
        self.assertEqual(overall["post_invalid_rate"]["numerator"], 1)
        self.assertEqual(overall["salr"]["rate"], 0)
        self.assertEqual(overall["salr"]["unknown"], 1)
        self.assertEqual(overall["salr"]["upper_bound"], 1 / 32)
        self.assertEqual(overall["salr"]["valid_only"]["denominator"], 31)
        self.assertEqual(overall["transition_adaptation_rate"]["numerator"], 31)
        self.assertEqual(overall["over_refusal_rate"]["upper_bound"], 1 / 20)

    def test_summary_rejects_missing_duplicate_unknown_pairs(self):
        scores = self.scores()
        for bad in (scores[:-1], scores + [scores[0]], [], scores[1:] + [scores[-1]]):
            with self.assertRaises(ValidationError):
                summarize_scores(self.scenarios, bad)

    def record(self, text="malformed\n\t{", **changes):
        args = dict(scenario=self.allow, raw_output=text, execution_index=1, provider="dummy",
                    model="dummy-model", timestamp="2026-10-07T12:00:00Z", condition="post_update",
                    parameters={"temperature": 0, "top_p": 1, "max_output_tokens": 512, "seed": None})
        args.update(changes)
        return make_raw_record(**args)

    def test_raw_artifact_preserves_malformed_text_and_does_not_overwrite(self):
        text = "malformed\n\t{ \r\n"
        record = self.record(text)
        self.assertEqual(record["raw_output"], text)
        self.assertEqual(record["parse_status"], "invalid")
        self.assertIsNone(record["parsed_output"])
        self.assertEqual(record["benchmark_commit"], BENCHMARK_COMMIT)
        self.assertEqual(record["benchmark_hash"], BENCHMARK_HASH)
        self.assertEqual(record["prompt_hash"], sha256(canonical_json(record["messages"]).encode()).hexdigest())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "response.json"
            write_raw_record(path, record)
            decoded = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(decoded["raw_output"], text)
            with self.assertRaises(FileExistsError):
                write_raw_record(path, record)
            self.assertEqual(decoded, json.loads(path.read_text(encoding="utf-8")))

    def test_raw_artifact_keeps_decoded_invalid_schema(self):
        record = self.record('{"action":"OTHER","release_fields":[]}')
        self.assertEqual(record["parsed_output"]["action"], "OTHER")
        self.assertEqual(record["parse_status"], "invalid")

    def test_raw_schema_rejects_credential_parameter_and_bad_provenance(self):
        for args in ({"execution_index": 0}, {"execution_index": 41}, {"provider": ""},
                     {"timestamp": "2026-10-07T12:00:00"}, {"timestamp": "bad"},
                     {"condition": "unknown"}, {"latency_ms": -1}, {"latency_ms": float("nan")},
                     {"parameters": {"api_key": "dummy"}}, {"request_id": {}},
                     {"parameters": {"temperature": False, "top_p": 1, "max_output_tokens": 512, "seed": None}}):
            with self.subTest(args=args), self.assertRaises(ValidationError):
                self.record(**args)

    def test_artifacts_ignored(self):
        result = subprocess.run(["git", "check-ignore", "results/raw/example.json", "results/parsed/example.json",
                                 "results/summaries/example.json"], cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertEqual(len(result.stdout.splitlines()), 3)


if __name__ == "__main__":
    unittest.main()
