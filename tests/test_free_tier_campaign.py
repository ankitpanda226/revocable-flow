"""All candidate execution tests use invented offline configuration and mock transport."""
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

from revocable_flow.free_tier_campaign import MODEL,PHASES,stage_plan,execute_stage,validate_history,stage_campaign
from revocable_flow.protocol import load_protocol_config
from revocable_flow.providers import GoogleProvider
from revocable_flow.providers.base import HTTPReply
from revocable_flow.schema import ValidationError

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'configs/free_tier_pilot_v1.yaml'
DUMMY='SYN-flash-lite-fixture-not-real'
GIT={'commit':'1'*40,'dirty':False}


class FreeTierCampaignTests(unittest.TestCase):
    def fixture(self,root):
        (root/'configs').mkdir()
        c=load_protocol_config(CONFIG);c['benchmark']['path']=str(ROOT/'data/pilot/scenarios.jsonl')
        model=c['model_matrix'][0];model.update(status='verified',notes='SYN mock-only capability verification; not actual provider evidence.',
                                               parameter_support={k:'supported' for k in model['parameter_support']})
        c['models']=[{'provider':'google','model':MODEL}]
        cfg=root/'configs/candidate.yaml';cfg.write_text(json.dumps(c))
        policy=json.loads((ROOT/'configs/free_tier_policy_v1.json').read_text())
        for k in ('execution_enabled','free_tier_verified','available_to_key_verified','generate_content_verified','json_output_verified','parameter_support_verified'):
            policy[k]=True
        policy['budget']['account_free_tier_eligibility_verified']=True
        policy['controls']['further_live_implementation_review_required']=False
        from hashlib import sha256
        evidence=root/'SYN-evidence.txt';evidence.write_text('SYN synthetic offline evidence, not provider documentation')
        diagnostic=root/'SYN-diagnostic.json';diagnostic.write_text(json.dumps({'status':'success','requested_model':'models/'+MODEL,'target_listed':True,'target_supports_generateContent':True,'models':[{'name':'models/'+MODEL,'supported_methods':['generateContent']}]}))
        parameters=root/'SYN-parameters.json';parameters.write_text(json.dumps({'model_id':MODEL,'parameter_support':model['parameter_support'],'documentation_source':'SYN-mock-only','verification_date':'2026-10-08'}))
        tier=root/'SYN-tier.json';tier.write_text(json.dumps({'model_id':MODEL,'tier':'Free','project_reference':'SYN-fictional-project','verification_date':'2026-10-08','verification_basis':'SYN-mock-only'}))
        for file_key,hash_key in (('diagnostic_file','diagnostic_sha256'),('official_pricing_file','official_pricing_sha256')):
            source=diagnostic if file_key=='diagnostic_file' else evidence
            policy['evidence'][file_key]=str(source);policy['evidence'][hash_key]=sha256(source.read_bytes()).hexdigest()
        for name,source in (('parameter_support',parameters),('account_tier',tier)):
            policy['evidence'][name+'_file']=str(source);policy['evidence'][name+'_sha256']=sha256(source.read_bytes()).hexdigest()
        policy['evidence']['availability_verification'].update(verification_date='2026-10-08',github_actions_run_url='https://github.com/ankitpanda226/revocable-flow/actions/runs/123')
        pol=root/'configs/policy.json';pol.write_text(json.dumps(policy))
        return cfg,pol

    def transport(self,text='{"action":"BLOCK","release_fields":[]}'):
        return Mock(return_value=HTTPReply(200,{'modelVersion':'SYN-candidate-version','candidates':[{'content':{'parts':[{'text':text}]}}],'usageMetadata':{'promptTokenCount':11,'candidatesTokenCount':7}}))

    def execute(self,phase,run,config,policy,transport,history=None):
        with patch.dict(os.environ,{'GOOGLE_API_KEY':DUMMY}),patch('revocable_flow.runner._git',return_value=GIT):
            return execute_stage(phase,run,config=config,policy=policy,adapters={'google':GoogleProvider(transport=transport)},
                                 history=history,reviewed_spend=0,approved=True,expected_previous_commit=GIT['commit'] if history else None)

    def test_phase_caps_frozen_mapping_and_no_38_exceptions(self):
        self.assertEqual(GoogleProvider.allowed_omissions(MODEL),frozenset())
        with tempfile.TemporaryDirectory() as directory:
            cfg,_=self.fixture(Path(directory));keys=set()
            for phase in PHASES:
                plan=stage_plan(phase,'SYN-'+phase,config=cfg)
                self.assertEqual(plan.manifest['expected_request_count'],len(PHASES[phase][1]))
                self.assertEqual(plan.manifest['execution_limits']['max_attempts_per_request'],1)
                current={r['request_key'] for r in plan.manifest['requests']}
                self.assertFalse(keys & current);keys.update(current)
                self.assertEqual(len(plan.scenarios),40)
            self.assertEqual(len(keys),80)

    def test_full_mock_campaign_80_unique_records_and_all_ancestors(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);cfg,pol=self.fixture(root);history=None;transport=self.transport()
            for n,phase in enumerate(PHASES):
                from revocable_flow.chained_recovery import file_hashes
                preserved=file_hashes(history) if history else {}
                plan,summary=self.execute(phase,'SYN-stage-'+str(n),cfg,pol,transport,history)
                self.assertTrue(summary['complete'])
                destination=root/('archive-'+str(n))
                stage_campaign(history,plan.root,plan.manifest['run_id'],destination)
                archived=file_hashes(destination)
                self.assertTrue(all(archived.get(name)==digest for name,digest in preserved.items()))
                history=destination
            self.assertEqual(transport.call_count,80)
            self.assertEqual(len(list(history.rglob('*.response.json'))),80)
            manifests=[json.loads(p.read_text()) for p in (history/'manifests').glob('*.json')]
            keys=[r['request_key'] for m in manifests for r in m['requests']]
            self.assertEqual(len(set(keys)),80)
            with self.assertRaises(ValidationError):stage_campaign(None,plan.root,plan.manifest['run_id'],history)

    def test_stops429_and_two_consecutive503_preserving_failures(self):
        for status,count in ((429,1),(503,2)):
            with self.subTest(status=status),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);cfg,pol=self.fixture(root)
                first,_=self.execute('connectivity','SYN-first',cfg,pol,self.transport())
                stage_campaign(None,first.root,'SYN-first',root/'history')
                transport=Mock(return_value=HTTPReply(status,None))
                plan,summary=self.execute('small_pilot','SYN-next',cfg,pol,transport,root/'history')
                self.assertEqual(transport.call_count,count)
                self.assertEqual(summary['attempted_provider_requests'],count)
                self.assertFalse(summary['complete'])
                self.assertEqual(len(summary['unattempted_requests']),4-count)
                self.assertEqual(len(summary['infrastructure_missing']),count)
                stage_campaign(root/'history',plan.root,'SYN-next',root/'failure-archive')
                self.assertEqual(len(list((root/'failure-archive'/f'raw/SYN-next').rglob('*.response.json'))),count)
                with self.assertRaises(ValidationError):validate_history(root/'failure-archive','remaining_post',config=cfg)

    def test_prior_complete_stage_required_and_success_not_repeated(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);cfg,pol=self.fixture(root);transport=self.transport()
            first,_=self.execute('connectivity','SYN-first',cfg,pol,transport)
            self.assertEqual(transport.call_count,1)
            stage_campaign(None,first.root,'SYN-first',root/'history')
            with self.assertRaises(ValidationError):self.execute('connectivity','SYN-repeat',cfg,pol,transport,root/'history')
            with self.assertRaises(ValidationError):self.execute('paired_pre','SYN-skip',cfg,pol,transport,root/'history')
            second,summary=self.execute('small_pilot','SYN-next',cfg,pol,transport,root/'history')
            self.assertEqual(transport.call_count,5);self.assertTrue(summary['complete'])
            self.assertEqual([r['execution_index'] for r in second.manifest['requests']],[2,3,4,5])
            stage_campaign(root/'history',second.root,'SYN-next',root/'next-history')
            validate_history(root/'next-history','remaining_post',config=cfg)
            with self.assertRaises(ValidationError):self.execute('small_pilot','SYN-next',cfg,pol,transport,root/'history')
            self.assertEqual(transport.call_count,5)

    def test_unknown_budget_bad_evidence_and_ambiguous_history_block(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);cfg,pol=self.fixture(root)
            for value in (None,4,float('nan'),-1):
                with self.assertRaises(ValidationError):execute_stage('connectivity','SYN-bad',config=cfg,policy=pol,reviewed_spend=value,approved=True)
            first,_=self.execute('connectivity','SYN-first',cfg,pol,self.transport())
            stage_campaign(None,first.root,'SYN-first',root/'history')
            extra=root/'history/raw/SYN-first/model-01/post_update/001/attempt-02.started.json';extra.write_text('{}')
            with self.assertRaises(ValidationError):validate_history(root/'history','small_pilot',config=cfg)
            extra.unlink()
            p=json.loads(pol.read_text());p['evidence']['diagnostic_sha256']='0'*64;pol.write_text(json.dumps(p))
            with self.assertRaises(ValidationError):self.execute('connectivity','SYN-bad',cfg,pol,self.transport())

    def test_candidate_parameter_and_project_tier_evidence_fail_closed(self):
        from hashlib import sha256
        for evidence_key,field,bad in (('parameter_support','model_id','SYN-other-model'),
                                     ('parameter_support','parameter_support',{'seed':'unsupported'}),
                                     ('account_tier','tier','Paid'),('account_tier','project_reference',None)):
            with self.subTest(evidence=evidence_key,field=field),tempfile.TemporaryDirectory() as directory:
                cfg,pol=self.fixture(Path(directory));p=json.loads(pol.read_text())
                source=Path(p['evidence'][evidence_key+'_file']);value=json.loads(source.read_text())
                value[field]=bad;source.write_text(json.dumps(value))
                p['evidence'][evidence_key+'_sha256']=sha256(source.read_bytes()).hexdigest();pol.write_text(json.dumps(p))
                transport=self.transport()
                with self.assertRaises(ValidationError):self.execute('connectivity','SYN-blocked',cfg,pol,transport)
                transport.assert_not_called()

    def test_invalid_semantic_response_is_final_without_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);cfg,pol=self.fixture(root);transport=self.transport('SYN-invalid-JSON')
            plan,summary=self.execute('connectivity','SYN-invalid',cfg,pol,transport)
            transport.assert_called_once()
            self.assertTrue(summary['complete'])
            self.assertEqual(summary['completed'],1)
            records=list((plan.root/'raw').rglob('*.response.json'))
            self.assertEqual(len(records),1)
            response=json.loads(records[0].read_text())
            self.assertEqual(response['raw_output'],'SYN-invalid-JSON')
            self.assertEqual(response['requested_parameters'],response['effective_parameters'])

    def test_candidate_readonly_target_safe_output(self):
        spec=importlib.util.spec_from_file_location('diag',ROOT/'.github/scripts/gemini_models_diagnostic.py');diag=importlib.util.module_from_spec(spec);spec.loader.exec_module(diag)
        body={'models':[{'name':'models/'+MODEL,'supportedGenerationMethods':['generateContent']}]}
        reply=Mock(status=200);reply.read.return_value=json.dumps(body).encode();reply.__enter__=Mock(return_value=reply);reply.__exit__=Mock(return_value=False)
        opener=Mock(return_value=reply);report=diag.diagnose(DUMMY,opener,target='models/'+MODEL)
        self.assertTrue(report['target_supports_generateContent']);opener.assert_called_once()
        self.assertEqual(opener.call_args.args[0].get_method(),'GET')
        with tempfile.TemporaryDirectory() as directory,patch.object(diag,'diagnose',return_value=report),patch.dict(os.environ,{'GOOGLE_API_KEY':DUMMY}),patch('sys.stdout',io.StringIO()):
            output=Path(directory)/'availability.json'
            self.assertEqual(diag.main(['--target-model','models/'+MODEL,'--require-target','--output',str(output)]),0)
            self.assertNotIn(DUMMY,output.read_text())
            with self.assertRaises(FileExistsError):diag.main(['--target-model','models/'+MODEL,'--output',str(output)])
        self.assertEqual(diag.diagnose(DUMMY,opener,target='models/SYN-unsupported')['requests_attempted'],0)

    def test_manual_candidate_workflows_no_auto_expansion(self):
        readonly=json.loads((ROOT/'.github/workflows/flash-lite-availability.yml').read_text())
        self.assertEqual(readonly['on'],{'workflow_dispatch':{}})
        scripts='\n'.join(s.get('run','') for s in readonly['jobs']['diagnostic']['steps'])
        self.assertIn('--target-model models/'+MODEL,scripts);self.assertNotIn('execute-live',scripts)
        campaign=json.loads((ROOT/'.github/workflows/free-tier-pilot.yml').read_text())
        self.assertEqual(set(campaign['on']),{'workflow_dispatch'})
        self.assertFalse(campaign['on']['workflow_dispatch']['inputs']['budget_review_confirmed']['default'])
        job=campaign['jobs']['readiness'];self.assertIn('github.run_attempt == 1',job['if'])
        for step in job['steps']:
            if 'GOOGLE_API_KEY' in step.get('env',{}):self.assertEqual(step['env']['GOOGLE_API_KEY'],'${{ secrets.GOOGLE_API_KEY }}')
