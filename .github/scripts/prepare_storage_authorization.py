"""Offline test-template transformation; no network, commit or provider calls."""
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import time

# Reuse the existing standard-library-only test schema; never execute input JSON.
spec = importlib.util.spec_from_file_location('storage_only_validation',
    Path(__file__).with_name('storage_only_integration.py'))
storage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(storage)
KNOWN_COMPLETED_RUNS = frozenset((38342458965, 38345162374, 38348238334))
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def validation_evidence(record):
    """Local schema validation only; synthetic hash/history is not GitHub evidence."""
    data = storage.encode(record)
    return {'path': storage.auth_path(record['binding']['run_id']), 'record_bytes': data.decode(),
            'blob_sha': hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest(),
            'introduction_commit': '0' * 40, 'file_history': ['0' * 40]}


def transform(template_bytes, *, now=None):
    storage.safe(template_bytes)
    original = storage.parse(template_bytes)
    storage.require(isinstance(original, dict), 'template must be a JSON object')
    storage.require(original.get('approved_at_epoch') == 'FILL_CURRENT_UNIX_TIME' and
                    original.get('storage_only_approved') is False,
                    'paste the untouched template, not a previous approval')
    approved = deepcopy(original)
    stamp = time.time() if now is None else now
    storage.require(type(stamp) in (int, float), 'invalid local clock')
    approved['approved_at_epoch'] = int(stamp)
    approved['storage_only_approved'] = True
    storage.validate(validation_evidence(approved), approved['binding'], now=stamp)
    # Serialization order/whitespace may change; every other JSON value/type is exact.
    restored = deepcopy(approved)
    restored['approved_at_epoch'] = original['approved_at_epoch']
    restored['storage_only_approved'] = original['storage_only_approved']
    storage.require(storage.encode(restored) == storage.encode(original), 'template changed beyond two permitted fields')
    return approved


def require_fresh_run(run_id, owner_confirmed):
    storage.require(type(run_id) is int and run_id > 0, 'invalid new run ID')
    storage.require(run_id not in KNOWN_COMPLETED_RUNS, 'known completed test run; authorization creation forbidden')
    storage.require(owner_confirmed is True, 'owner must confirm this run is still waiting')


def create(template_bytes, run_id, owner_confirmed, *, root=REPOSITORY_ROOT, now=None):
    require_fresh_run(run_id, owner_confirmed)
    approved = transform(template_bytes, now=now)
    storage.require(approved['binding']['run_id'] == run_id, 'copied template belongs to a different run')
    path = storage.auth_path(run_id)
    storage.write(root, path, approved)  # Exclusive; no replacement of an existing file.
    return path


def check(template_bytes, run_id, owner_confirmed, *, root=REPOSITORY_ROOT, now=None):
    require_fresh_run(run_id, owner_confirmed)
    expected = transform(template_bytes, now=now)
    storage.require(expected['binding']['run_id'] == run_id, 'copied template belongs to a different run')
    path = storage.auth_path(run_id)
    data = (root / path).read_bytes()
    storage.safe(data)
    actual = storage.parse(data)
    storage.validate(validation_evidence(actual), expected['binding'], now=now)
    # Timestamp is intentionally generated at creation; recheck age, not regenerate it.
    expected['approved_at_epoch'] = actual['approved_at_epoch']
    storage.require(storage.encode(actual) == storage.encode(expected), 'final file differs from original template')
    return path


def main():
    parser = argparse.ArgumentParser(description='Offline SYN template helper; requires owner live-status confirmation')
    parser.add_argument('command', choices=('create', 'check'))
    parser.add_argument('--template', type=Path, required=True)
    parser.add_argument('--run-id', type=int, required=True)
    parser.add_argument('--confirm-run-still-waiting', action='store_true', required=True)
    args = parser.parse_args()
    storage.require(args.template.is_file() and args.template.stat().st_size <= 100_000, 'missing/oversized copied template')
    data = args.template.read_bytes()
    operation = create if args.command == 'create' else check
    path = operation(data, args.run_id, args.confirm_run_still_waiting)
    # No full binding, nonce, approval JSON or credentials printed.
    print(json.dumps({'test_only': True, 'path': path, 'template_sha256': storage.digest(data),
                      'status': 'created' if args.command == 'create' else 'validated',
                      'provider_requests': 0, 'live_status': 'owner-attested, not independently checked'}))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, TypeError, KeyError, OSError, OverflowError):
        raise SystemExit('Offline preparation rejected. Copy the complete untouched SYN template; never reuse a completed run.') from None
