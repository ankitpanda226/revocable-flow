import json
import hashlib
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from revocable_flow.loader import load_predictions, load_scenarios, validate_metadata
from revocable_flow.schema import Action, ValidationError
from revocable_flow.evaluator import evaluate_files, load_config

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/pilot/scenarios.jsonl"


class LoaderTests(unittest.TestCase):
    def test_exact_pilot_balance_and_diversity(self):
        scenarios = load_scenarios(DATA, require_pilot=True)
        self.assertEqual(len(scenarios), 40)
        self.assertEqual(sorted(Counter(s.transition_type for s in scenarios).values()), [10]*4)
        self.assertEqual(Counter(s.expected_action for s in scenarios), {Action.BLOCK:20,Action.REDACT:12,Action.ALLOW:8})
        self.assertEqual(len({s.domain for s in scenarios}), 6)
        self.assertEqual(len({s.scenario_id for s in scenarios}), 40)
        self.assertTrue(all("SYN-" in s.synthetic_private_value for s in scenarios))

    def test_invalid_json_missing_fields_blank_duplicate_and_empty(self):
        first = DATA.read_text().splitlines()[0]
        for content in ("", "\n", "{oops}\n", "{}\n", first+"\n\n", first+"\n"+first+"\n"):
            with self.subTest(content=content[:20]), tempfile.TemporaryDirectory() as folder:
                path = Path(folder)/"bad.jsonl"
                path.write_text(content)
                with self.assertRaises(ValidationError): load_scenarios(path)

    def test_errors_identify_line(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"bad.jsonl"
            path.write_text(DATA.read_text().splitlines()[0]+"\n{}\n")
            with self.assertRaisesRegex(ValidationError, r":2:"): load_scenarios(path)

    def test_duplicate_json_keys_and_nonstandard_constants_fail(self):
        first = DATA.read_text().splitlines()[0]
        for text in ('{"scenario_id":"first",' + first[1:], first.replace('false', 'NaN', 1) if 'false' in first else first.replace('true', 'NaN', 1)):
            with self.subTest(text=text[:30]), tempfile.TemporaryDirectory() as folder:
                path = Path(folder)/"bad.jsonl"
                path.write_text(text + "\n")
                with self.assertRaises(ValidationError): load_scenarios(path)

    def test_pilot_rejects_incomplete_benchmark(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"small.jsonl"
            path.write_text(DATA.read_text().splitlines()[0]+"\n")
            self.assertEqual(len(load_scenarios(path)),1)
            with self.assertRaises(ValidationError): load_scenarios(path,require_pilot=True)

    def test_offline_artifacts_preserve_inputs_and_config(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            predictions=folder/"dummy.jsonl"
            # Synthetic dummy decisions for plumbing tests, never a model experiment.
            predictions.write_text(''.join(json.dumps(dict(scenario_id=s.scenario_id,action=s.expected_action.value,
                disclosed_information=list(s.allowed_information),raw_output="DUMMY ONLY: no model executed"))+"\n"
                for s in load_scenarios(DATA)))
            self.assertEqual(len(load_predictions(predictions)),40)
            result=evaluate_files(DATA,predictions,ROOT/"configs/pilot.yaml",folder/"run")
            self.assertEqual(result["overall"]["accuracy"]["value"],1)
            self.assertEqual((folder/"run/predictions.jsonl").read_bytes(),predictions.read_bytes())
            self.assertEqual((folder/"run/scenarios.jsonl").read_bytes(),DATA.read_bytes())
            manifest=json.loads((folder/"run/manifest.json").read_text())
            self.assertEqual(manifest["configuration"]["model"],"not_run")
            self.assertEqual(manifest["benchmark_metadata"]["version"],"0.2")
            self.assertEqual(set(manifest["artifact_sha256"]),{"scenarios.jsonl","predictions.jsonl","config.yaml","metadata.json"})
            for artifact, expected_hash in manifest["artifact_sha256"].items():
                self.assertEqual(hashlib.sha256((folder/"run"/artifact).read_bytes()).hexdigest(),expected_hash)
            with self.assertRaises(FileExistsError): evaluate_files(DATA,predictions,ROOT/"configs/pilot.yaml",folder/"run")

    def test_config_and_benchmark_mismatch_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            path=folder/"config.yaml"
            path.write_text("{}")
            with self.assertRaises(ValidationError): load_config(path)
            path.write_text((ROOT/"configs/pilot.yaml").read_text())
            with self.assertRaisesRegex(ValidationError,"benchmark.*differ"):
                evaluate_files(DATA,folder/"absent",path,folder/"run")

    def test_exact_existing_ids_and_permission_inventory(self):
        scenarios=load_scenarios(DATA,require_pilot=True)
        categories={"consent_revocation","recipient_change","purpose_change","scope_change"}
        self.assertEqual({s.scenario_id for s in scenarios},{f"{t}-{i:02d}" for t in categories for i in range(1,11)})
        self.assertTrue(all(s.initial_authorizations and s.updated_authorizations for s in scenarios))
        self.assertTrue(all(s.pre_update_expected_action is Action.ALLOW for s in scenarios))
        self.assertTrue(all(s.invalidated_permissions for s in scenarios))
        self.assertEqual(sum(s.salr_eligible for s in scenarios),32)
        kinds=Counter(s.transition_kind.value for s in scenarios)
        self.assertEqual(kinds,{"revoke":24,"narrow":8,"unaffected_control":8})
        for s in scenarios:
            if s.salr_eligible:
                self.assertTrue(s.tested_invalidated_permissions)
                self.assertFalse(s.expected_action is Action.ALLOW)

    def test_matched_family_ids_and_histories(self):
        scenarios=load_scenarios(DATA,require_pilot=True)
        families={}
        for s in scenarios: families.setdefault(s.family_id,[]).append(s)
        self.assertEqual(len(families),32)
        self.assertEqual(sum(len(v)==2 for v in families.values()),8)
        for members in families.values():
            for s in members[1:]:
                self.assertEqual(set(s.initial_authorizations),set(members[0].initial_authorizations))
                self.assertEqual(set(s.updated_authorizations),set(members[0].updated_authorizations))
                self.assertEqual(s.initial_permission,members[0].initial_permission)
                self.assertEqual(s.policy_update,members[0].policy_update)

    def test_metadata_hash_and_count_mismatch_fail(self):
        scenarios=load_scenarios(DATA)
        metadata=validate_metadata(DATA,scenarios)
        self.assertEqual(metadata["version"],"0.2")
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder); path=folder/"scenarios.jsonl"
            path.write_bytes(DATA.read_bytes())
            for changes in ({"sha256":"0"*64},{"scenario_count":41},{"version":"0.1"}):
                (folder/"metadata.json").write_text(json.dumps(metadata|changes))
                with self.assertRaises(ValidationError): validate_metadata(path,scenarios)

    def test_conversations_vary_and_contracts_precede_updates(self):
        scenarios=load_scenarios(DATA,require_pilot=True)
        self.assertGreater(len({len(s.turns) for s in scenarios}),1)
        gaps=[]
        for s in scenarios:
            stages=[t.stage for t in s.turns]
            self.assertLess(stages.index("tool_contract"),stages.index("policy_update"))
            gaps.append(stages.index("final_request")-stages.index("policy_update")-1)
        self.assertEqual(set(gaps),{0,1,2,3})

    def test_metadata_seed_reproduces_the_frozen_id_order(self):
        import random
        scenarios=load_scenarios(DATA,require_pilot=True)
        metadata=validate_metadata(DATA,scenarios)
        expected=sorted(s.scenario_id for s in scenarios)
        random.Random(metadata["ordering_seed"]).shuffle(expected)
        self.assertEqual([s.scenario_id for s in scenarios],expected)

    def test_pilot_rejects_altered_matched_family_history(self):
        rows=[json.loads(line) for line in DATA.read_text().splitlines()]
        member=next(s for s in rows if s["scenario_id"]=="recipient_change-10")
        member["synthetic_private_value"] += " Additional fictitious note."
        member["initial_permission"] += " Additional fictitious note."
        member["turns"][0]["content"] = member["initial_permission"]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"scenarios.jsonl"
            path.write_text(''.join(json.dumps(s)+"\n" for s in rows))
            with self.assertRaisesRegex(ValidationError,"matched family"):
                load_scenarios(path,require_pilot=True)
