"""Synthetic mocked artifacts only; never contacts a provider or GitHub."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from revocable_flow import compatibility_probe as probe
from revocable_flow.four_request_bridge import bridge, prepare, run, archive, approvals_checked
from revocable_flow.chained_recovery import file_hashes
from revocable_flow.providers.base import HTTPReply, TransportFailure
from revocable_flow.protocol import load_protocol_config
from revocable_flow.schema import ValidationError

ROOT=Path(__file__).resolve().parents[1]
GIT={'commit':'1'*40,'dirty':False}
OLD={'one_request_approved':True,'key_project_binding_confirmed':True,
     'free_tier_no_paid_billing_confirmed':True,'quota_review_confirmed':True,
     'all_provider_budget_review_confirmed':True,'reviewed_spend_usd':0}
NEW={k:v for k,v in OLD.items() if k!='one_request_approved'}
NEW.update(four_requests_approved=True,available_rpm_requests=15,available_rpd_requests=500,available_tpm_tokens=250000)


def reply(text='{"action":"ALLOW","release_fields":[]}'):
    return HTTPReply(200,{'modelVersion':'gemini-3.5-flash-lite','responseId':'SYN-request',
        'candidates':[{'content':{'parts':[{'text':text}]},'finishReason':'STOP'}],
        'usageMetadata':{'promptTokenCount':10,'candidatesTokenCount':5}})


class FourRequestBridgeTests(unittest.TestCase):
    def fixture(self,root):
        config=load_protocol_config(ROOT/'configs/free_tier_pilot_v1.yaml')
        config['benchmark']['path']=str(ROOT/'data/pilot/scenarios.jsonl')
        (root/'configs').mkdir();path=root/'configs/base.yaml';path.write_text(json.dumps(config))
        with patch('revocable_flow.runner._git',return_value=GIT),patch.dict(os.environ,{'GOOGLE_API_KEY':'SYN-test-credential'},clear=True):
            plan,_,_=probe.run('SYN-original',OLD,config=path,
                transport=Mock(return_value=reply('```json\n{"action":"REDACT","release_fields":["band_field"]}\n```')))
        source=root/'source';probe.archive(plan.root,'SYN-original',source)
        pin=json.loads((ROOT/'configs/flash_lite_next_four_v1.json').read_text())
        pin.update(source_run_id='SYN-original',source_commit=GIT['commit'],source_manifest_hash=plan.manifest['manifest_hash'],
                   source_config_hash=sha256(path.read_bytes()).hexdigest(),source_file_hashes=file_hashes(source))
        scope=root/'configs/scope.json';scope.write_text(json.dumps(pin))
        return source,path,scope

    def invoke(self,source,config,scope,transport,approval=NEW):
        with patch('revocable_flow.runner._git',return_value=GIT),patch.dict(os.environ,{'GOOGLE_API_KEY':'SYN-test-credential'},clear=True):
            return run(source,'SYN-four',approval,config=config,scope=scope,transport=transport)

    def test_verified_bridge_counts_invalid_original_once_and_exact_schedule(self):
        with tempfile.TemporaryDirectory() as directory:
            source,config,scope=self.fixture(Path(directory));before=file_hashes(source)
            b,_=bridge(source,config=config,scope=scope)
            self.assertEqual(len(b['ledger']),1);entry=b['ledger'][0]
            self.assertEqual(entry['identity']['scenario_id'],'scope_change-09')
            self.assertEqual(entry['status'],'terminal_completed');self.assertEqual(entry['primary_validation_errors'],['invalid_json'])
            self.assertIsNone(entry['primary_score']['privacy_violation']);self.assertIsNone(entry['primary_score']['over_refusal'])
            self.assertEqual([r['execution_index'] for r in b['next_requests']],[2,3,4,5])
            self.assertEqual([r['identity']['scenario_id'] for r in b['next_requests']],
                             ['purpose_change-04','consent_revocation-03','scope_change-07','consent_revocation-08'])
            self.assertFalse(b['exploratory_analysis_in_primary']);self.assertFalse(b['later_phases_enabled'])
            self.assertEqual(file_hashes(source),before)

    def test_four_exact_payloads_no_retry_source_preserved_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source,config,scope=self.fixture(root);before=file_hashes(source)
            transport=Mock(return_value=reply('SYN-invalid-json'))
            plan,summary=self.invoke(source,config,scope,transport)
            self.assertEqual(transport.call_count,4);self.assertEqual(summary['completed'],4)
            self.assertFalse(plan.manifest['primary_complete_design'])
            self.assertEqual(plan.manifest['configuration']['model_matrix'][0]['status'],'disabled')
            self.assertEqual(plan.manifest['provider_checks'][0]['effective_parameters'],probe.PARAMETERS)
            payloads=[call.args[2] for call in transport.call_args_list]
            self.assertEqual(len({json.dumps(p,sort_keys=True) for p in payloads}),4)
            for payload in payloads:
                self.assertEqual(payload['generationConfig'],{'temperature':0,'topP':1,'seed':20261007,'maxOutputTokens':512})
                self.assertNotIn('scope_change-09',json.dumps(payload));self.assertNotIn('expected_action',json.dumps(payload))
            ledger=json.loads((plan.root/'summaries/SYN-four/campaign-ledger.json').read_text())['ledger']
            self.assertEqual(len(ledger),5);self.assertEqual(ledger[0],plan.manifest['provenance_bridge']['ledger'][0])
            self.assertEqual([r['status'] for r in ledger],['terminal_completed']*5)
            self.assertEqual(file_hashes(source),before)
            archive(source,plan.root,'SYN-four',root/'upload')
            self.assertEqual(file_hashes(root/'upload/source'),before)
            with self.assertRaises(ValidationError):archive(source,plan.root,'SYN-four',root/'upload')
            with self.assertRaises(ValidationError):self.invoke(source,config,scope,transport)
            self.assertEqual(transport.call_count,4)

    def test_quota_budget_and_each_fresh_confirmation_fail_closed(self):
        for field in NEW:
            a=deepcopy(NEW);a[field]=0 if field.startswith('available_') else (None if field=='reviewed_spend_usd' else False)
            with self.subTest(field=field),self.assertRaises(ValidationError):approvals_checked(a,10000)
        for spend in (4,-1,float('nan'),float('inf'),True):
            a=deepcopy(NEW);a['reviewed_spend_usd']=spend
            with self.assertRaises(ValidationError):approvals_checked(a,10000)
        a=deepcopy(NEW);a['available_tpm_tokens']=9999
        with self.assertRaises(ValidationError):approvals_checked(a,10000)
        a=deepcopy(NEW);a['available_rpm_requests']=16
        with self.assertRaises(ValidationError):approvals_checked(a,10000)

    def test_source_extra_record_changed_hash_prompt_and_config_refuse(self):
        for mutation in ('extra','raw','config','scope_indices','repinned_prompt'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as directory:
                source,config,scope=self.fixture(Path(directory));transport=Mock(side_effect=AssertionError('forbidden'))
                if mutation=='extra':(source/'extra-attempt.json').write_text('{}')
                elif mutation=='raw':next((source/'raw').rglob('*.response.json')).write_text('{}')
                elif mutation=='config':config.write_text(config.read_text()+' ')
                elif mutation=='scope_indices':
                    p=json.loads(scope.read_text());p['execution_indices']=[1,2,3,4];scope.write_text(json.dumps(p))
                else:
                    from revocable_flow.runner import _digest
                    mp=next((source/'manifests').glob('*.json'));m=json.loads(mp.read_text())
                    m['prompt_catalog'][0]['messages'][0]['content']='SYN-altered-prompt'
                    m.pop('manifest_hash');m['manifest_hash']=_digest(m);mp.write_text(json.dumps(m))
                    p=json.loads(scope.read_text());p['source_manifest_hash']=m['manifest_hash'];p['source_file_hashes']=file_hashes(source);scope.write_text(json.dumps(p))
                with self.assertRaises(ValidationError):self.invoke(source,config,scope,transport)
                transport.assert_not_called()

    def test_429_repeated_503_and_ambiguous_transport_stop_without_retry(self):
        cases=[([HTTPReply(429,None)]*4,1),([HTTPReply(503,None)]*4,2),([TransportFailure('SYN-timeout')]*4,1)]
        for responses,count in cases:
            with self.subTest(count=count),tempfile.TemporaryDirectory() as directory:
                source,config,scope=self.fixture(Path(directory));transport=Mock(side_effect=responses)
                plan,summary=self.invoke(source,config,scope,transport)
                self.assertEqual(transport.call_count,count);self.assertEqual(summary['completed'],0)
                self.assertEqual(summary['attempted_provider_requests'],count)
                archive(source,plan.root,'SYN-four',Path(directory)/'upload')
                self.assertEqual(len(list((plan.root/'raw/SYN-four').rglob('*.started.json'))),count)

    def test_dirty_checkout_and_missing_key_never_call(self):
        with tempfile.TemporaryDirectory() as directory:
            source,config,scope=self.fixture(Path(directory));transport=Mock()
            with patch('revocable_flow.runner._git',return_value={'commit':'1'*40,'dirty':True}):
                with self.assertRaises(ValidationError):run(source,'SYN-refused',NEW,config=config,scope=scope,transport=transport)
            transport.assert_not_called()
            with patch('revocable_flow.runner._git',return_value=GIT),patch.dict(os.environ,{},clear=True):
                with self.assertRaises(ValidationError):run(source,'SYN-no-key',NEW,config=config,scope=scope,transport=transport)
            transport.assert_not_called()

    def test_manual_workflow_fixed_source_scope_and_fresh_reviews(self):
        w=json.loads((ROOT/'.github/workflows/flash-lite-next-four.yml').read_text())
        self.assertEqual(set(w['on']),{'workflow_dispatch'})
        inputs=w['on']['workflow_dispatch']['inputs'];self.assertEqual(set(inputs),set(NEW))
        for key in NEW:
            if type(NEW[key]) is bool:self.assertIs(inputs[key]['default'],False)
        job=w['jobs']['next_four'];self.assertIn('github.run_attempt == 1',job['if'])
        steps=job['steps'];execute=next(s for s in steps if s.get('id')=='run')
        self.assertEqual(execute['env']['GOOGLE_API_KEY'],'${{ secrets.GOOGLE_API_KEY }}')
        self.assertEqual(execute['run'],'python .github/scripts/flash_lite_next_four.py run --execute-live')
        download=next(s for s in steps if s.get('uses')=='actions/download-artifact@v4')
        self.assertEqual(download['with']['run-id'],37891267903)
        guard=next(s for s in steps if 'free_tier_dispatch_guard.js' in str(s))
        self.assertLess(steps.index(guard),steps.index(execute));self.assertIn('flash-lite-next-four.yml',str(guard))
        for forbidden in ('createWorkflowDispatch','workflow_run','schedule','anthropic','openai'):
            self.assertNotIn(forbidden,json.dumps(w))
        self.assertFalse(json.loads((ROOT/'configs/free_tier_policy_v1.json').read_text())['execution_enabled'])
        self.assertEqual(load_protocol_config(ROOT/'configs/free_tier_pilot_v1.yaml')['models'],[])
