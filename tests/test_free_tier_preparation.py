"""Unresolved model preparation must remain offline and fail closed."""
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from revocable_flow.protocol import build_messages, load_protocol_config, canonical_json
from revocable_flow.runner import plan_run
from revocable_flow.schema import ValidationError
from revocable_flow.providers import GoogleProvider

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'configs/free_tier_pilot_v1.yaml'
POLICY=ROOT/'configs/free_tier_policy_v1.json'
WORKFLOW=ROOT/'.github/workflows/free-tier-pilot.yml'
spec=importlib.util.spec_from_file_location('free_tier_preflight',ROOT/'.github/scripts/free_tier_preflight.py')
preflight=importlib.util.module_from_spec(spec);spec.loader.exec_module(preflight)


class FreeTierPreparationTests(unittest.TestCase):
    def test_unverified_required_parameters_never_reach_transport(self):
        from unittest.mock import Mock
        transport=Mock(side_effect=AssertionError('provider call forbidden'))
        config=load_protocol_config(CONFIG)
        with patch.dict('os.environ',{},clear=True):
            response=GoogleProvider(transport=transport).generate(
                [{'role':'system','content':'SYN offline fixture'},
                 {'role':'user','content':'SYN offline fixture'}],
                model='gemini-3.5-flash-lite',parameters={k:config['execution'][k]
                    for k in ('temperature','top_p','max_output_tokens','seed')},
                supported_parameters=set(),execute_live=True)
        self.assertEqual(response.error.category,'unsupported_required_parameters')
        transport.assert_not_called()

    def test_model_and_free_tier_remain_unresolved_not_invented(self):
        config=load_protocol_config(CONFIG); policy=json.loads(POLICY.read_text())
        self.assertEqual(config['models'],[])
        self.assertEqual(len(config['model_matrix']),1)
        model=config['model_matrix'][0]
        self.assertEqual(model['provider'],'google');self.assertEqual(model['model_id'],'gemini-3.5-flash-lite')
        self.assertEqual(model['status'],'disabled')
        self.assertTrue(all(v=='unresolved' for v in model['parameter_support'].values()))
        self.assertEqual(policy['model_id'],'gemini-3.5-flash-lite');self.assertEqual(policy['verification_date'],'2026-10-08')
        self.assertTrue(policy['free_tier_verified']);self.assertFalse(policy['execution_enabled'])
        self.assertTrue(policy['available_to_key_verified']);self.assertTrue(policy['generate_content_verified'])
        observation=policy['evidence']['availability_verification']
        self.assertEqual(observation['reported_result']['requested_model'],'models/gemini-3.5-flash-lite')
        self.assertEqual(observation['report_received_date'],'2026-10-08')
        self.assertEqual(observation['github_actions_run_url'],'https://github.com/ankitpanda226/revocable-flow/actions/runs/37854150199')
        self.assertEqual(observation['verification_date'],'2026-10-08')
        self.assertEqual(observation['verification_date_timezone'],'UTC')
        self.assertFalse(policy['json_output_verified'])
        tier_path=ROOT/policy['evidence']['account_tier_file']
        self.assertEqual(sha256(tier_path.read_bytes()).hexdigest(),policy['evidence']['account_tier_sha256'])
        self.assertEqual(json.loads(tier_path.read_text())['tier'],'Free')
        self.assertFalse(json.loads(tier_path.read_text())['secret_project_binding_confirmed'])
        self.assertFalse(policy['parameter_support_verified'])
        self.assertEqual(policy['budget']['maximum_total_usd'],4)
        self.assertIsNone(policy['budget']['verified_spend_usd'])

    def test_deterministic_existing_runner_preview_zero_live_scope(self):
        with patch('urllib.request.urlopen',side_effect=AssertionError('network forbidden')) as network:
            first=plan_run(CONFIG);second=plan_run(CONFIG)
        network.assert_not_called()
        self.assertEqual(first.manifest['requests'],[])
        self.assertEqual(first.manifest['expected_request_count'],0)
        self.assertEqual(first.manifest['expected_if_all_selected_enabled'],80)
        self.assertEqual(first.manifest['scenario_order'],second.manifest['scenario_order'])
        self.assertEqual(first.manifest['prompt_catalog'],second.manifest['prompt_catalog'])
        self.assertEqual(len(first.manifest['prompt_catalog']),80)
        for prompt in first.manifest['prompt_catalog']:
            scenario=first.scenarios[prompt['execution_index']-1]
            self.assertEqual(prompt['messages'],build_messages(scenario,prompt['condition']))
            self.assertEqual(prompt['prompt_hash'],sha256(canonical_json(prompt['messages']).encode()).hexdigest())
            self.assertNotIn('scenario_id',prompt['messages'][1]['content'])
            self.assertNotIn('expected_action',prompt['messages'][1]['content'])
            self.assertNotIn('rationale',prompt['messages'][1]['content'])

    def test_planned_phase_partition_80_without_repeating_connectivity_case(self):
        policy=json.loads(POLICY.read_text()); seen=set()
        self.assertEqual([v['maximum_requests'] for v in policy['phases'].values()],[1,4,35,40])
        for phase in policy['phases'].values():
            keys={(phase['condition'],i) for i in phase['execution_indices']}
            self.assertFalse(seen & keys);seen.update(keys)
        self.assertEqual(seen,{(c,i) for c in ('pre_update','post_update') for i in range(1,41)})
        self.assertEqual(policy['controls']['max_attempts_per_request'],1)
        self.assertTrue(policy['controls']['stop_on_http_429'])
        self.assertEqual(policy['controls']['stop_after_consecutive_http_503'],2)

    def test_all_phases_fail_before_network_or_credentials(self):
        with patch('urllib.request.urlopen',side_effect=AssertionError('network forbidden')) as network,patch.dict('os.environ',{},clear=True):
            for phase in json.loads(POLICY.read_text())['phases']:
                with self.assertRaisesRegex(ValidationError,'unresolved'):
                    preflight.check(phase)
            with self.assertRaises(ValidationError):preflight.check('automatic-all-phases')
        network.assert_not_called()

    def test_enabling_flag_alone_cannot_bypass_missing_evidence(self):
        policy=json.loads(POLICY.read_text());policy['execution_enabled']=True
        original_read=Path.read_text
        def read(path,*args,**kwargs):
            if path.name==POLICY.name:return json.dumps(policy)
            return original_read(path,*args,**kwargs)
        with patch.object(Path,'read_text',read),patch('urllib.request.urlopen') as network:
            with self.assertRaisesRegex(ValidationError,'unresolved'):preflight.check('connectivity')
            network.assert_not_called()

    def test_workflow_is_manual_readiness_only_no_provider_calls(self):
        workflow=json.loads(WORKFLOW.read_text())
        self.assertEqual(set(workflow['on']),{'workflow_dispatch'})
        inputs=workflow['on']['workflow_dispatch']['inputs']
        self.assertEqual(inputs['phase']['default'],'connectivity')
        self.assertEqual(inputs['phase']['options'],['connectivity','small_pilot','remaining_post','paired_pre'])
        self.assertEqual(workflow['permissions'],{'contents':'read','actions':'read'})
        scripts='\n'.join(s.get('run','') for s in workflow['jobs']['readiness']['steps'])
        self.assertIn('free_tier_preflight.py',scripts)
        for forbidden in ('execute-live','generateContent','pilot-run','curl','printenv','set -x'):
            self.assertNotIn(forbidden,scripts)

    def test_frozen_benchmark_config_and_definitions_unchanged(self):
        self.assertEqual(sha256((ROOT/'data/pilot/scenarios.jsonl').read_bytes()).hexdigest(),
                         '17e4da22029b31b280fcf711bec9c88f261f01ee40dd45137a2ad2540ed4c80d')
        protected=['configs/pilot_eval.yaml','src/revocable_flow/protocol.py','src/revocable_flow/metrics.py']
        for path in protected:
            previous=subprocess.check_output(['git','show','HEAD:'+path],cwd=ROOT)
            self.assertEqual(previous,(ROOT/path).read_bytes())
