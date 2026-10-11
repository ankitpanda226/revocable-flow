"""Offline fixed fourth-batch safety tests; synthetic responses, no API calls."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

import test_flash_lite_006_009 as prior_tests
import test_four_request_bridge as original_tests
from revocable_flow import four_request_bridge as batch
from revocable_flow.chained_recovery import file_hashes
from revocable_flow.providers.base import HTTPReply,TransportFailure
from revocable_flow.schema import ValidationError

ROOT=Path(__file__).resolve().parents[1]
EXPECTED=['scope_change-08','scope_change-01','consent_revocation-10','recipient_change-08']

class Requests010013Tests(unittest.TestCase):
    def fixture(self,root):
        helper=prior_tests.Requests006009Tests();previous=helper.fixture(root)
        replies=[original_tests.reply('```json\n{"action":"REDACT","release_fields":["slot_reference"]}\n```'),
                 original_tests.reply('{"action":"BLOCK","release_fields":[]}'),
                 original_tests.reply('```json\n{"action":"BLOCK","release_fields":[]}\n```'),
                 original_tests.reply('{"action":"BLOCK","release_fields":[]}')]
        plan,_=helper.invoke(previous,Mock(side_effect=replies))
        source=root/'nine';batch.archive(previous[0],plan.root,'SYN-006009',source)
        pin=json.loads((ROOT/batch.NEXT_SCOPE).read_text())
        pin.update(source_run_id='SYN-006009',source_commit=original_tests.GIT['commit'],
                   source_manifest_hash=plan.manifest['manifest_hash'],source_file_hashes=file_hashes(source),
                   source_config_hash=plan.manifest['config_hash'],source_bridge_hash=plan.manifest['provenance_bridge']['bridge_hash'])
        scope=root/'configs/next.json';scope.write_text(json.dumps(pin))
        return source,previous[1],previous[2],previous[3],scope

    def contexts(self,f):
        from contextlib import ExitStack
        stack=ExitStack();stack.enter_context(patch.object(batch,'SCOPE',f[2]))
        stack.enter_context(patch.object(batch,'CONTINUATION_SCOPE',f[3]))
        stack.enter_context(patch('revocable_flow.runner._git',return_value=original_tests.GIT))
        stack.enter_context(patch.dict(os.environ,{'GOOGLE_API_KEY':'SYN-test-credential'},clear=True))
        return stack

    def invoke(self,f,transport,run_id='SYN-010013',approval=original_tests.NEW):
        with self.contexts(f):return batch.run(f[0],run_id,approval,config=f[1],scope=f[4],transport=transport)

    def test_chain_and_exact_next_preserve_invalid_terminal_scores(self):
        with tempfile.TemporaryDirectory() as d:
            f=self.fixture(Path(d));before=file_hashes(f[0])
            with self.contexts(f):b,_=batch.bridge(f[0],config=f[1],scope=f[4])
            self.assertEqual(len(before),48);self.assertEqual(len(b['ledger']),9)
            self.assertEqual([r['execution_index'] for r in b['ledger']],list(range(1,10)))
            self.assertEqual([r['identity']['scenario_id'] for r in b['next_requests']],EXPECTED)
            self.assertEqual([r['request_key'] for r in b['next_requests']],[f'model-01/post_update/{i:03d}' for i in range(10,14)])
            self.assertEqual(sum(r['primary_parse_status']=='invalid' for r in b['ledger']),4)
            for p in f[0].rglob('*.json'):
                record=json.loads(p.read_text());score=record.get('score',{}) if isinstance(record,dict) else {}
                if score and score.get('valid') is False:
                    self.assertIsNone(score['privacy_violation']);self.assertIsNone(score['over_refusal'])
            self.assertEqual(before,file_hashes(f[0]));self.assertFalse(b['later_phases_enabled'])

    def test_four_call_cap_wire_ledger_archive_and_duplicate_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);f=self.fixture(root);before=file_hashes(f[0]);transport=Mock(return_value=original_tests.reply('SYN-invalid-format'))
            plan,summary=self.invoke(f,transport)
            self.assertEqual(transport.call_count,4);self.assertEqual(summary['completed'],4)
            for call in transport.call_args_list:
                self.assertTrue(call.args[0].endswith('/gemini-3.5-flash-lite:generateContent'))
                self.assertEqual(call.args[2]['generationConfig'],{'temperature':0,'topP':1,'seed':20261007,'maxOutputTokens':512})
            ledger=json.loads((plan.root/'summaries/SYN-010013/campaign-ledger.json').read_text())['ledger']
            self.assertEqual(len(ledger),13);self.assertEqual(ledger[:9],plan.manifest['provenance_bridge']['ledger'])
            self.assertTrue(all(r['status']=='terminal_completed' for r in ledger))
            batch.archive(f[0],plan.root,'SYN-010013',root/'upload')
            self.assertEqual(before,file_hashes(root/'upload/source'));self.assertEqual(before,file_hashes(f[0]))
            with self.assertRaises(ValidationError):batch.archive(f[0],plan.root,'SYN-010013',root/'upload')
            with self.assertRaises(ValidationError):self.invoke(f,transport,run_id='SYN-other')
            self.assertEqual(transport.call_count,4)

    def test_tampered_uncertain_duplicate_and_audit_block_even_if_repinned(self):
        for change in ('raw','uncertain','duplicate','audit'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as d:
                f=self.fixture(Path(d));source=f[0]
                if change=='raw':next((source/'batch/raw').rglob('*.response.json')).write_text('{}')
                else:
                    p=source/'batch/summaries/SYN-006009'/('dispatch-audit.json' if change=='audit' else 'campaign-ledger.json')
                    record=json.loads(p.read_text())
                    if change=='audit':record['provider_calls_entered']=5
                    elif change=='uncertain':record['ledger'][7]['status']='ambiguous_provider_outcome_never_redispatch'
                    else:record['ledger'][7]=deepcopy(record['ledger'][6])
                    p.write_text(json.dumps(record));pin=json.loads(f[4].read_text());pin['source_file_hashes']=file_hashes(source);f[4].write_text(json.dumps(pin))
                transport=Mock()
                with self.assertRaises(ValidationError):self.invoke(f,transport)
                transport.assert_not_called()

    def test_fresh_approval_and_fixed_scope_required(self):
        with tempfile.TemporaryDirectory() as d:
            f=self.fixture(Path(d));transport=Mock()
            for key in original_tests.NEW:
                approval=deepcopy(original_tests.NEW);approval[key]=0 if key.startswith('available_') else None if key=='reviewed_spend_usd' else False
                with self.subTest(key=key),self.assertRaises(ValidationError):self.invoke(f,transport,approval=approval)
            pin=json.loads(f[4].read_text());pin['maximum_new_requests']=5;f[4].write_text(json.dumps(pin))
            with self.assertRaises(ValidationError):self.invoke(f,transport)
            pin['maximum_new_requests']=4;pin['execution_indices']=[9,10,11,12];f[4].write_text(json.dumps(pin))
            with self.assertRaises(ValidationError):self.invoke(f,transport)
            transport.assert_not_called()

    def test_failures_preserved_no_retries_and_uncertainty_blocks_continuation(self):
        for replies,count in (([HTTPReply(503,None)]*4,2),([HTTPReply(429,None)]*4,1),([TransportFailure('timeout')]*4,1)):
            with self.subTest(count=count),tempfile.TemporaryDirectory() as d:
                root=Path(d);f=self.fixture(root);transport=Mock(side_effect=replies)
                plan,summary=self.invoke(f,transport);self.assertEqual(transport.call_count,count)
                ledger=json.loads((plan.root/'summaries/SYN-010013/campaign-ledger.json').read_text())['ledger']
                self.assertEqual(ledger[:9],plan.manifest['provenance_bridge']['ledger'])
                self.assertTrue(any(r['status']!='terminal_completed' for r in ledger[9:]))
                batch.archive(f[0],plan.root,'SYN-010013',root/'upload')
                with self.assertRaises(ValidationError):self.invoke(f,transport,run_id='SYN-retry')
                self.assertEqual(transport.call_count,count)

    def test_historical_validation_does_not_bypass_dispatch_claim_or_overlap(self):
        with tempfile.TemporaryDirectory() as d:
            f=self.fixture(Path(d));transport=Mock()
            with self.contexts(f):plan=batch.prepare(f[0],'SYN-010013',original_tests.NEW,config=f[1],scope=f[4])
            p=plan.root/'manifests/SYN-overlap.json';p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text(json.dumps({'requests':[plan.manifest['requests'][0]]}))
            with self.assertRaises(ValidationError):self.invoke(f,transport)
            p.unlink();claim=plan.root/f"claims/{plan.manifest['dispatch_claim_key']}.json";claim.parent.mkdir(parents=True,exist_ok=True);claim.write_text('{}')
            with self.assertRaises(ValidationError):self.invoke(f,transport)
            transport.assert_not_called()

    def test_workflow_manual_fixed_source_scope_secret_and_history(self):
        w=json.loads((ROOT/'.github/workflows/flash-lite-010-013.yml').read_text())
        self.assertEqual(set(w['on']),{'workflow_dispatch'});self.assertFalse(w['concurrency']['cancel-in-progress'])
        job=w['jobs']['requests_010_013'];self.assertIn('github.run_attempt == 1',job['if'])
        steps=job['steps'];commands=[s['run'] for s in steps if 'run' in s]
        self.assertEqual(sum('--execute-live' in c for c in commands),1)
        self.assertTrue(all('--scope 010-013' in c for c in commands if 'flash_lite_next_four.py' in c))
        download=next(s for s in steps if s.get('uses')=='actions/download-artifact@v4')
        self.assertEqual(download['with']['run-id'],38108369312);self.assertEqual(download['with']['name'],'flash-lite-006-009-results')
        guard=next(s for s in steps if s.get('name')=='Reject any prior attempted four-request dispatch')['with']['script']
        self.assertIn("workflowId:'flash-lite-010-013.yml'",guard);self.assertIn("priorRunId:'38108369312'",guard)
        self.assertIn("expectedPriorCommit:'7309995160e8c41a7f762b1da67027860f3aa9d4'",guard)
        self.assertNotIn('dispatchWorkflow',json.dumps(w))
        for step in steps:
            if 'GOOGLE_API_KEY' in step.get('env',{}):self.assertEqual(step['env']['GOOGLE_API_KEY'],'${{ secrets.GOOGLE_API_KEY }}')
        pin=batch.load_scope(ROOT/batch.NEXT_SCOPE)
        self.assertEqual(pin['execution_indices'],[10,11,12,13]);self.assertFalse(pin['next_phases_enabled'])
