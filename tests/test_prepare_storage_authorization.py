"""Offline template preservation and historical-record regression tests."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare_storage', ROOT / '.github/scripts/prepare_storage_authorization.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
s = p.storage


class PrepareStorageTests(unittest.TestCase):
    def template(self, run_id=900):
        return {'version': s.NAMESPACE, 'workflow_path': s.WORKFLOW,
                'scope_hash': s.digest(s.encode(s.scope())), 'approved_at_epoch': 'FILL_CURRENT_UNIX_TIME',
                'storage_only_approved': False, 'binding': {'repository': s.REPO, 'run_id': run_id,
                'run_attempt': 1, 'job_id': 115134512105, 'runner_id': 1000000016,
                'execution_commit': 'a' * 40, 'invocation_nonce': 'storage-only-v1:' + 'b' * 64}}

    def test_changes_only_two_values_and_preserves_large_runner_id(self):
        template = self.template(); original = deepcopy(template)
        with patch.object(s, 'get', side_effect=AssertionError('network forbidden')):
            result = p.transform(s.encode(template), now=1000.75)
        self.assertEqual(template, original)
        self.assertEqual(result['binding'], original['binding'])
        self.assertEqual(result['binding']['runner_id'], 1000000016)
        self.assertEqual(type(result['binding']['runner_id']), int)
        self.assertEqual(result['approved_at_epoch'], 1000)
        self.assertIs(result['storage_only_approved'], True)
        result['approved_at_epoch'] = original['approved_at_epoch'];result['storage_only_approved'] = False
        self.assertEqual(s.encode(result), s.encode(original))

    def test_invalid_schema_types_scope_or_recycled_approval_rejected(self):
        template = self.template()
        bad = [{**template, 'scope_hash': 'bad'}, {**template, 'version': 'production'},
               {**template, 'approved_at_epoch': '1000'}, {**template, 'storage_only_approved': True},
               {**template, 'extra': True}, {**template, 'binding': {**template['binding'], 'runner_id': '1000000016'}},
               {**template, 'binding': {**template['binding'], 'run_attempt': True}},
               {**template, 'binding': {**template['binding'], 'invocation_nonce': 'wrong'}}]
        for value in bad:
            with self.assertRaises((ValueError, KeyError, TypeError)): p.transform(s.encode(value), now=1000)
        with self.assertRaises(ValueError): p.transform(b'{"binding":{},"binding":{}}', now=1000)

    def test_confirmation_closed_run_wrong_run_and_create_only_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); data = s.encode(self.template())
            with self.assertRaises(ValueError): p.create(data, 900, False, root=root, now=1000)
            for run_id in p.KNOWN_COMPLETED_RUNS:
                with self.assertRaises(ValueError): p.create(s.encode(self.template(run_id)), run_id, True, root=root, now=1000)
            self.assertFalse(list(root.rglob('*.json')))
            with self.assertRaises(ValueError): p.create(data, 999, True, root=root, now=1000)
            path = p.create(data, 900, True, root=root, now=1000)
            before = (root / path).read_bytes()
            with self.assertRaises(FileExistsError): p.create(data, 900, True, root=root, now=1000)
            self.assertEqual((root / path).read_bytes(), before)

    def test_final_check_detects_transcription_and_expiry_without_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); data = s.encode(self.template())
            path = p.create(data, 900, True, root=root, now=1000)
            self.assertEqual(p.check(data, 900, True, root=root, now=1100), path)
            with self.assertRaises(ValueError): p.check(data, 900, True, root=root, now=1301)
            record = s.parse((root / path).read_bytes());record['binding']['runner_id'] = 100000016
            (root / path).write_bytes(s.encode(record))  # Synthetic temporary fixture only.
            with self.assertRaises(ValueError): p.check(data, 900, True, root=root, now=1100)
            self.assertEqual(s.parse((root / path).read_bytes())['binding']['runner_id'], 100000016)

    def test_actual_failed_records_are_preserved_and_rejected_as_templates(self):
        # Actual stored approvals, not independently retrieved original log templates.
        for run_id in (38345162374, 38348238334):
            path = ROOT / s.auth_path(run_id); before = path.read_bytes()
            with self.assertRaises(ValueError): p.transform(before, now=1000)
            self.assertEqual(path.read_bytes(), before)
        record = s.parse((ROOT / s.auth_path(38348238334)).read_bytes())
        self.assertEqual(record['binding']['runner_id'], 100000016)
        # Correct expected runner ID is owner-provided log evidence, not a retrieved template.
        expected_binding = {**record['binding'], 'runner_id': 1000000016}
        with self.assertRaisesRegex(ValueError, 'binding mismatch'):
            s.validate(p.validation_evidence(record), expected_binding, check_age=False)
        # Pure synthetic draft built from those public binding values for preservation regression.
        draft = {**record, 'binding': expected_binding, 'approved_at_epoch': 'FILL_CURRENT_UNIX_TIME', 'storage_only_approved': False}
        result = p.transform(s.encode(draft), now=1000)
        self.assertEqual(result['binding'], expected_binding)
        self.assertEqual(result['binding']['runner_id'], 1000000016)
        self.assertFalse((ROOT / s.auth_path(38342458965)).exists())


if __name__ == '__main__':
    unittest.main()
