"""Synthetic three-case failure archives and mock-only recovery dispatches."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from revocable_flow.artifact_safety import stage_archive
from revocable_flow.providers import GoogleProvider
from revocable_flow.providers.base import HTTPReply
from revocable_flow.recovery import prepare
from revocable_flow.recovery import NoRedirect, main, recovery_transport
from revocable_flow.runner import _digest, execute_plan, plan_run
from revocable_flow.schema import ValidationError

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/pilot_eval.yaml"
SOURCE_ID = "gh-gemini-12345-1"
SOURCE_COMMIT = "0" * 40
NEW_COMMIT = "1" * 40
DUMMY_KEY = "SYN-recovery-fixture-not-a-real-key"


class RecoveryTests(unittest.TestCase):
    def test_recovery_transport_uses_existing_normalization_without_redirects(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.invalid'))
        with patch('revocable_flow.recovery.urllib.request.build_opener') as opener, \
                patch('revocable_flow.recovery.http_transport', return_value=HTTPReply(503, None)) as transport:
            reply = recovery_transport('https://example.invalid', {}, {'synthetic': True})
            self.assertEqual(reply.status, 503)
            opener.assert_called_once()
            self.assertIsInstance(opener.call_args.args[0], NoRedirect)
            transport.assert_called_once_with('https://example.invalid', {}, {'synthetic': True},
                                             open_request=opener.return_value.open)

    def test_cli_live_flag_cannot_bypass_failed_source_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.fixture(root)
            path = source.root / f'raw/{SOURCE_ID}/model-02/post_update/001/attempt-01.response.json'
            record = json.loads(path.read_text())
            record['provider_error']['http_status'] = 429
            path.write_text(json.dumps(record))
            argv = ['recovery', '--source', str(source.root), '--source-run-id', SOURCE_ID,
                    '--source-commit', SOURCE_COMMIT, '--run-id', 'gh-gemini-recovery-67890-1',
                    '--destination', str(root/'preserved'), '--execute-live']
            with patch('sys.argv', argv), patch('revocable_flow.recovery.execute_plan') as execute, \
                    patch('urllib.request.urlopen', side_effect=AssertionError('no HTTP')) as network:
                with self.assertRaises(SystemExit):
                    main()
                execute.assert_not_called()
                network.assert_not_called()

    def test_safe_recovery_upload_rejects_third_request_and_extra_attempt(self):
        for kind in ('third', 'retry'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = self.fixture(root)
                recovery = self.prepare(source, root)
                transport = Mock(return_value=HTTPReply(503, None))
                with patch.dict(os.environ, {'GOOGLE_API_KEY': DUMMY_KEY}), \
                        patch('revocable_flow.runner._git', return_value={'commit': NEW_COMMIT, 'dirty': False}):
                    execute_plan(recovery, execute_live=True, adapters={'google': GoogleProvider(transport=transport)})
                index, attempt = ('003', '01') if kind == 'third' else ('001', '02')
                path = recovery.root / f'raw/{recovery.manifest["run_id"]}/model-02/post_update/{index}/attempt-{attempt}.started.json'
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('{}')
                with self.assertRaises(ValidationError):
                    stage_archive(recovery.root, recovery.manifest['run_id'], root/'upload', recovery=True)
                self.assertFalse((root/'upload').exists())

    def fixture(self, root):
        with patch('revocable_flow.runner._git', return_value={'commit': SOURCE_COMMIT, 'dirty': False}):
            plan = plan_run(CONFIG, run_id=SOURCE_ID, provider='google', model='gemini-3.8-flash',
                            condition='post_update', scenario_limit=3, max_provider_requests=3, max_attempts_per_request=1)
            plan.root = root / 'source'
            success = HTTPReply(200, {'modelVersion': 'SYN-Gemini-reported-model',
                'candidates': [{'content': {'parts': [{'text': ' {"action":"BLOCK","release_fields":[]}\n'}]}, 'finishReason': 'STOP'}],
                'usageMetadata': {'promptTokenCount': 11, 'candidatesTokenCount': 7}})
            transport = Mock(side_effect=[HTTPReply(503, None), HTTPReply(503, None), success])
            with patch.dict(os.environ, {'GOOGLE_API_KEY': DUMMY_KEY}):
                summary = execute_plan(plan, execute_live=True, adapters={'google': GoogleProvider(transport=transport)})
            self.assertEqual(summary['completed'], 1)
            self.assertEqual(transport.call_count, 3)
        return plan

    def prepare(self, plan, root):
        def planner(*args, **kwargs):
            planned = plan_run(*args, **kwargs)
            planned.root = root / 'recovery'
            return planned
        with patch('revocable_flow.runner._git', return_value={'commit': NEW_COMMIT, 'dirty': False}), \
                patch('revocable_flow.recovery.plan_run', side_effect=planner):
            return prepare(plan.root, SOURCE_ID, SOURCE_COMMIT, 'gh-gemini-recovery-67890-1', config=CONFIG)

    def test_only_two_requests_success_preserved_and_safe_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.fixture(root)
            before = {str(p.relative_to(source.root)): p.read_bytes() for p in source.root.rglob('*') if p.is_file()}
            recovery = self.prepare(source, root)
            self.assertEqual([r['execution_index'] for r in recovery.manifest['requests']], [1, 2])
            self.assertEqual(recovery.manifest['execution_limits'], {'max_provider_requests': 2, 'max_attempts_per_request': 1})
            self.assertNotEqual(recovery.manifest['manifest_hash'], source.manifest['manifest_hash'])
            self.assertEqual(recovery.manifest['recovery']['source_manifest_hash'], source.manifest['manifest_hash'])
            for old, new in zip(source.manifest['requests'], recovery.manifest['requests']):
                self.assertEqual(old, new)
            self.assertEqual(source.manifest['prompt_catalog'][:2], recovery.manifest['prompt_catalog'])
            transport = Mock(return_value=HTTPReply(503, None))
            with patch.dict(os.environ, {'GOOGLE_API_KEY': DUMMY_KEY}), \
                 patch('revocable_flow.runner._git', return_value={'commit': NEW_COMMIT, 'dirty': False}):
                summary = execute_plan(recovery, execute_live=True, adapters={'google': GoogleProvider(transport=transport)})
                self.assertEqual(transport.call_count, 2)
                self.assertEqual(summary['attempted_provider_requests'], 2)
                self.assertEqual(summary['completed'], 0)
                # Explicit attempts remain exhausted even if someone calls resume on the same plan.
                execute_plan(recovery, execute_live=True, resume=True, adapters={'google': GoogleProvider(transport=transport)})
                self.assertEqual(transport.call_count, 2)
                stage_archive(source.root, SOURCE_ID, root/'archive/source')
                stage_archive(recovery.root, recovery.manifest['run_id'], root/'archive/recovery', recovery=True)
            after = {str(p.relative_to(source.root)): p.read_bytes() for p in source.root.rglob('*') if p.is_file()}
            self.assertEqual(before, after)
            self.assertFalse(list(recovery.root.rglob('003')))
            with self.assertRaises(ValidationError):
                self.prepare(source, root)

    def test_non503_missing_and_ambiguous_source_records_fail_before_dispatch(self):
        for kind in ('429', 'timeout', 'missing_response', 'missing_started', 'third_failure', 'parsed_failure', 'deferred'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                plan = self.fixture(root)
                prefix = plan.root / f'raw/{SOURCE_ID}/model-02/post_update/001/attempt-01'
                path = Path(str(prefix)+'.response.json')
                record = json.loads(path.read_text())
                if kind == 'missing_response':
                    path.unlink()
                elif kind == 'missing_started':
                    Path(str(prefix)+'.started.json').unlink()
                elif kind == 'third_failure':
                    third = plan.root / f'raw/{SOURCE_ID}/model-02/post_update/003/attempt-01.response.json'
                    third.write_text(json.dumps(record))
                elif kind == 'parsed_failure':
                    p = plan.root / f'parsed/{SOURCE_ID}/model-02/post_update/001.json'
                    p.write_text('{}')
                else:
                    if kind == '429':
                        record['provider_error']['http_status'] = 429
                    elif kind == 'timeout':
                        record['provider_error'].update(category='timeout', http_status=None)
                    elif kind == 'deferred':
                        record['provider_error']['retry_after_seconds'] = 100000
                    path.write_text(json.dumps(record))
                with patch('urllib.request.urlopen', side_effect=AssertionError('no HTTP')) as network:
                    with self.assertRaises((ValidationError, OSError)):
                        self.prepare(plan, root)
                    network.assert_not_called()

    def test_manifest_inputs_provenance_and_success_score_are_checked(self):
        for kind in ('manifest_hash', 'parameters', 'source_commit', 'benchmark_copy', 'started_prompt', 'third_score', 'summary'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                plan = self.fixture(root)
                path = plan.root / f'manifests/{SOURCE_ID}.json'
                manifest = json.loads(path.read_text())
                if kind == 'manifest_hash':
                    manifest['manifest_hash'] = '2'*64
                    path.write_text(json.dumps(manifest))
                elif kind in ('parameters', 'source_commit'):
                    if kind == 'parameters':
                        manifest['requests'][0]['parameters']['temperature'] = 0.5
                    else:
                        manifest['commit'] = '2'*40
                    manifest.pop('manifest_hash')
                    manifest['manifest_hash'] = _digest(manifest)
                    path.write_text(json.dumps(manifest))
                elif kind == 'benchmark_copy':
                    (plan.root / manifest['benchmark_artifact']).write_text('SYN-changed')
                elif kind == 'started_prompt':
                    p = plan.root / f'raw/{SOURCE_ID}/model-02/post_update/001/attempt-01.started.json'
                    record = json.loads(p.read_text())
                    record['messages'][1]['content'] = 'SYN-changed'
                    p.write_text(json.dumps(record))
                elif kind == 'third_score':
                    p = plan.root / f'parsed/{SOURCE_ID}/model-02/post_update/003.json'
                    record = json.loads(p.read_text())
                    record['raw_hash'] = '2'*64
                    p.write_text(json.dumps(record))
                else:
                    p = next((plan.root / f'summaries/{SOURCE_ID}').glob('completion-*.json'))
                    record = json.loads(p.read_text())
                    record['attempted_provider_requests'] = 2
                    p.write_text(json.dumps(record))
                with self.assertRaises((ValidationError, OSError)):
                    self.prepare(plan, root)

    def test_completed_invalid_json_is_preserved_and_never_retried(self):
        # Completion means a terminal model response, not necessarily a correct or valid answer.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self.fixture(root)
            recovery = self.prepare(plan, root)
            transport = Mock(return_value=HTTPReply(200, {'candidates': [{'content': {'parts': [{'text': 'SYN-not-JSON'}]}}]}))
            with patch.dict(os.environ, {'GOOGLE_API_KEY': DUMMY_KEY}), patch('revocable_flow.runner._git', return_value={'commit': NEW_COMMIT, 'dirty': False}):
                summary = execute_plan(recovery, execute_live=True, adapters={'google': GoogleProvider(transport=transport)})
            self.assertEqual(transport.call_count, 2)
            self.assertTrue(summary['complete'])
            for p in recovery.root.rglob('*.response.json'):
                self.assertEqual(json.loads(p.read_text())['parse_status'], 'invalid')
            self.assertNotIn('metrics_by_model', summary)

    def test_workflow_manual_two_call_gate_and_existing_artifact_download(self):
        workflow = json.loads((ROOT/'.github/workflows/gemini-recovery.yml').read_text())
        self.assertEqual(set(workflow['on']), {'workflow_dispatch'})
        self.assertFalse(workflow['on']['workflow_dispatch']['inputs']['budget_review_confirmed']['default'])
        self.assertEqual(workflow['permissions'], {'contents': 'read', 'actions': 'read'})
        job = workflow['jobs']['recovery']
        self.assertIn('github.run_attempt == 1', job['if'])
        self.assertIn('inputs.budget_review_confirmed', job['if'])
        steps = job['steps']
        download = next(s for s in steps if s.get('uses','').startswith('actions/download-artifact'))
        self.assertEqual(download['with']['name'], 'gemini-sanity-results')
        self.assertEqual(download['with']['repository'], '${{ github.repository }}')
        self.assertEqual(download['with']['run-id'], '${{ inputs.source_run_id }}')
        recover = next(s for s in steps if s.get('id') == 'recover')
        self.assertEqual(recover['env']['GOOGLE_API_KEY'], '${{ secrets.GOOGLE_API_KEY }}')
        self.assertIn('revocable_flow.recovery', recover['run'])
        self.assertNotIn('pilot-run', recover['run'])
        self.assertNotIn('--resume', recover['run'])
        for step in steps:
            for forbidden in ('curl', '$GOOGLE_API_KEY', 'printenv', 'openai', 'anthropic'):
                self.assertNotIn(forbidden, step.get('run',''))
        upload = next(s for s in steps if s.get('uses','').startswith('actions/upload-artifact'))
        self.assertIn("steps.artifacts.outputs.safe == 'true'", upload['if'])
        self.assertEqual(upload['with']['path'], '${{ runner.temp }}/recovery-upload/')
        self.assertTrue(any('unittest discover' in s.get('run','') for s in steps))
