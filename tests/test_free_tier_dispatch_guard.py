"""Exercise workflow-history rejection with a mocked GitHub client, offline."""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / '.github/scripts/free_tier_dispatch_guard.js'


class DispatchGuardTests(unittest.TestCase):
    def invoke(self, phase, runs, prior='', jobs=None):
        payload = {'phase': phase, 'runs': runs, 'prior': prior, 'jobs': jobs or {}}
        script = '''
const fs = require('fs'); const p = JSON.parse(fs.readFileSync(0,'utf8'));
const guard = require(process.argv[1]); const output = {};
const actions = {listWorkflowRuns:'runs', listJobsForWorkflowRunAttempt:'jobs'};
const github = {rest:{actions}, paginate:async (method,args) => {
 if(method==='runs') return p.runs;
 return p.jobs[String(args.run_id)] || [{steps:[{name:'Run only explicitly selected bounded phase', status:'completed', conclusion:'success'}]}];
}};
guard({github,context:{repo:{owner:'SYN-owner',repo:'SYN-repo'},runId:999},
 core:{setOutput:(k,v)=>output[k]=v},phase:p.phase,priorRunId:p.prior})
 .then(()=>process.stdout.write(JSON.stringify({ok:true,output})))
 .catch(()=>process.stdout.write(JSON.stringify({ok:false})));
'''
        result = subprocess.run(['node', '-e', script, str(GUARD)], input=json.dumps(payload),
                                text=True, capture_output=True, check=True)
        return json.loads(result.stdout)

    def run_record(self, index=1, **changes):
        return {'id': index, 'status': 'completed', 'run_attempt': 1,
                'path': '.github/workflows/free-tier-pilot.yml', 'event': 'workflow_dispatch',
                'head_branch': 'main', 'conclusion': 'success', 'head_sha': '1'*40, **changes}

    def test_first_dispatch_only_once_even_when_prior_attempt_failed(self):
        self.assertTrue(self.invoke('connectivity', [])['ok'])
        for conclusion in ('success', 'failure', 'cancelled'):
            self.assertFalse(self.invoke('connectivity', [self.run_record(conclusion=conclusion)])['ok'])

    def test_later_phases_require_exact_history_count_and_predecessor(self):
        for phase, count in (('small_pilot', 1), ('remaining_post', 2), ('paired_pre', 3)):
            runs = [self.run_record(i) for i in range(1, count+1)]
            self.assertEqual(self.invoke(phase, runs, str(count)), {'ok': True, 'output': {'commit': '1'*40}})
            self.assertFalse(self.invoke(phase, runs, '111')['ok'])
            self.assertFalse(self.invoke(phase, runs+[self.run_record(count+1)], str(count))['ok'])
            self.assertFalse(self.invoke(phase, runs[:-1], str(count))['ok'])

    def test_ambiguous_reruns_and_invalid_predecessor_block(self):
        for change in ({'status':'in_progress'}, {'run_attempt':2}, {'conclusion':'failure'},
                       {'event':'push'}, {'head_sha':'bad'}, {'head_branch':'other'}):
            self.assertFalse(self.invoke('small_pilot', [self.run_record(**change)], '1')['ok'])
        for job in ({'conclusion':'cancelled','steps':[]}, {'steps':[{
                'name':'Run only explicitly selected bounded phase','status':'in_progress'}]}):
            self.assertFalse(self.invoke('connectivity',[self.run_record()],jobs={'1':[job]})['ok'])

    def test_preflight_only_failure_does_not_claim_generation_slot(self):
        jobs={'1':[{'steps':[{'name':'Run only explicitly selected bounded phase',
                              'status':'completed','conclusion':'skipped'}]}]}
        self.assertTrue(self.invoke('connectivity', [self.run_record(conclusion='failure')], jobs=jobs)['ok'])
        self.assertFalse(self.invoke('unknown', [])['ok'])

    def test_history_guard_precedes_secret_bound_dispatch(self):
        workflow=json.loads((ROOT/'.github/workflows/free-tier-pilot.yml').read_text())
        steps=workflow['jobs']['readiness']['steps']
        guard=next(s for s in steps if s.get('id')=='previous')
        execute=next(s for s in steps if s.get('id')=='run')
        self.assertNotIn('if',guard)
        self.assertNotIn('GOOGLE_API_KEY',guard.get('env',{}))
        self.assertLess(steps.index(guard),steps.index(execute))
        self.assertIn('free_tier_dispatch_guard.js',guard['with']['script'])
