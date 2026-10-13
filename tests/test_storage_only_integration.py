"""Standalone SYN storage tests: no revocable_flow/provider imports or network."""
import ast
import base64
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / '.github/scripts/storage_only_integration.py'
spec = importlib.util.spec_from_file_location('storage_test_helper', SCRIPT)
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class StorageOnlyTests(unittest.TestCase):
    def fixture(self):
        binding = {'repository': s.REPO, 'run_id': 900, 'run_attempt': 1, 'job_id': 901,
                   'runner_id': 0, 'execution_commit': 'a' * 40,
                   'invocation_nonce': 'storage-only-v1:' + 'b' * 64}
        record = {'version': s.NAMESPACE, 'workflow_path': s.WORKFLOW, 'binding': binding,
                  'scope_hash': s.digest(s.encode(s.scope())), 'approved_at_epoch': 1000,
                  'storage_only_approved': True}
        return binding, self.evidence(record)

    def evidence(self, record):
        data = s.encode(record)
        return {'path': s.auth_path(record['binding']['run_id']), 'record_bytes': data.decode(),
                'blob_sha': hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest(),
                'introduction_commit': 'c' * 40, 'file_history': ['c' * 40]}

    def produce(self, root):
        binding, evidence = self.fixture()
        with patch.object(s.time, 'time', return_value=1000):
            s.write(root, 'invocation.json', {'namespace': s.NAMESPACE, 'binding': binding, 'generation_authorized': False})
            return s.synthetic_execute(root, evidence, binding)

    def test_authorization_rejects_stale_future_wrong_binding_scope_and_malformed(self):
        binding, evidence = self.fixture()
        self.assertEqual(s.validate(evidence, binding, now=1000)['storage_only_approved'], True)
        for age in (301, -1):
            with self.assertRaises(ValueError): s.validate(evidence, binding, now=1000 + age)
        for field, value in [('run_id', 999), ('invocation_nonce', 'storage-only-v1:' + 'd' * 64),
                             ('execution_commit', 'd' * 40), ('job_id', 999), ('run_attempt', 2)]:
            with self.assertRaises(ValueError): s.validate(evidence, {**binding, field: value}, now=1000)
        record = s.parse(evidence['record_bytes'])
        for changed in ({**record, 'scope_hash': 'bad'}, {**record, 'storage_only_approved': False},
                        {**record, 'extra': 'bad'}, {**record, 'version': 'production'},
                        {**record, 'binding': {**binding, 'run_attempt': True}}):
            with self.assertRaises(ValueError): s.validate(self.evidence(changed), binding, now=1000)
        with self.assertRaises(ValueError): s.parse('{"a":1,"a":2}')
        with self.assertRaises(ValueError): s.parse('{"a":NaN}')

    def test_edited_reused_wrong_path_or_blob_are_rejected(self):
        binding, evidence = self.fixture()
        for changed in ({**evidence, 'file_history': ['c' * 40, 'd' * 40]},
                        {**evidence, 'path': 'checkpoints/authorizations/post_update_014_023.json'},
                        {**evidence, 'blob_sha': '0' * 40}, {**evidence, 'record_bytes': '{}'}):
            with self.assertRaises(ValueError): s.validate(changed, binding, now=1000)

    def test_read_only_wait_requires_new_commit_in_actual_invocation(self):
        ticks = [0]
        env = {'GITHUB_REPOSITORY': s.REPO, 'GITHUB_REF': 'refs/heads/main', 'GITHUB_EVENT_NAME': 'workflow_dispatch',
               'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_RUN_ID': '900', 'GITHUB_SHA': 'a' * 40}
        paths = []
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, env, clear=True), patch.object(s.time, 'time', return_value=1000), patch('sys.stdout', new_callable=io.StringIO):
            root = Path(tmp) / 'results'
            def read(path):
                paths.append(path)
                if '/attempts/1/jobs' in path:
                    return {'total_count': 1, 'jobs': [{'name': 'storage_only', 'status': 'in_progress', 'run_id': 900, 'id': 901, 'runner_id': 0}]}
                if '/actions/runs/' in path:
                    return {'id': 900, 'head_sha': 'a' * 40, 'path': s.WORKFLOW, 'run_attempt': 1,
                            'head_branch': 'main', 'event': 'workflow_dispatch'}
                if '/commits?' in path: return [{'sha': 'c' * 40}]
                self.assertFalse((root / 'synthetic').exists())
                if ticks[0] == 0: return None
                binding = s.parse((root / 'invocation.json').read_bytes())['binding']
                record = {'version': s.NAMESPACE, 'workflow_path': s.WORKFLOW, 'binding': binding,
                          'scope_hash': s.digest(s.encode(s.scope())), 'approved_at_epoch': 1000, 'storage_only_approved': True}
                evidence = self.evidence(record)
                return {'type': 'file', 'encoding': 'base64', 'content': base64.b64encode(evidence['record_bytes'].encode()).decode(), 'sha': evidence['blob_sha']}
            evidence, binding = s.wait_for_owner(root, read=read, sleep=lambda sec: ticks.__setitem__(0, ticks[0] + sec), clock=lambda: ticks[0])
            self.assertEqual(ticks[0], 15)
            self.assertTrue(binding['invocation_nonce'].startswith('storage-only-v1:'))
            result = s.synthetic_execute(root, evidence, binding)
            self.assertEqual(result['provider_requests'], 0)
            with self.assertRaises(FileExistsError): s.wait_for_owner(root, read=read)
            self.assertTrue(all(path.startswith(s.PREFIX) for path in paths))

    def test_timeout_creates_no_synthetic_records(self):
        env = {'GITHUB_REPOSITORY': s.REPO, 'GITHUB_REF': 'refs/heads/main', 'GITHUB_EVENT_NAME': 'workflow_dispatch',
               'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_RUN_ID': '900', 'GITHUB_SHA': 'a' * 40}
        ticks = [0]
        def read(path):
            if '/attempts/' in path: return {'total_count': 1, 'jobs': [{'name': 'storage_only', 'status': 'in_progress', 'run_id': 900, 'id': 901, 'runner_id': 0}]}
            if '/actions/' in path: return {'id': 900, 'head_sha': 'a' * 40, 'path': s.WORKFLOW, 'run_attempt': 1, 'head_branch': 'main', 'event': 'workflow_dispatch'}
            return None
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, env, clear=True), patch('sys.stdout', new_callable=io.StringIO):
            root = Path(tmp) / 'results'
            with self.assertRaises(ValueError): s.wait_for_owner(root, read=read, sleep=lambda sec: ticks.__setitem__(0, ticks[0] + sec), clock=lambda: ticks[0])
            self.assertFalse((root / 'synthetic').exists())

    def test_provider_credentials_and_unlisted_network_destinations_fail_before_network(self):
        with patch.dict(os.environ, {'GOOGLE_API_KEY': 'SYN-credential'}, clear=True):
            read = Mock()
            with self.assertRaises(ValueError): s.wait_for_owner(Path('/unused'), read=read)
            read.assert_not_called()
        with patch('urllib.request.build_opener') as opener:
            for path in ('https://generativelanguage.googleapis.com', s.PREFIX + '/git/refs', s.PREFIX + '/contents/README.md?ref=main'):
                with self.assertRaises(ValueError): s.get(path)
            opener.assert_not_called()

    def test_artifact_readback_and_immutable_duplicate_writes(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            root = Path(tmp) / 'original'; result = self.produce(root)
            readback = Path(tmp) / 'readback'; shutil.copytree(root, readback)
            self.assertEqual(s.verify(readback, result['manifest_sha256']), result)
            with self.assertRaises(FileExistsError): self.produce(root)
            (readback / 'test-audit.json').write_text('{}')
            with self.assertRaises(ValueError): s.verify(readback, result['manifest_sha256'])
            with self.assertRaises(ValueError): s.verify(root, '0' * 64)

    def test_dual_archive_readback_alias_and_tamper_rejection(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            root = Path(tmp) / 'results'; result = self.produce(root)
            first = Path(tmp) / 'first.zip'; second = Path(tmp) / 'second.zip'
            with zipfile.ZipFile(first, 'w') as archive:
                for p in root.rglob('*'):
                    if p.is_file(): archive.write(p, p.relative_to(root))
            shutil.copyfile(first, second)
            receipt = s.archive_copies(root, first, second, result['manifest_sha256'])
            self.assertTrue(receipt['two_copies_readback_verified'])
            self.assertEqual(receipt['physical_storage_independence'], 'requires owner verification')
            extraction = Path(tmp) / 'extraction'
            self.assertEqual(s.extract_test_archive(first, extraction, result['manifest_sha256']), result)
            self.assertEqual(s.hashes(extraction), s.hashes(root))
            with self.assertRaises(ValueError): s.extract_test_archive(first, extraction, result['manifest_sha256'])
            with self.assertRaises(ValueError): s.archive_copies(root, first, first, result['manifest_sha256'])
            with zipfile.ZipFile(second, 'a') as archive: archive.writestr('unexpected', 'SYN')
            with self.assertRaises(ValueError): s.archive_copies(root, first, second, result['manifest_sha256'])
            with self.assertRaises(ValueError): s.extract_test_archive(second, Path(tmp) / 'unsafe', result['manifest_sha256'])

    def test_static_workflow_and_import_boundary(self):
        workflow = json.loads((ROOT / s.WORKFLOW).read_text())
        self.assertEqual(set(workflow['on']), {'workflow_dispatch'})
        self.assertEqual(workflow['permissions'], {'contents': 'read', 'actions': 'read'})
        text = json.dumps(workflow)
        for forbidden in ('GOOGLE_API_KEY', 'GEMINI_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'secrets.', 'generateContent', '--execute-live', 'workflow_dispatches'):
            self.assertNotIn(forbidden, text)
        imports = []
        for node in ast.walk(ast.parse(SCRIPT.read_text())):
            if isinstance(node, ast.Import): imports.extend(n.name.split('.')[0] for n in node.names)
            if isinstance(node, ast.ImportFrom): imports.append(node.module.split('.')[0])
        self.assertTrue(set(imports) <= sys.stdlib_module_names)
        self.assertNotIn('revocable_flow', imports)
        self.assertEqual(s.scope()['provider_requests'], 0)
        self.assertTrue(all(i.startswith('SYN-STORAGE-ONLY-') for i in s.IDENTITIES))
        production = json.loads((ROOT / 'configs/flash_lite_artifact_batch_014_023_v1.json').read_text())
        self.assertFalse(production['live_execution_enabled'])
        self.assertFalse(Path(production['authorization_path']).exists())


if __name__ == '__main__':
    unittest.main()
