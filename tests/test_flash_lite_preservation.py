"""Synthetic diagnostic fixtures; no GitHub or Google request is executed."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
from unittest.mock import patch
from hashlib import sha256

from revocable_flow.schema import ValidationError

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('preservation',ROOT/'.github/scripts/preserve_flash_lite_diagnostic.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)


class PreservationTests(unittest.TestCase):
    def test_workflow_metadata_is_valid_json_with_mocked_github_response(self):
        workflow=json.loads((ROOT/'.github/workflows/preserve-flash-lite-diagnostic.yml').read_text())
        script=next(s for s in workflow['jobs']['preserve']['steps']
                    if s.get('uses')=='actions/github-script@v7')['with']['script']
        wrapper='''
const p=JSON.parse(require('fs').readFileSync(0,'utf8'));
process.env.RUNNER_TEMP=p.directory;
const fn=new (Object.getPrototypeOf(async function(){}).constructor)('github','context',p.script);
const github={rest:{actions:{getWorkflowRun:async args=>{
 if(args.run_id!==37854150199) throw new Error('Wrong run'); return {data:p.run};
}}}};
fn(github,{repo:{owner:'ankitpanda226',repo:'revocable-flow'}}).catch(()=>process.exitCode=1);
'''
        with tempfile.TemporaryDirectory() as directory:
            source,_,dest,_,_=self.fixture(Path(directory))
            run={'id':helper.RUN_ID,'html_url':helper.URL,'head_sha':helper.COMMIT,'run_attempt':1,
                 'path':'.github/workflows/flash-lite-availability.yml','event':'workflow_dispatch',
                 'head_branch':'main','status':'completed','conclusion':'success','created_at':'2026-10-08T00:00:00Z'}
            subprocess.run(['node','-e',wrapper],input=json.dumps({'directory':directory,'script':script,'run':run}),
                           text=True,check=True,capture_output=True)
            metadata=Path(directory)/'source-run.json'
            self.assertEqual(json.loads(metadata.read_text())['source_run_id'],helper.RUN_ID)
            manifest=helper.preserve(source,metadata,dest)
            self.assertEqual(manifest['source_run_id'],helper.RUN_ID)

    def fixture(self, root):
        source=root/'source';source.mkdir()
        report={'status':'success','http_status':200,'requests_attempted':1,'requested_model':helper.MODEL,
                'models':[{'name':helper.MODEL,'supported_methods':['generateContent']}],
                'list_complete':True,'target_listed':True,'target_supports_generateContent':True}
        provenance={'source_run_id':helper.RUN_ID,'source_run_url':helper.URL,'source_head_sha':helper.COMMIT,
                    'source_run_attempt':1,'source_workflow':'.github/workflows/flash-lite-availability.yml',
                    'source_event':'workflow_dispatch','source_branch':'main','source_conclusion':'success',
                    'source_created_at':'2026-10-08T00:00:00Z'}
        raw=json.dumps(report,indent=3)+'\n\n'
        (source/'flash-lite-availability.json').write_text(raw)
        metadata=root/'metadata.json';metadata.write_text(json.dumps(provenance))
        return source,metadata,root/'destination',report,provenance

    def test_preserves_bytes_hashes_and_source_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            source,meta,dest,_,_=self.fixture(Path(directory))
            original=(source/'flash-lite-availability.json').read_bytes()
            with patch('urllib.request.urlopen',side_effect=AssertionError('network forbidden')):
                manifest=helper.preserve(source,meta,dest)
            self.assertEqual((dest/'flash-lite-availability.json').read_bytes(),original)
            self.assertEqual((source/'flash-lite-availability.json').read_bytes(),original)
            self.assertEqual((dest/'source-run.json').read_bytes(),meta.read_bytes())
            self.assertEqual(manifest['diagnostic_sha256'],sha256(original).hexdigest())
            self.assertEqual(manifest['generation_requests_made'],0)
            with self.assertRaises(ValidationError):helper.preserve(source,meta,dest)
            self.assertEqual((dest/'flash-lite-availability.json').read_bytes(),original)

    def test_model_method_and_response_mismatches_fail_before_writes(self):
        changes=({'requested_model':'models/SYN-other'}, {'requests_attempted':2}, {'target_listed':False},
                 {'models':[]}, {'models':[{'name':helper.MODEL,'supported_methods':['countTokens']}]},
                 {'status':'http_failure'}, {'env':{'SYN':'forbidden'}})
        for change in changes:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as directory:
                source,meta,dest,report,_=self.fixture(Path(directory));report.update(change)
                (source/'flash-lite-availability.json').write_text(json.dumps(report))
                with self.assertRaises(ValidationError):helper.preserve(source,meta,dest)
                self.assertFalse(dest.exists())

    def test_wrong_run_commit_workflow_and_attempt_fail_before_writes(self):
        for field,value in (('source_run_id',1),('source_head_sha','0'*40),('source_run_attempt',2),
                            ('source_workflow','SYN-other.yml'),('source_event','push'),('source_created_at','bad')):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as directory:
                source,meta,dest,_,provenance=self.fixture(Path(directory));provenance[field]=value
                meta.write_text(json.dumps(provenance))
                with self.assertRaises(ValidationError):helper.preserve(source,meta,dest)
                self.assertFalse(dest.exists())

    def test_extra_files_symlinks_and_credentials_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source,meta,dest,report,_=self.fixture(Path(directory))
            extra=source/'SYN-extra.txt';extra.write_text('SYN-not-executed')
            with self.assertRaises(ValidationError):helper.preserve(source,meta,dest)
            extra.unlink();file=source/'flash-lite-availability.json';file.unlink();file.symlink_to(meta)
            with self.assertRaises(ValidationError):helper.preserve(source,meta,dest)
            file.unlink();file.write_text(json.dumps(report))
            with patch.dict('os.environ',{'GITHUB_TOKEN':'generateContent'},clear=True):
                with self.assertRaises(ValidationError):helper.preserve(source,meta,dest)
            self.assertFalse(dest.exists())

    def test_workflow_only_downloads_fixed_run_without_google_secret_or_generation(self):
        workflow=json.loads((ROOT/'.github/workflows/preserve-flash-lite-diagnostic.yml').read_text())
        self.assertEqual(workflow['on'],{'workflow_dispatch':{}})
        self.assertEqual(workflow['permissions'],{'contents':'read','actions':'read'})
        steps=workflow['jobs']['preserve']['steps']
        download=next(s for s in steps if s.get('uses','').startswith('actions/download-artifact@'))
        self.assertEqual(download['with']['run-id'],str(helper.RUN_ID))
        self.assertEqual(download['with']['repository'],'ankitpanda226/revocable-flow')
        self.assertEqual(download['with']['name'],'flash-lite-availability')
        upload=next(s for s in steps if s.get('uses','').startswith('actions/upload-artifact@'))
        self.assertEqual(upload['if'],"${{ steps.inspect.outputs.safe == 'true' }}")
        self.assertEqual(upload['with']['path'],'${{ runner.temp }}/preserved-diagnostic/')
        for forbidden in ('GOOGLE_API_KEY','generativelanguage.googleapis.com','generateContent','execute-live','pilot-run'):
            self.assertNotIn(forbidden,json.dumps(workflow))
