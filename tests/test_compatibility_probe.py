"""All provider responses and authorization values are synthetic offline fixtures."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from revocable_flow.compatibility_probe import prepare, run, archive, PARAMETERS
from revocable_flow.providers.base import HTTPReply, TransportFailure
from revocable_flow.protocol import load_protocol_config
from revocable_flow.schema import ValidationError

ROOT=Path(__file__).resolve().parents[1]
APPROVAL={'one_request_approved':True,'key_project_binding_confirmed':True,
          'free_tier_no_paid_billing_confirmed':True,'quota_review_confirmed':True,
          'all_provider_budget_review_confirmed':True,'reviewed_spend_usd':0}
GIT={'commit':'1'*40,'dirty':False}


class CompatibilityProbeTests(unittest.TestCase):
    def fixture(self,root):
        config=load_protocol_config(ROOT/'configs/free_tier_pilot_v1.yaml')
        config['benchmark']['path']=str(ROOT/'data/pilot/scenarios.jsonl')
        (root/'configs').mkdir(exist_ok=True)
        path=root/'configs/probe-config.yaml';path.write_text(json.dumps(config))
        return path

    def invoke(self,root,transport,run_id='SYN-compat',approval=None):
        config=self.fixture(root)
        with patch('revocable_flow.runner._git',return_value=GIT),patch.dict(os.environ,{'GOOGLE_API_KEY':'SYN-mock-credential'},clear=True):
            return run(run_id,APPROVAL if approval is None else approval,config=config,transport=transport)

    def reply(self,text='{"action":"BLOCK","release_fields":[]}'):
        return HTTPReply(200,{'modelVersion':'SYN-model-revision','responseId':'SYN-request',
            'candidates':[{'content':{'parts':[{'text':text}]},'finishReason':'STOP'}],
            'usageMetadata':{'promptTokenCount':11,'candidatesTokenCount':4}})

    def test_exact_one_request_raw_metadata_and_safe_archive_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);transport=Mock(return_value=self.reply())
            plan,summary,audit=self.invoke(root,transport)
            transport.assert_called_once();self.assertEqual(summary['attempted_provider_requests'],1)
            self.assertEqual(audit['http_status'],200);self.assertFalse(audit['transport_outcome_uncertain'])
            self.assertEqual(audit['automatic_retries'],0)
            self.assertEqual(transport.call_args.args[2],json.loads((ROOT/'docs/reports/flash_lite_outbound_payload_audit.json').read_text()))
            m=plan.manifest
            self.assertEqual(m['execution_limits'],{'max_provider_requests':1,'max_attempts_per_request':1})
            self.assertEqual(m['compatibility_probe']['exact_model_support'],'unverified_under_test')
            self.assertEqual(m['configuration']['model_matrix'][0]['status'],'disabled')
            self.assertEqual(json.loads(m['config_bytes_utf8']),m['configuration'])
            raw=next((plan.root/'raw').rglob('*.response.json'));original=raw.read_bytes()
            record=json.loads(original);self.assertEqual(record['reported_model'],'SYN-model-revision')
            self.assertEqual(record['raw_output'],'{"action":"BLOCK","release_fields":[]}')
            self.assertEqual(record['usage'],{'promptTokenCount':11,'candidatesTokenCount':4})
            archive(plan.root,'SYN-compat',root/'archive')
            self.assertEqual((root/'archive'/raw.relative_to(plan.root)).read_bytes(),original)
            with self.assertRaises(ValidationError):archive(plan.root,'SYN-compat',root/'archive')
            with patch('revocable_flow.runner._git',return_value=GIT):
                with self.assertRaises(ValidationError):prepare('SYN-compat',APPROVAL,config=root/'configs/probe-config.yaml')
            self.assertEqual(transport.call_count,1)

    def test_all_authorizations_and_unknown_budget_fail_before_transport(self):
        bad=[]
        for key in APPROVAL:
            changed=deepcopy(APPROVAL);changed[key]=None if key=='reviewed_spend_usd' else False;bad.append(changed)
        for spend in (4,-1,float('nan'),float('inf'),True):
            changed=deepcopy(APPROVAL);changed['reviewed_spend_usd']=spend;bad.append(changed)
        for approval in bad:
            with self.subTest(approval=approval),tempfile.TemporaryDirectory() as directory:
                transport=Mock(side_effect=AssertionError('call forbidden'))
                with self.assertRaises(ValidationError):self.invoke(Path(directory),transport,approval=approval)
                transport.assert_not_called()

    def test_503_429_invalid_output_and_transport_failure_never_retry(self):
        for reply in (HTTPReply(503,None),HTTPReply(429,None),self.reply('SYN-invalid-json')):
            with self.subTest(reply=reply),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);transport=Mock(return_value=reply)
                plan,summary,audit=self.invoke(root,transport)
                transport.assert_called_once();self.assertEqual(audit['http_status'],reply.status)
                if reply.status!=200:
                    self.assertEqual(summary['completed'],0);self.assertEqual(len(summary['infrastructure_missing']),1)
                    self.assertEqual(len(list((plan.root/'parsed').rglob('model-01/**/*.json'))),0)
                else:
                    self.assertEqual(summary['completed'],1)
                    self.assertEqual(json.loads(next((plan.root/'raw').rglob('*.response.json')).read_text())['raw_output'],'SYN-invalid-json')
                archive(plan.root,'SYN-compat',root/'archive')
        with tempfile.TemporaryDirectory() as directory:
            transport=Mock(side_effect=TransportFailure('timeout'))
            _,summary,audit=self.invoke(Path(directory),transport)
            transport.assert_called_once();self.assertTrue(audit['transport_outcome_uncertain'])
            self.assertIsNone(audit['http_status']);self.assertEqual(summary['completed'],0)

    def test_model_parameters_repetitions_mismatch_and_dirty_checkout_refuse(self):
        for mutation in ('model','parameters','repetitions'):
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);path=self.fixture(root);config=json.loads(path.read_text())
                if mutation=='model':config['model_matrix'][0]['model_id']='SYN-other'
                elif mutation=='parameters':config['execution']['temperature']=1
                else:config['execution']['repetitions']=2
                path.write_text(json.dumps(config))
                with self.assertRaises(ValidationError):prepare('SYN-refused',APPROVAL,config=path)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=self.fixture(root);transport=Mock()
            with patch('revocable_flow.runner._git',return_value={'commit':'1'*40,'dirty':True}):
                with self.assertRaises(ValidationError):run('SYN-dirty',APPROVAL,config=path,transport=transport)
            transport.assert_not_called()

    def test_unsafe_raw_response_stops_but_preserves_sanitized_http_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);transport=Mock(return_value=self.reply('SYN-mock-credential'))
            with self.assertRaises(ValidationError):self.invoke(root,transport)
            transport.assert_called_once()
            audit=json.loads((root/'results/summaries/SYN-compat/dispatch-audit.json').read_text())
            self.assertEqual(audit['http_status'],200)
            self.assertFalse(audit['runner_terminated_normally'])
            self.assertEqual(len(list((root/'results/raw').rglob('*.started.json'))),1)
            self.assertEqual(len(list((root/'results/raw').rglob('*.response.json'))),0)
            archive(root/'results','SYN-compat',root/'archive')

    def test_manual_workflow_one_fixed_request_no_phase_or_chain(self):
        workflow=json.loads((ROOT/'.github/workflows/flash-lite-compatibility.yml').read_text())
        self.assertEqual(set(workflow['on']),{'workflow_dispatch'})
        inputs=workflow['on']['workflow_dispatch']['inputs']
        self.assertNotIn('phase',inputs)
        for key in APPROVAL:
            if key!='reviewed_spend_usd':self.assertFalse(inputs[key]['default'])
        job=workflow['jobs']['compatibility'];self.assertIn('github.run_attempt == 1',job['if'])
        steps=job['steps'];dispatch=next(s for s in steps if s.get('id')=='run')
        self.assertEqual(dispatch['env']['GOOGLE_API_KEY'],'${{ secrets.GOOGLE_API_KEY }}')
        self.assertEqual(dispatch['run'],'python .github/scripts/flash_lite_compatibility.py run --execute-live')
        self.assertIn('workflowId',json.dumps(steps));self.assertIn('flash-lite-compatibility.yml',json.dumps(steps))
        for forbidden in ('createWorkflowDispatch','workflow_run','schedule','anthropic','openai'):
            self.assertNotIn(forbidden,json.dumps(workflow))
        self.assertFalse(json.loads((ROOT/'configs/free_tier_policy_v1.json').read_text())['execution_enabled'])
