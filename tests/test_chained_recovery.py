"""Mock-only lineage fixtures; no research outputs or real provider requests."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import os
import io
from contextlib import redirect_stdout
import test_recovery as fixtures

from revocable_flow.chained_recovery import prepare_chained, preserve_bundle, file_hashes, stage_chained_upload
from revocable_flow.providers import GoogleProvider
from revocable_flow.providers.base import HTTPReply
from revocable_flow.runner import execute_plan, plan_run, _digest, _write
from revocable_flow.schema import ValidationError
from revocable_flow.recovery import main

FIRST_ID='gh-gemini-recovery-67890-1'
CHAIN_ID='gh-gemini-chained-98765-1'


class ChainedTests(unittest.TestCase):
    def test_chained_cli_mock_dispatch_and_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); bundle,_=self.fixture(root)
            def planner(*args,**kwargs):
                plan=plan_run(*args,**kwargs); plan.root=root/'new-results'; return plan
            argv=['recovery','--from-recovery','--source',str(bundle),'--source-run-id',FIRST_ID,
                  '--source-commit',fixtures.NEW_COMMIT,'--run-id',CHAIN_ID,
                  '--destination',str(root/'preserved'),'--execute-live']
            transport=Mock(return_value=HTTPReply(503,None))
            with patch('sys.argv',argv),patch.dict(os.environ,{'GOOGLE_API_KEY':fixtures.DUMMY_KEY}), \
                    patch('revocable_flow.runner._git',return_value={'commit':fixtures.NEW_COMMIT,'dirty':False}), \
                    patch('revocable_flow.chained_recovery.plan_run',side_effect=planner), \
                    patch('revocable_flow.recovery.recovery_transport',transport),redirect_stdout(io.StringIO()):
                self.assertEqual(main(),1)
            transport.assert_called_once()
            audit=json.loads((root/'new-results'/f'summaries/{CHAIN_ID}/dispatch-audit.json').read_text())
            self.assertEqual(audit['new_requests_attempted'],1)
            self.assertEqual(audit['retry_indices'],[2])
            self.assertEqual(audit['preserved_indices'],[1,3])
            self.assertEqual(audit['next_trial_attempt'],3)
            stage_chained_upload(root/'preserved',FIRST_ID,root/'new-results',CHAIN_ID,root/'upload')

    def fixture(self, root):
        bundle=root/'bundle'; bundle.mkdir()
        helper=fixtures.RecoveryTests()
        original=helper.fixture(bundle)
        first=helper.prepare(original,bundle)
        reply=HTTPReply(200,{'modelVersion':'SYN-fixture-version','candidates':[{'content':{'parts':[{'text':'{"action":"ALLOW","release_fields":["band_field"]}'}]}}]})
        transport=Mock(side_effect=[reply,HTTPReply(503,None)])
        with patch.dict(os.environ,{'GOOGLE_API_KEY':fixtures.DUMMY_KEY}),patch('revocable_flow.runner._git',return_value={'commit':fixtures.NEW_COMMIT,'dirty':False}):
            summary=execute_plan(first,execute_live=True,adapters={'google':GoogleProvider(transport=transport)})
        self.assertEqual(summary['completed'],1)
        _write(first.root,f'summaries/{FIRST_ID}/dispatch-audit.json',{
            'manifest_hash':first.manifest['manifest_hash'],'source_manifest_hash':original.manifest['manifest_hash'],
            'maximum_new_requests':2,'new_requests_attempted':2,'retry_indices':[1,2],'preserved_index':3})
        return bundle,first

    def prepare(self,bundle,root):
        def planner(*args,**kwargs):
            p=plan_run(*args,**kwargs); p.root=root/'new-results'; return p
        with patch('revocable_flow.runner._git',return_value={'commit':fixtures.NEW_COMMIT,'dirty':False}),patch('revocable_flow.chained_recovery.plan_run',side_effect=planner):
            return prepare_chained(bundle,FIRST_ID,fixtures.NEW_COMMIT,CHAIN_ID,config=fixtures.CONFIG)

    def execute(self,plan,transport):
        with patch.dict(os.environ,{'GOOGLE_API_KEY':fixtures.DUMMY_KEY}),patch('revocable_flow.runner._git',return_value={'commit':fixtures.NEW_COMMIT,'dirty':False}):
            return execute_plan(plan,execute_live=True,adapters={'google':GoogleProvider(transport=transport)})

    def test_one_request_original_index_mapping_and_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); bundle,first=self.fixture(root); before=file_hashes(bundle)
            plan=self.prepare(bundle,root)
            self.assertEqual([r['execution_index'] for r in plan.manifest['requests']],[2])
            self.assertEqual(plan.manifest['requests'][0],first.manifest['requests'][1])
            self.assertEqual(len(plan.scenarios),3)
            self.assertEqual(plan.manifest['recovery']['prior_trial_attempts'],{'1':2,'2':2,'3':1})
            self.assertEqual(plan.manifest['recovery']['next_trial_attempt'],3)
            transport=Mock(return_value=HTTPReply(200,{'candidates':[{'content':{'parts':[{'text':'{"action":"BLOCK","release_fields":[]}'}]}}]}))
            summary=self.execute(plan,transport)
            transport.assert_called_once(); self.assertTrue(summary['complete'])
            parsed=json.loads(next((plan.root/f'parsed/{CHAIN_ID}').glob('model-*/post_update/*.json')).read_text())
            self.assertEqual(parsed['score']['scenario_id'],plan.scenarios[1].scenario_id)
            self.assertEqual(file_hashes(bundle),before)
            stage_chained_upload(bundle,FIRST_ID,plan.root,CHAIN_ID,root/'upload')
            self.assertEqual(file_hashes(root/'upload/source'),file_hashes(bundle/'source'))
            self.assertEqual(file_hashes(root/'upload/recovery'),file_hashes(bundle/'recovery'))
            with self.assertRaises(ValidationError):
                self.execute(plan,transport)
            self.assertEqual(transport.call_count,1)
            with self.assertRaises(ValidationError):
                preserve_bundle(bundle,FIRST_ID,root/'upload')
            with self.assertRaises(ValidationError):
                self.prepare(bundle,root)

    def test_one_call_even_on503_and_resume_never_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); bundle,_=self.fixture(root); plan=self.prepare(bundle,root)
            transport=Mock(return_value=HTTPReply(503,None))
            summary=self.execute(plan,transport)
            self.assertFalse(summary['complete']); self.assertEqual(summary['attempted_provider_requests'],1)
            with patch.dict(os.environ,{'GOOGLE_API_KEY':fixtures.DUMMY_KEY}),patch('revocable_flow.runner._git',return_value={'commit':fixtures.NEW_COMMIT,'dirty':False}):
                execute_plan(plan,execute_live=True,resume=True,adapters={'google':GoogleProvider(transport=transport)})
            transport.assert_called_once()
            self.assertEqual(len(list(plan.root.rglob('*.started.json'))),1)

    def test_crash_is_ambiguous_and_not_repeated(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); bundle,_=self.fixture(root); plan=self.prepare(bundle,root)
            adapter=Mock(provider='google'); adapter.generate.side_effect=KeyboardInterrupt
            with patch.dict(os.environ,{'GOOGLE_API_KEY':fixtures.DUMMY_KEY}),patch('revocable_flow.runner._git',return_value={'commit':fixtures.NEW_COMMIT,'dirty':False}):
                with self.assertRaises(KeyboardInterrupt):
                    execute_plan(plan,execute_live=True,adapters={'google':adapter})
                summary=execute_plan(plan,execute_live=True,resume=True,adapters={'google':adapter})
            adapter.generate.assert_called_once()
            self.assertEqual(summary['ambiguous_attempts'],['model-02/post_update/002'])

    def test_hash_provenance_eligibility_and_history_rejections(self):
        for kind in ('manifest','model','original_hash','prompt','success_score','missing_response','429','already_success','summary','audit','deferred'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as directory:
                root=Path(directory); bundle,first=self.fixture(root)
                mpath=bundle/'recovery'/f'manifests/{FIRST_ID}.json'
                path=bundle/'recovery'/f'raw/{FIRST_ID}/model-02/post_update/002/attempt-01.response.json'
                record=json.loads(path.read_text())
                if kind in ('manifest','model','original_hash'):
                    m=json.loads(mpath.read_text())
                    if kind=='manifest': m['manifest_hash']='0'*64
                    else:
                        if kind=='model': m['requests'][1]['model']='SYN-other-model'
                        else: m['recovery']['source_manifest_hash']='0'*64
                        m.pop('manifest_hash'); m['manifest_hash']=_digest(m)
                    mpath.write_text(json.dumps(m))
                elif kind=='missing_response': path.unlink()
                elif kind=='success_score':
                    p=bundle/'recovery'/f'parsed/{FIRST_ID}/model-02/post_update/001.json'
                    r=json.loads(p.read_text()); r['raw_hash']='0'*64; p.write_text(json.dumps(r))
                elif kind=='summary':
                    p=next((bundle/'recovery'/f'summaries/{FIRST_ID}').glob('completion-*.json'))
                    r=json.loads(p.read_text()); r['ambiguous_attempts']=['model-02/post_update/002']; p.write_text(json.dumps(r))
                elif kind=='audit':
                    p=bundle/'recovery'/f'summaries/{FIRST_ID}/dispatch-audit.json'; p.write_text('{}')
                else:
                    if kind=='prompt': record['messages'][1]['content']='SYN-modified'
                    elif kind=='429': record['provider_error']['http_status']=429
                    elif kind=='already_success': record.update(provider_error=None,raw_output='{"action":"BLOCK","release_fields":[]}',parse_status='valid')
                    elif kind=='deferred': record['provider_error']['retry_after_seconds']=100000
                    path.write_text(json.dumps(record))
                with patch('urllib.request.urlopen',side_effect=AssertionError('no live HTTP')) as network:
                    with self.assertRaises((ValueError,OSError,KeyError,TypeError)):
                        self.prepare(bundle,root)
                    network.assert_not_called()

    def test_ancestor_mutation_withholds_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); bundle,_=self.fixture(root); plan=self.prepare(bundle,root)
            self.execute(plan,Mock(return_value=HTTPReply(503,None)))
            p=bundle/'recovery'/f'raw/{FIRST_ID}/model-02/post_update/001/attempt-01.response.json'
            p.write_bytes(p.read_bytes()+b' ')
            with self.assertRaises(ValidationError):
                stage_chained_upload(bundle,FIRST_ID,plan.root,CHAIN_ID,root/'upload')
            self.assertFalse((root/'upload').exists())

    def test_extra_ambiguous_claim_and_symlink_are_rejected(self):
        for kind in ('claim','symlink'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as directory:
                root=Path(directory); bundle,_=self.fixture(root)
                path=bundle/'recovery'/f'raw/{FIRST_ID}/model-02/post_update/002/attempt-02.started.json'
                if kind=='claim': path.write_text('{}')
                else: path.symlink_to(path.parent/'attempt-01.started.json')
                with self.assertRaises(ValidationError): self.prepare(bundle,root)

    def test_invalid_new_json_is_preserved_without_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); bundle,_=self.fixture(root); plan=self.prepare(bundle,root)
            transport=Mock(return_value=HTTPReply(200,{'candidates':[{'content':{'parts':[{'text':'SYN-invalid-json'}]}}]}))
            summary=self.execute(plan,transport)
            self.assertTrue(summary['complete']); transport.assert_called_once()
            record=json.loads(next(plan.root.rglob('*.response.json')).read_text())
            self.assertEqual(record['raw_output'],'SYN-invalid-json'); self.assertEqual(record['parse_status'],'invalid')

    def test_safe_upload_rejects_extra_success_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); bundle,_=self.fixture(root); plan=self.prepare(bundle,root)
            self.execute(plan,Mock(return_value=HTTPReply(503,None)))
            extra=plan.root/f'raw/{CHAIN_ID}/model-02/post_update/001/attempt-01.started.json'
            extra.parent.mkdir(parents=True); extra.write_text('{}')
            with self.assertRaises(ValidationError):
                stage_chained_upload(bundle,FIRST_ID,plan.root,CHAIN_ID,root/'upload')

    def test_workflow_manual_and_selects_first_recovery_artifact(self):
        w=json.loads((fixtures.ROOT/'.github/workflows/gemini-chained-recovery.yml').read_text())
        self.assertEqual(set(w['on']),{'workflow_dispatch'})
        self.assertFalse(w['on']['workflow_dispatch']['inputs']['budget_review_confirmed']['default'])
        job=w['jobs']['recovery']; self.assertIn('github.run_attempt == 1',job['if'])
        steps=job['steps']; recover=next(s for s in steps if s.get('id')=='recover')
        self.assertIn('--from-recovery',recover['run']); self.assertNotIn('--resume',recover['run'])
        self.assertEqual(recover['env']['GOOGLE_API_KEY'],'${{ secrets.GOOGLE_API_KEY }}')
        source=next(s for s in steps if s.get('id')=='source')
        self.assertIn("'.github/workflows/gemini-recovery.yml'",source['with']['script'])
        download=next(s for s in steps if s.get('uses','').startswith('actions/download-artifact'))
        self.assertEqual(download['with']['name'],'gemini-recovery-results')
        upload=next(s for s in steps if s.get('uses','').startswith('actions/upload-artifact'))
        self.assertIn("steps.artifacts.outputs.safe == 'true'",upload['if'])
