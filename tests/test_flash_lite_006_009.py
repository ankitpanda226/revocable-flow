"""Synthetic three-run provenance fixtures; all provider and GitHub calls mocked."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

import test_four_request_bridge as previous
from revocable_flow import four_request_bridge as batch
from revocable_flow.chained_recovery import file_hashes
from revocable_flow.providers.base import HTTPReply,TransportFailure
from revocable_flow.schema import ValidationError

ROOT=Path(__file__).resolve().parents[1]


class Requests006009Tests(unittest.TestCase):
    def fixture(self,root):
        helper=previous.FourRequestBridgeTests()
        source,config,old_scope=helper.fixture(root)
        replies=[previous.reply('```json\n{"action":"BLOCK","release_fields":[]}\n```'),
                 previous.reply('{"action":"BLOCK","release_fields":[]}'),
                 previous.reply('{"action":"REDACT","release_fields":["area_field"]}'),
                 previous.reply('{"action":"REDACT","release_fields":["slot_reference"]}')]
        plan,_=helper.invoke(source,config,old_scope,Mock(side_effect=replies))
        prior=root/'prior';batch.archive(source,plan.root,'SYN-four',prior)
        pin=json.loads((ROOT/batch.CONTINUATION_SCOPE).read_text())
        pin.update(source_run_id='SYN-four',source_commit=previous.GIT['commit'],
                   source_manifest_hash=plan.manifest['manifest_hash'],source_file_hashes=file_hashes(prior),
                   source_config_hash=plan.manifest['config_hash'],source_bridge_hash=plan.manifest['provenance_bridge']['bridge_hash'])
        scope=root/'configs/continuation.json';scope.write_text(json.dumps(pin))
        return prior,config,old_scope,scope

    def invoke(self,fixture,transport,run_id='SYN-006009',approval=previous.NEW):
        source,config,old_scope,scope=fixture
        with patch.object(batch,'SCOPE',old_scope),patch('revocable_flow.runner._git',return_value=previous.GIT),patch.dict(os.environ,{'GOOGLE_API_KEY':'SYN-test-credential'},clear=True):
            return batch.run(source,run_id,approval,config=config,scope=scope,transport=transport)

    def test_full_source_ledger_preserved_invalid_attempts_excluded_and_exact_next(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture=self.fixture(Path(directory));source,config,old_scope,scope=fixture;before=file_hashes(source)
            with patch.object(batch,'SCOPE',old_scope):b,_=batch.bridge(source,config=config,scope=scope)
            self.assertEqual(len(b['ledger']),5)
            original=json.loads((source/'batch/summaries/SYN-four/campaign-ledger.json').read_text())['ledger']
            self.assertEqual(b['ledger'],original)
            self.assertEqual([r['request_key'] for r in b['next_requests']],[f'model-01/post_update/{i:03d}' for i in range(6,10)])
            self.assertEqual([r['identity']['scenario_id'] for r in b['next_requests']],
                             ['purpose_change-07','consent_revocation-02','purpose_change-03','scope_change-04'])
            self.assertFalse(b['later_phases_enabled']);self.assertFalse(b['exploratory_analysis_in_primary'])
            for i in (1,2):
                tree=source/'source' if i==1 else source/'batch';rid='SYN-original' if i==1 else 'SYN-four'
                score=json.loads((tree/f'parsed/{rid}/model-01/post_update/{i:03d}.json').read_text())['score']
                self.assertIsNone(score['privacy_violation']);self.assertIsNone(score['over_refusal'])
            self.assertEqual(file_hashes(source),before)

    def test_four_new_calls_exact_parameters_safe_archive_and_global_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);fixture=self.fixture(root);source=fixture[0];before=file_hashes(source)
            transport=Mock(return_value=previous.reply('SYN-invalid-format'))
            plan,summary=self.invoke(fixture,transport)
            self.assertEqual(transport.call_count,4);self.assertEqual(summary['completed'],4)
            self.assertEqual([r['execution_index'] for r in plan.manifest['requests']],[6,7,8,9])
            for call in transport.call_args_list:
                self.assertTrue(call.args[0].endswith('/gemini-3.5-flash-lite:generateContent'))
                self.assertEqual(call.args[2]['generationConfig'],{'temperature':0,'topP':1,'seed':20261007,'maxOutputTokens':512})
                self.assertNotIn('responseMimeType',call.args[2]['generationConfig'])
            ledger=json.loads((plan.root/'summaries/SYN-006009/campaign-ledger.json').read_text())['ledger']
            self.assertEqual(len(ledger),9);self.assertEqual(ledger[:5],plan.manifest['provenance_bridge']['ledger'])
            self.assertTrue(all(e['status']=='terminal_completed' for e in ledger))
            batch.archive(source,plan.root,'SYN-006009',root/'upload')
            self.assertEqual(file_hashes(root/'upload/source'),before);self.assertEqual(file_hashes(source),before)
            with self.assertRaises(ValidationError):batch.archive(source,plan.root,'SYN-006009',root/'upload')
            with self.assertRaises(ValidationError):self.invoke(fixture,transport,run_id='SYN-different-run-id')
            self.assertEqual(transport.call_count,4)

    def test_source_hash_uncertain_duplicate_and_dispatch_audit_fail_closed(self):
        for change in ('raw','uncertain','duplicate','audit'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as directory:
                fixture=self.fixture(Path(directory));source,_,_,scope=fixture
                if change=='raw':next((source/'batch/raw').rglob('*.response.json')).write_text('{}')
                else:
                    path=source/'batch/summaries/SYN-four'/('dispatch-audit.json' if change=='audit' else 'campaign-ledger.json')
                    record=json.loads(path.read_text())
                    if change=='audit':record['provider_calls_entered']=5
                    elif change=='uncertain':record['ledger'][2]['status']='ambiguous_claimed_never_redispatch'
                    else:record['ledger'][2]=deepcopy(record['ledger'][1])
                    path.write_text(json.dumps(record))
                    # Repinning bytes must not bypass semantic/provenance validation.
                    pin=json.loads(scope.read_text());pin['source_file_hashes']=file_hashes(source);scope.write_text(json.dumps(pin))
                transport=Mock(side_effect=AssertionError('no live call'))
                with self.assertRaises(ValidationError):self.invoke(fixture,transport)
                transport.assert_not_called()

    def test_quota_budget_scope_overlap_and_cap_block_before_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture=self.fixture(Path(directory));transport=Mock()
            for key in previous.NEW:
                approval=deepcopy(previous.NEW)
                approval[key]=0 if key.startswith('available_') else None if key=='reviewed_spend_usd' else False
                with self.subTest(key=key),self.assertRaises(ValidationError):self.invoke(fixture,transport,approval=approval)
            scope=fixture[3];pin=json.loads(scope.read_text());pin['execution_indices']=[5,6,7,8];scope.write_text(json.dumps(pin))
            with self.assertRaises(ValidationError):self.invoke(fixture,transport)
            pin['execution_indices']=[6,7,8,9];pin['maximum_new_requests']=5;scope.write_text(json.dumps(pin))
            with self.assertRaises(ValidationError):self.invoke(fixture,transport)
            transport.assert_not_called()

    def test_provider_errors_and_uncertain_transport_are_preserved_never_retried(self):
        for responses,count in (([HTTPReply(503,None)]*4,2),([HTTPReply(429,None)]*4,1),([TransportFailure('timeout')]*4,1)):
            with self.subTest(count=count),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);fixture=self.fixture(root);before=file_hashes(fixture[0]);transport=Mock(side_effect=responses)
                plan,summary=self.invoke(fixture,transport)
                self.assertEqual(transport.call_count,count);self.assertEqual(summary['completed'],0)
                ledger=json.loads((plan.root/'summaries/SYN-006009/campaign-ledger.json').read_text())['ledger']
                self.assertEqual(ledger[:5],plan.manifest['provenance_bridge']['ledger'])
                self.assertEqual(sum(e['status']=='not_attempted' for e in ledger),4-count)
                batch.archive(fixture[0],plan.root,'SYN-006009',root/'upload')
                self.assertEqual(file_hashes(root/'upload/source'),before)
                with self.assertRaises(ValidationError):self.invoke(fixture,transport,run_id='SYN-no-resume')
                self.assertEqual(transport.call_count,count)

    def test_atomic_scope_claim_blocks_overlapping_run_before_provider(self):
        for conflict in ('manifest','claim_before','claim_race'):
            with self.subTest(conflict=conflict),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);fixture=self.fixture(root);source,config,old_scope,scope=fixture;transport=Mock()
                with patch.object(batch,'SCOPE',old_scope):plan=batch.prepare(source,'SYN-new',previous.NEW,config=config,scope=scope)
                claim=root/'results/claims'/f"{plan.manifest['dispatch_claim_key']}.json"
                if conflict=='manifest':
                    (root/'results/manifests/SYN-overlap.json').write_text(json.dumps({'requests':[{
                        'provider':'google','model':batch.MODEL,'condition':'post_update','execution_index':6}]}))
                elif conflict=='claim_before':claim.parent.mkdir(parents=True);claim.write_text('{}')
                original_prepare=batch.prepare
                def concurrent_claim(*args,**kwargs):
                    p=original_prepare(*args,**kwargs)
                    if conflict=='claim_race' and p.manifest['provenance_bridge']['bridge_version']==2:
                        claim.parent.mkdir(parents=True);claim.write_text('{}')
                    return p
                with patch.object(batch,'prepare',side_effect=concurrent_claim):
                    with self.assertRaises(ValidationError):self.invoke(fixture,transport)
                transport.assert_not_called()
                self.assertFalse((root/'results/raw/SYN-006009').exists())

    def test_manual_workflow_exact_source_scope_no_followup_and_fresh_gates(self):
        w=json.loads((ROOT/'.github/workflows/flash-lite-006-009.yml').read_text())
        self.assertEqual(set(w['on']),{'workflow_dispatch'});self.assertEqual(w['concurrency']['group'],'flash-lite-pilot-v1')
        inputs=w['on']['workflow_dispatch']['inputs'];self.assertEqual(set(inputs),set(previous.NEW))
        for key,value in previous.NEW.items():
            if type(value) is bool:self.assertIs(inputs[key]['default'],False)
        job=w['jobs']['requests_006_009'];self.assertIn('github.run_attempt == 1',job['if'])
        steps=job['steps'];execute=next(s for s in steps if s.get('id')=='run')
        self.assertEqual(execute['run'],'python .github/scripts/flash_lite_next_four.py run --execute-live --scope 006-009')
        self.assertEqual(execute['env']['GOOGLE_API_KEY'],'${{ secrets.GOOGLE_API_KEY }}')
        download=next(s for s in steps if s.get('uses')=='actions/download-artifact@v4')
        self.assertEqual(download['with']['run-id'],38080218987);self.assertEqual(download['with']['name'],'flash-lite-next-four-results')
        guard=next(s for s in steps if 'free_tier_dispatch_guard.js' in str(s))
        self.assertLess(steps.index(guard),steps.index(execute));self.assertIn('expectedPriorCommit',str(guard))
        for forbidden in ('createWorkflowDispatch','workflow_run','schedule','anthropic','openai'):
            self.assertNotIn(forbidden,json.dumps(w))
        self.assertFalse(json.loads((ROOT/'configs/free_tier_policy_v1.json').read_text())['execution_enabled'])
