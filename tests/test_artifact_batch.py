"""Offline owner-bound batch protocol; no Google/GitHub requests or commits."""
from copy import deepcopy
from hashlib import sha1
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import Mock,patch
import zipfile

import test_continuation_checkpoint as previous
import test_four_request_bridge as initial
from revocable_flow import artifact_batch as b
from revocable_flow.chained_recovery import file_hashes
from revocable_flow.providers.base import HTTPReply,TransportFailure
from revocable_flow.runner import _digest
from revocable_flow.schema import ValidationError

ROOT=Path(__file__).resolve().parents[1]

class Crash(BaseException):pass

class ArtifactBatchTests(unittest.TestCase):
    def fixture(self,root):
        helper=previous.ContinuationCheckpointTests();f=helper.fixture(root)
        scope=json.loads((ROOT/b.SCOPE).read_text());scope['source_manifest_hash']=json.loads(f[3].read_text())['manifest_hash']
        # Synthetic archival attestation, never a claim about actual owner backups.
        old_scope=scope['predecessor_archive_summary']
        with f[0].contexts(f[1]):checkpoint,_=b.verify_checkpoint(f[2],config=f[1][1],pin=f[3],predecessor_scope=f[1][4])
        summary=json.loads((ROOT/old_scope).read_text());summary.update(batch_manifest_hash=checkpoint['manifest_hash'],
            cumulative_ledger_hash=_digest(checkpoint['ledger']),scientific_file_tree_hash=_digest(file_hashes(f[2])),
            terminal_identities=[{'request_key':r['request_key'],'identity':r['identity'],'status':r['status'],'primary_parse_status':r['primary_parse_status']} for r in checkpoint['ledger']],
            owner_verified_two_independent_archive_copies=True,archive_references=['SYN-copy-A','SYN-copy-B'])
        archive_path=root/'configs/archive-summary.json';archive_path.write_text(json.dumps(summary))
        scope['predecessor_archive_summary']=str(archive_path)
        path=root/'configs/artifact-scope.json';path.write_text(json.dumps(scope))
        with f[0].contexts(f[1]):p=b.prepare(f[2],'gh-artifact-900-1',scope=path,config=f[1][1],pin=f[3],predecessor_scope=f[1][4])
        context={'repository':'ankitpanda226/revocable-flow','run_id':900,'run_attempt':1,'job_id':901,'runner_id':902,
                 'execution_commit':initial.GIT['commit'],'invocation_nonce':'a'*64}
        review={flag:True for flag in b.FLAGS};review.update(reviewed_spend_usd=0,available_rpm_requests=15,available_rpd_requests=500,available_tpm_tokens=250000)
        record={'version':'flash-lite-invocation-authorization-v1','binding':context,'workflow_path':b.WORKFLOW,
            'scope_hash':_digest(p['planned']['requests']),'predecessor_manifest_hash':p['checkpoint']['manifest_hash'],
            'approved_at_epoch':time.time(),'fresh_review':review}
        evidence=self.evidence(record,p);return f,p,evidence,context
    def evidence(self,record,p):
        data=json.dumps(record)+'\n'
        return {'record':record,'record_bytes_utf8':data,'blob_sha':sha1(b'blob '+str(len(data.encode())).encode()+b'\0'+data.encode()).hexdigest(),
                'authorization_commit':'2'*40,'file_history':['2'*40],'path':p['policy']['authorization_path']}
    def reply(self,text='SYN OFFLINE INVALID'):
        r=initial.reply(text);r.body['usageMetadata']['totalTokenCount']=15;return r
    def invoke(self,f,p,evidence,context,transport,**kwargs):
        ticks=[0.0]
        with f[0].contexts(f[1]):return b.run(p,evidence,context,simulation=True,transport=transport,sleep=lambda s:ticks.__setitem__(0,ticks[0]+s),clock=lambda:ticks[0],**kwargs)
    def test_ten_requests_source_bytes_strict_unknowns_snapshots_and_archive(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);f,p,e,c=self.fixture(root);before=file_hashes(p['source']);t=Mock(return_value=self.reply('```json\n{"action":"BLOCK","release_fields":[]}\n```'))
            r=self.invoke(f,p,e,c,t);self.assertEqual(t.call_count,10);self.assertEqual(r['audit']['provider_calls_entered'],10)
            for call in t.call_args_list:self.assertEqual(call.args[2]['generationConfig'],{'temperature':0,'topP':1,'seed':20261007,'maxOutputTokens':512})
            receipt=b.seal(p,r['root'],r['batch_id'],root/'artifact');self.assertTrue(receipt['complete'])
            ledger=b.verify_sealed(p,root/'artifact',receipt['file_tree_hash']);self.assertEqual(len(ledger),23);self.assertEqual(ledger[:13],p['checkpoint']['ledger'])
            for row in ledger[13:]:self.assertEqual(row['status'],'terminal_completed');self.assertIsNone(row['primary_score']['privacy_violation']);self.assertIsNone(row['primary_score']['over_refusal'])
            self.assertEqual(file_hashes(root/'artifact/source'),before);self.assertEqual(file_hashes(p['source']),before)
            with self.assertRaises(ValidationError):b.seal(p,r['root'],r['batch_id'],root/'artifact')
            with self.assertRaises(FileExistsError):self.invoke(f,p,e,c,t)
            self.assertEqual(t.call_count,10)
    def test_fresh_invocation_run_job_and_attempt_cannot_reuse_approval(self):
        with tempfile.TemporaryDirectory() as d:
            f,p,e,c=self.fixture(Path(d));t=Mock()
            for field,value in (('invocation_nonce','b'*64),('run_id',999),('run_attempt',2),('job_id',903),('runner_id',904)):
                changed={**c,field:value}
                with self.subTest(field=field),self.assertRaises(ValidationError):self.invoke(f,p,e,changed,t)
            changed=deepcopy(e);changed['file_history'].append('3'*40)
            with self.assertRaises(ValidationError):self.invoke(f,p,changed,c,t)
            t.assert_not_called()
    def test_fresh_gates_budget_quota_and_live_disable(self):
        with tempfile.TemporaryDirectory() as d:
            f,p,e,c=self.fixture(Path(d));t=Mock()
            for flag in b.FLAGS:
                record=deepcopy(e['record']);record['fresh_review'][flag]=False
                with self.subTest(flag=flag),self.assertRaises(ValidationError):self.invoke(f,p,self.evidence(record,p),c,t)
            for field,value in (('reviewed_spend_usd',None),('reviewed_spend_usd',4),('available_rpm_requests',9),('available_rpd_requests',9),('available_tpm_tokens',0)):
                record=deepcopy(e['record']);record['fresh_review'][field]=value
                with self.assertRaises(ValidationError):self.invoke(f,p,self.evidence(record,p),c,t)
            record=deepcopy(e['record']);record['approved_at_epoch']=0
            with self.assertRaises(ValidationError):self.invoke(f,p,self.evidence(record,p),c,t)
            with self.assertRaises(ValidationError):b.run(p,e,c,transport=t)
            p['archival_summary']['owner_verified_two_independent_archive_copies']=False
            with self.assertRaises(ValidationError):self.invoke(f,p,e,c,t)
            t.assert_not_called()
    def test_crashes_never_allow_fresh_invocation_and_partial_seal_blocks_continuation(self):
        for point,count in (('after_claim_before_call',0),('during_transport',0),('after_response_before_score',1),('after_result',1)):
            with self.subTest(point=point),tempfile.TemporaryDirectory() as d:
                root=Path(d);f,p,e,c=self.fixture(root);t=Mock(return_value=self.reply())
                def crash(phase,index):
                    if phase==point:raise Crash()
                with self.assertRaises(Crash):self.invoke(f,p,e,c,t,crash_hook=crash)
                self.assertEqual(t.call_count,count)
                receipt=b.seal(p,p['base'].root,p['base'].manifest['run_id'],root/'partial');self.assertFalse(receipt['complete'])
                with self.assertRaises(ValidationError):b.verify_sealed(p,root/'partial',receipt['file_tree_hash'])
                other=deepcopy(p);other['base'].root=root/'different-runner'
                with self.assertRaises(ValidationError):self.invoke(f,other,e,{**c,'invocation_nonce':'b'*64},t)
                self.assertEqual(t.call_count,count)
    def test_http_failure_and_ambiguous_transport_consume_identity_no_privacy_score(self):
        for reply in (HTTPReply(503,{}),HTTPReply(429,{}),TransportFailure('timeout')):
            with self.subTest(kind=type(reply).__name__),tempfile.TemporaryDirectory() as d:
                root=Path(d);f,p,e,c=self.fixture(root);t=Mock(side_effect=[reply]);r=self.invoke(f,p,e,c,t)
                self.assertEqual(t.call_count,1);self.assertIsNotNone(r['audit']['stop_reason'])
                receipt=b.seal(p,r['root'],r['batch_id'],root/'failure');self.assertFalse(receipt['complete'])
                ledger=b._read(r['root'],f"batches/{r['batch_id']}/campaign-ledger.json")['ledger']
                self.assertEqual(len(ledger),14);self.assertNotEqual(ledger[-1]['status'],'not_attempted');self.assertNotIn('primary_score',ledger[-1])
                with self.assertRaises(ValidationError):b.verify_sealed(p,root/'failure',receipt['file_tree_hash'])
    def test_tampered_predecessor_score_or_archive_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);f,p,e,c=self.fixture(root);t=Mock(return_value=self.reply());r=self.invoke(f,p,e,c,t)
            parsed=next((r['root']/f"parsed/{r['batch_id']}-i014").glob('model-01/post_update/*.json'))
            value=json.loads(parsed.read_text());value['score']['privacy_violation']=False;parsed.write_text(json.dumps(value))
            with self.assertRaises(ValidationError):b.seal(p,r['root'],r['batch_id'],root/'bad')
            next(p['source'].rglob('*.response.json')).write_text('{}')
            with self.assertRaises(ValidationError):self.invoke(f,p,e,{**c,'invocation_nonce':'b'*64},t)
    def test_two_copy_archive_receipt_and_zip_validation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);f,p,e,c=self.fixture(root);r=self.invoke(f,p,e,c,Mock(return_value=self.reply()))
            seal=b.seal(p,r['root'],r['batch_id'],root/'artifact')
            with zipfile.ZipFile(root/'archive.zip','w') as z:
                for file in (root/'artifact').rglob('*'):
                    if file.is_file():z.write(file,file.relative_to(root/'artifact'))
            summary=b.archival_summary(root/'artifact',root/'archive.zip',seal['file_tree_hash'])
            self.assertFalse(summary['archival_copies_verified_by_owner']);self.assertTrue(summary['complete'])
            with zipfile.ZipFile(root/'archive.zip','a') as z:z.writestr('unexpected.json','{}')
            with self.assertRaises(ValidationError):b.archival_summary(root/'artifact',root/'archive.zip',seal['file_tree_hash'])
    def test_manual_workflow_has_no_writer_privilege_and_static_live_gate(self):
        w=json.loads((ROOT/b.WORKFLOW).read_text());self.assertEqual(set(w['on']),{'workflow_dispatch'})
        self.assertEqual(w['permissions'],{'contents':'read','actions':'read'});self.assertEqual(len(w['jobs']),1)
        self.assertNotIn('RESEARCH_JOURNAL_TOKEN',json.dumps(w));self.assertNotIn('environment',w['jobs']['artifact_batch'])
        self.assertFalse(w['concurrency']['cancel-in-progress'])
        execute=next(s for s in w['jobs']['artifact_batch']['steps'] if s.get('id')=='execute')
        self.assertEqual(execute['if'],'${{ false }}');self.assertEqual(execute['env']['GOOGLE_API_KEY'],'${{ secrets.GOOGLE_API_KEY }}')
        policy=json.loads((ROOT/b.SCOPE).read_text());self.assertFalse(policy['live_execution_enabled'])
        self.assertEqual([r['execution_index'] for r in policy['requests']],list(range(14,24)))
    def test_history_guard_blocks_higher_id_runs_missing_steps_and_reruns(self):
        guard=ROOT/'.github/scripts/artifact_batch_history_guard.js'
        script='''const p=JSON.parse(require('fs').readFileSync(0,'utf8'));
const actions={listWorkflowRuns:'runs',listJobsForWorkflowRunAttempt:'jobs'};
const github={rest:{actions},paginate:async(method,args)=>method==='runs'?p.runs:p.jobs};
require(process.argv[1])({github,context:{repo:{owner:'ankitpanda226',repo:'revocable-flow'},runId:900}})
.then(()=>process.stdout.write('ok')).catch(()=>process.stdout.write('blocked'));'''
        def invoke(runs,jobs):
            return subprocess.run(['node','-e',script,str(guard)],input=json.dumps({'runs':runs,'jobs':jobs}),text=True,capture_output=True,check=True).stdout
        self.assertEqual(invoke([],[]),'ok')
        run={'id':901,'status':'completed','run_attempt':1};step={'name':'Execute owner-bound frozen 014–023','status':'completed','conclusion':'skipped'}
        self.assertEqual(invoke([run],[{'conclusion':'success','steps':[step]}]),'ok')
        for change in ('started','missing','repeated','unfinished','rerun','active'):
            r=deepcopy(run);s=deepcopy(step);jobs=[{'conclusion':'success','steps':[s]}]
            if change=='started':s['conclusion']='failure'
            elif change=='missing':jobs[0]['steps']=[]
            elif change=='repeated':jobs[0]['steps']=[s,s]
            elif change=='unfinished':s['status']='in_progress'
            elif change=='rerun':r['run_attempt']=2
            else:r['status']='in_progress'
            self.assertEqual(invoke([r],jobs),'blocked')
    def test_readonly_owner_waiter_binds_service_and_fresh_nonce(self):
        import base64
        file=ROOT/'.github/scripts/artifact_batch_control.py'
        spec=importlib.util.spec_from_file_location('owner_waiter',file);waiter=importlib.util.module_from_spec(spec);spec.loader.exec_module(waiter)
        with tempfile.TemporaryDirectory() as d:
            f,p,e,c=self.fixture(Path(d))
            info={'id':900,'head_sha':initial.GIT['commit'],'head_branch':'main','event':'workflow_dispatch','path':b.WORKFLOW,'run_attempt':1}
            jobs={'total_count':1,'jobs':[{'id':901,'name':'artifact_batch','status':'in_progress','runner_id':902,'run_id':900}]}
            content={'type':'file','encoding':'base64','sha':e['blob_sha'],'content':base64.b64encode(e['record_bytes_utf8'].encode()).decode()}
            read=Mock(side_effect=[info,jobs,content,[{'sha':'2'*40}]])
            env={'GITHUB_RUN_ID':'900','GITHUB_RUN_ATTEMPT':'1','GITHUB_REF':'refs/heads/main','GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_SHA':initial.GIT['commit']}
            with patch.dict(os.environ,env,clear=True),patch.object(waiter.uuid,'uuid4',return_value=Mock(hex='a'*32)),patch('builtins.print'):
                evidence,context=waiter.wait_for_owner(p,read=read,sleep=Mock())
            self.assertEqual(context,c);self.assertEqual(evidence,e)
            self.assertTrue(all('/repos/ankitpanda226/revocable-flow/' in call.args[0] for call in read.call_args_list))
            with patch.dict(os.environ,env,clear=True),patch('builtins.print'),self.assertRaises(FileExistsError):waiter.wait_for_owner(p,read=Mock(side_effect=[info,jobs]))
