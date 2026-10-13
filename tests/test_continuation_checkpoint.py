"""Offline checkpoint and crash-state specifications; no live persistence or calls."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import test_flash_lite_010_013 as previous
import test_four_request_bridge as initial
from revocable_flow import continuation_checkpoint as c
from revocable_flow import four_request_bridge as batch
from revocable_flow.chained_recovery import file_hashes
from revocable_flow.runner import _digest
from revocable_flow.schema import ValidationError

ROOT=Path(__file__).resolve().parents[1]

class ContinuationCheckpointTests(unittest.TestCase):
    def fixture(self,root):
        helper=previous.Requests010013Tests();f=helper.fixture(root)
        plan,_=helper.invoke(f,Mock(return_value=initial.reply('SYN-invalid-format')))
        source=root/'thirteen';batch.archive(f[0],plan.root,'SYN-010013',source)
        pin=json.loads((ROOT/c.PIN).read_text());pin.update(run_id='SYN-010013',commit=initial.GIT['commit'],
            manifest_hash=plan.manifest['manifest_hash'],scientific_file_hashes=file_hashes(source))
        pin_path=root/'configs/checkpoint.json';pin_path.write_text(json.dumps(pin))
        return helper,f,source,pin_path

    def verify(self,fixture):
        helper,f,source,pin=fixture
        with helper.contexts(f):return c.verify_checkpoint(source,pin=pin,config=f[1],predecessor_scope=f[4])

    def test_complete_chain_verification_preserves_all_primary_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            f=self.fixture(Path(d));before=file_hashes(f[2]);checkpoint,schedule=self.verify(f)
            self.assertEqual(len(before),68);self.assertEqual(len(checkpoint['ledger']),13)
            self.assertEqual(before,file_hashes(f[2]))
            for case in checkpoint['cases']:
                if not case['score']['valid']:
                    for field in ('privacy_violation','over_refusal','stale_leak'):self.assertIsNone(case['score'][field])
            plan=c.plan_range(checkpoint,schedule,'post_update',14,23,approved_for_offline_planning=True)
            self.assertFalse(plan['live_execution_enabled']);self.assertEqual(plan['maximum_new_requests'],10)
            self.assertEqual([r['request_key'] for r in plan['requests']],[f'model-01/post_update/{i:03d}' for i in range(14,24)])
            self.assertEqual(plan['automatic_retries'],0);self.assertEqual(plan['maximum_attempts_per_identity'],1)
            self.assertFalse(plan['later_phases_enabled']);self.assertEqual(plan['parameters'],c.PARAMETERS)

    def test_range_overlap_skips_invalid_values_and_missing_approval_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            checkpoint,schedule=self.verify(self.fixture(Path(d)))
            self.assertEqual(len(c.plan_range(checkpoint,schedule,'post_update',14,33,approved_for_offline_planning=True)['requests']),20)
            for args in [('post_update',13,22),('post_update',15,24),('post_update',14,34),
                         ('pre_update',1,10),('post_update',True,4),('post_update',14,41)]:
                with self.subTest(args=args),self.assertRaises(ValidationError):
                    c.plan_range(checkpoint,schedule,*args,approved_for_offline_planning=True)
            with self.assertRaises(ValidationError):c.plan_range(checkpoint,schedule,'post_update',14,23)
            for status in ('ambiguous_claimed_never_redispatch','terminal_provider_failure','not_attempted'):
                altered=deepcopy(checkpoint);altered['ledger'][0]['status']=status
                with self.assertRaises(ValidationError):c.plan_range(altered,schedule,'post_update',14,23,approved_for_offline_planning=True)
            altered=deepcopy(checkpoint);altered['ledger'][1]=altered['ledger'][0]
            with self.assertRaises(ValidationError):c.plan_range(altered,schedule,'post_update',14,23,approved_for_offline_planning=True)

    def test_repinned_primary_tampering_audit_and_duplicate_rejected(self):
        for change in ('score','duplicate','audit'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as d:
                f=self.fixture(Path(d));root=f[2]/'batch'
                if change=='score':
                    p=root/'parsed/SYN-010013/model-01/post_update/010.json';r=json.loads(p.read_text());r['score']['privacy_violation']=False
                elif change=='duplicate':
                    p=root/'summaries/SYN-010013/campaign-ledger.json';r=json.loads(p.read_text());r['ledger'][12]=r['ledger'][11]
                else:
                    p=root/'summaries/SYN-010013/dispatch-audit.json';r=json.loads(p.read_text());r['automatic_retries']=1
                p.write_text(json.dumps(r));pin=json.loads(f[3].read_text());pin['scientific_file_hashes']=file_hashes(f[2]);f[3].write_text(json.dumps(pin))
                with self.assertRaises(ValidationError):self.verify(f)

    def test_offline_crash_state_spec_never_reopens_existing_claim(self):
        identity={'provider':'google','model':c.MODEL,'scenario_id':'SYN-example','condition':'post_update','repetition':1}
        claim={'identity':identity,'identity_hash':_digest(identity),'plan_hash':'SYN-plan'}
        self.assertEqual(c.claim_disposition(identity),'unclaimed_requires_fresh_approval_and_atomic_remote_claim')
        # Crash before dispatch, during transport, or after receiving but before
        # publishing: all leave the same durable claim and prohibit redispatch.
        for crash in ('before_call','during_transport','after_response_before_publish'):
            with self.subTest(crash=crash):
                self.assertEqual(c.claim_disposition(identity,claim=claim),'claimed_unknown_never_redispatch')
        for result in ('valid','invalid_json','HTTP_503','HTTP_429','timeout'):
            record={'claim_hash':_digest(claim),'status':result}
            self.assertEqual(c.claim_disposition(identity,claim=claim,terminal_record=record),'terminal_never_redispatch')
        with self.assertRaises(ValidationError):c.claim_disposition(identity,terminal_record={'status':'valid'})
        with self.assertRaises(ValidationError):c.claim_disposition(identity,claim={**claim,'identity_hash':'wrong'})
        with self.assertRaises(ValidationError):c.claim_disposition(identity,claim=claim,terminal_record={'claim_hash':'wrong'})

    def test_offline_workflow_cannot_generate_or_bypass_plan_approval(self):
        workflow=json.loads((ROOT/'.github/workflows/flash-lite-continuation-plan.yml').read_text())
        self.assertEqual(set(workflow['on']),{'workflow_dispatch'})
        self.assertEqual(workflow['permissions'],{'contents':'read','actions':'read'})
        self.assertFalse(workflow['on']['workflow_dispatch']['inputs']['approve_offline_plan']['default'])
        job=workflow['jobs']['plan'];self.assertIn('inputs.approve_offline_plan',job['if'])
        text=json.dumps(workflow)
        for forbidden in ('GOOGLE_API_KEY','--execute-live','dispatchWorkflow','run_free_tier_phase.py','generateContent'):
            self.assertNotIn(forbidden,text)
        step=next(s for s in job['steps'] if s.get('id')=='plan')
        self.assertIn('revocable_flow.continuation_checkpoint',step['run'])
        self.assertIn('"$PLAN_START"',step['run']);self.assertNotIn('${{ inputs.',step['run'])
        self.assertEqual(c.PARAMETERS,{'temperature':0,'top_p':1,'seed':20261007,'max_output_tokens':512})
        self.assertFalse(json.loads((ROOT/c.PIN).read_text())['live_execution_enabled'])
