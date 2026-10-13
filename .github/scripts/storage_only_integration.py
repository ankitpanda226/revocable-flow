"""Synthetic authorization/storage integration only; standard-library imports.

The only network capability here is allowlisted read-only GitHub metadata GET.
No research modules, model adapters, scientific scoring or provider transports.
"""
import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.request
import uuid
import zipfile

REPO = 'ankitpanda226/revocable-flow'
PREFIX = '/repos/' + REPO
WORKFLOW = '.github/workflows/storage-only-integration.yml'
NAMESPACE = 'SYN-STORAGE-ONLY-v1'
IDENTITIES = ['SYN-STORAGE-ONLY-001', 'SYN-STORAGE-ONLY-002']
PROVIDER_KEYS = ('GOOGLE_API_KEY', 'GEMINI_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY')
DIAGNOSTIC_STAGE = 'initialization'


class StorageTestFailure(ValueError):
    """Controlled, credential-free reason supplied only by this helper."""


def diagnostic(event, **details):
    allowed = {'stage', 'reason', 'exception_type', 'http_status', 'operation',
               'elapsed_seconds', 'poll_count', 'approval_age_seconds', 'timestamp_type'}
    require(set(details) <= allowed, 'unsupported diagnostic fields')
    record = {'namespace': NAMESPACE, 'event': event, **details}
    # Never print exception bodies, credentials, response bodies or authorization JSON.
    data = encode(record)
    try:
        safe(data)
        require(not re.search(rb'storage-only-v1:[0-9a-f]{64}', data),
                'full invocation nonce excluded from diagnostics')
    except ValueError:
        print('SYN storage diagnostic suppressed: unsafe content', flush=True)
        return
    print(json.dumps(record, sort_keys=True, allow_nan=False), flush=True)


def report_failure(error):
    details = {'stage': DIAGNOSTIC_STAGE, 'exception_type': type(error).__name__}
    if isinstance(error, StorageTestFailure):
        details['reason'] = str(error)
    diagnostic('storage_test_failed', **details)


def require(value, message):
    if not value:
        raise StorageTestFailure(message)


def parse(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('nonfinite JSON')
    return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def auth_path(run_id):
    require(type(run_id) is int and run_id > 0, 'invalid run ID')
    return f'checkpoints/storage_tests/authorizations/run-{run_id}.json'


def scope():
    return {'namespace': NAMESPACE, 'synthetic_identities': IDENTITIES,
            'scientific_observation': False, 'provider_requests': 0,
            'campaign_ledger_writes': 0, 'production_activation': False}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def get(path):
    # Reject arbitrary destinations and operations, including provider endpoints.
    tail = path.removeprefix(PREFIX)
    allowed = (re.fullmatch(r'/actions/runs/[1-9][0-9]*', tail) or
               re.fullmatch(r'/actions/runs/[1-9][0-9]*/attempts/1/jobs\?per_page=100', tail) or
               re.fullmatch(r'/contents/checkpoints/storage_tests/authorizations/run-[1-9][0-9]*\.json\?ref=main', tail) or
               re.fullmatch(r'/commits\?path=checkpoints/storage_tests/authorizations/run-[1-9][0-9]*\.json&sha=main&per_page=100', tail))
    require(path.startswith(PREFIX + '/') and allowed, 'GitHub read outside storage test allowlist')
    key = os.environ.get('GITHUB_TOKEN')
    require(bool(key), 'read-only GitHub credential missing')
    request = urllib.request.Request('https://api.github.com' + path, method='GET', headers={
        'Authorization': 'Bearer ' + key, 'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
            data = response.read(2_000_001)
            require(len(data) <= 2_000_000, 'oversized GitHub metadata')
            return parse(data)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        diagnostic('github_read_failed', stage=DIAGNOSTIC_STAGE, http_status=error.code,
                   operation='read-only metadata GET', exception_type='HTTPError')
        raise StorageTestFailure('GitHub metadata read failed') from None
    except Exception as error:
        diagnostic('github_read_uncertain', stage=DIAGNOSTIC_STAGE,
                   operation='read-only metadata GET', exception_type=type(error).__name__)
        raise StorageTestFailure('GitHub metadata read uncertain') from None


def safe(data):
    text = data.decode()
    values = [os.environ.get(k) for k in ('GITHUB_TOKEN', *PROVIDER_KEYS)]
    require(not any(v and v in text for v in values), 'credential material rejected')
    require(not re.search(r'AIza[\w-]{30,}|gh[pousr]_[\w]{20,}|github_pat_[\w_]{20,}|-----BEGIN .*PRIVATE KEY-----', text),
            'credential-like content rejected')


def write(root, name, value):
    data = encode(value)
    safe(data)
    path = root / name
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'symlink destination rejected')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def validate(evidence, binding, *, now=None, check_age=True):
    require(set(binding) == {'repository', 'run_id', 'run_attempt', 'job_id', 'runner_id',
                             'execution_commit', 'invocation_nonce'}, 'invalid binding fields')
    require(binding['repository'] == REPO and type(binding['run_attempt']) is int and binding['run_attempt'] == 1,
            'invalid repository/attempt')
    require(all(type(binding[k]) is int and binding[k] > 0 for k in ('run_id', 'job_id')) and
            type(binding['runner_id']) is int and binding['runner_id'] >= 0, 'invalid service IDs')
    require(re.fullmatch(r'[0-9a-f]{40}', binding['execution_commit']) and
            re.fullmatch(r'storage-only-v1:[0-9a-f]{64}', binding['invocation_nonce']), 'invalid commit/nonce')
    require(set(evidence) == {'path', 'record_bytes', 'blob_sha', 'introduction_commit', 'file_history'},
            'invalid evidence fields')
    require(evidence['path'] == auth_path(binding['run_id']) and
            evidence['file_history'] == [evidence['introduction_commit']] and
            re.fullmatch(r'[0-9a-f]{40}', evidence['introduction_commit']), 'authorization edited/reused')
    data = evidence['record_bytes'].encode()
    safe(data)
    require(hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == evidence['blob_sha'],
            'authorization blob mismatch')
    record = parse(data)
    require(set(record) == {'version', 'workflow_path', 'binding', 'scope_hash', 'approved_at_epoch', 'storage_only_approved'},
            'authorization fields missing or unexpected')
    require(record['version'] == NAMESPACE and record['workflow_path'] == WORKFLOW,
            'authorization workflow or namespace mismatch')
    require(encode(record['binding']) == encode(binding), 'authorization run or invocation binding mismatch')
    require(record['scope_hash'] == digest(encode(scope())), 'authorization scope hash mismatch')
    require(record['storage_only_approved'] is True, 'storage-only approval must be true')
    stamp = record['approved_at_epoch']
    require(type(stamp) in (int, float) and math.isfinite(stamp), 'approved_at_epoch must be an unquoted JSON number')
    if check_age:
        age = (time.time() if now is None else now) - stamp
        require(age >= 0, 'approval timestamp is future dated')
        require(age <= 300, 'authorization expired; approval older than 300 seconds')
    return record


def wait_for_owner(root, *, read=get, sleep=time.sleep, clock=time.monotonic):
    global DIAGNOSTIC_STAGE
    DIAGNOSTIC_STAGE = 'workflow_context'
    require(not any(os.environ.get(k) for k in PROVIDER_KEYS), 'provider credential must not be present')
    require(os.environ['GITHUB_REPOSITORY'] == REPO and os.environ['GITHUB_REF'] == 'refs/heads/main' and
            os.environ['GITHUB_EVENT_NAME'] == 'workflow_dispatch' and os.environ['GITHUB_RUN_ATTEMPT'] == '1',
            'unsupported workflow context')
    run_id = int(os.environ['GITHUB_RUN_ID'])
    info = read(PREFIX + f'/actions/runs/{run_id}')
    require(info and info['id'] == run_id and info['path'] == WORKFLOW and info['run_attempt'] == 1 and
            info['head_sha'] == os.environ['GITHUB_SHA'] and info['head_branch'] == 'main' and
            info['event'] == 'workflow_dispatch', 'service run mismatch')
    jobs = read(PREFIX + f'/actions/runs/{run_id}/attempts/1/jobs?per_page=100')
    require(jobs and jobs['total_count'] == 1 and len(jobs['jobs']) == 1, 'ambiguous job history')
    job = jobs['jobs'][0]
    require(job['name'] == 'storage_only' and job['status'] == 'in_progress' and job['run_id'] == run_id,
            'job binding mismatch')
    binding = {'repository': REPO, 'run_id': run_id, 'run_attempt': 1, 'job_id': job['id'],
               'runner_id': job['runner_id'], 'execution_commit': os.environ['GITHUB_SHA'],
               'invocation_nonce': 'storage-only-v1:' + uuid.uuid4().hex + uuid.uuid4().hex}
    write(root, 'invocation.json', {'namespace': NAMESPACE, 'binding': binding, 'generation_authorized': False})
    template = {'version': NAMESPACE, 'workflow_path': WORKFLOW, 'binding': binding,
                'scope_hash': digest(encode(scope())), 'approved_at_epoch': 'FILL_CURRENT_UNIX_TIME',
                'storage_only_approved': False}
    print('TEST ONLY: owner must create once at ' + auth_path(run_id), flush=True)
    print(encode(template).decode(), flush=True)
    started = clock()
    deadline = started + 600
    polls = 0
    DIAGNOSTIC_STAGE = 'authorization_poll'
    diagnostic('waiting_for_owner', stage=DIAGNOSTIC_STAGE, elapsed_seconds=0, poll_count=0)
    while clock() < deadline:
        polls += 1
        content = read(PREFIX + '/contents/' + auth_path(run_id) + '?ref=main')
        if content is not None:
            DIAGNOSTIC_STAGE = 'authorization_content'
            diagnostic('authorization_found', stage=DIAGNOSTIC_STAGE,
                       elapsed_seconds=round(clock() - started, 3), poll_count=polls)
            require(content['type'] == 'file' and content['encoding'] == 'base64', 'invalid authorization content')
            data = base64.b64decode(''.join(content['content'].split()), validate=True).decode()
            history = read(PREFIX + '/commits?path=' + auth_path(run_id) + '&sha=main&per_page=100')
            require(isinstance(history, list) and len(history) == 1, 'authorization file edited/reused')
            evidence = {'path': auth_path(run_id), 'record_bytes': data, 'blob_sha': content['sha'],
                        'introduction_commit': history[0]['sha'], 'file_history': [h['sha'] for h in history]}
            DIAGNOSTIC_STAGE = 'authorization_validation'
            record = parse(data)
            stamp = record.get('approved_at_epoch') if isinstance(record, dict) else None
            details = {'stage': DIAGNOSTIC_STAGE, 'timestamp_type': type(stamp).__name__}
            if type(stamp) in (int, float) and math.isfinite(stamp):
                age = time.time() - stamp
                if math.isfinite(age):
                    details['approval_age_seconds'] = round(age, 3)
            diagnostic('checking_authorization', **details)
            validate(evidence, binding)
            diagnostic('authorization_accepted', stage=DIAGNOSTIC_STAGE,
                       elapsed_seconds=round(clock() - started, 3), poll_count=polls)
            return evidence, binding
        if polls == 1 or polls % 4 == 0:
            diagnostic('authorization_not_found', stage=DIAGNOSTIC_STAGE,
                       elapsed_seconds=round(clock() - started, 3), poll_count=polls)
        sleep(15)
    diagnostic('authorization_wait_expired', stage=DIAGNOSTIC_STAGE,
               elapsed_seconds=round(clock() - started, 3), poll_count=polls)
    raise StorageTestFailure('authorization missing at waiting deadline; no synthetic execution')


def synthetic_execute(root, evidence, binding):
    validate(evidence, binding)
    write(root, 'authorization.json', evidence)
    write(root, 'test-scope.json', scope())
    for identity in IDENTITIES:
        write(root, 'synthetic/' + identity + '.json', {
            'namespace': NAMESPACE, 'test_identity': identity,
            'scientific_observation': False, 'content': 'SYN: deterministic storage fixture; no model response',
            'provider_requests': 0})
    write(root, 'test-audit.json', {'namespace': NAMESPACE, 'synthetic_records': 2,
                                  'provider_requests': 0, 'campaign_ledger_writes': 0, 'production_activation': False})
    files = hashes(root)
    write(root, 'test-manifest.json', {'namespace': NAMESPACE, 'scope': scope(), 'binding': binding,
                                     'file_hashes': files, 'tree_hash': digest(encode(files))})
    return verify(root, digest((root / 'test-manifest.json').read_bytes()))


def hashes(root):
    require(root.is_dir() and not root.is_symlink(), 'missing/symlink artifact')
    result = {}
    for p in root.rglob('*'):
        require(not p.is_symlink(), 'artifact symlink')
        if p.is_file():
            data = p.read_bytes()
            require(len(data) <= 100_000, 'oversized test record')
            safe(data)
            result[p.relative_to(root).as_posix()] = digest(data)
    return result


def verify(root, expected_manifest_hash):
    files = hashes(root)
    data = (root / 'test-manifest.json').read_bytes()
    require(digest(data) == expected_manifest_hash, 'manifest hash mismatch')
    manifest = parse(data)
    files.pop('test-manifest.json')
    require(set(files) == {'invocation.json', 'authorization.json', 'test-scope.json', 'test-audit.json',
                          *('synthetic/' + i + '.json' for i in IDENTITIES)}, 'unexpected/missing test record')
    require(manifest['namespace'] == NAMESPACE and manifest['scope'] == scope() and
            manifest['file_hashes'] == files and manifest['tree_hash'] == digest(encode(files)), 'test tree mismatch')
    binding = manifest['binding']
    validate(parse((root / 'authorization.json').read_bytes()), binding, check_age=False)
    require(parse((root / 'invocation.json').read_bytes()) ==
            {'namespace': NAMESPACE, 'binding': binding, 'generation_authorized': False}, 'invocation changed')
    require(parse((root / 'test-scope.json').read_bytes()) == scope(), 'test scope changed')
    require(parse((root / 'test-audit.json').read_bytes()) == {'namespace': NAMESPACE, 'synthetic_records': 2,
            'provider_requests': 0, 'campaign_ledger_writes': 0, 'production_activation': False}, 'test audit changed')
    for identity in IDENTITIES:
        require(parse((root / ('synthetic/' + identity + '.json')).read_bytes()) == {
            'namespace': NAMESPACE, 'test_identity': identity, 'scientific_observation': False,
            'content': 'SYN: deterministic storage fixture; no model response', 'provider_requests': 0}, 'synthetic record changed')
    return {'namespace': NAMESPACE, 'manifest_sha256': expected_manifest_hash,
            'tree_hash': manifest['tree_hash'], 'provider_requests': 0, 'scientific_observation': False}


def archive_copies(root, first, second, expected_manifest_hash):
    receipt = verify(root, expected_manifest_hash)
    require(first.resolve() != second.resolve() and not os.path.samefile(first, second), 'archive aliases are not two copies')
    expected = hashes(root)
    copies = []
    for archive in (first, second):
        with zipfile.ZipFile(archive) as z:
            entries = z.infolist()
            require(len(entries) == len(expected) and sum(i.file_size for i in entries) <= 1_000_000,
                    'archive size/count mismatch')
            names = set()
            for item in entries:
                require(item.filename in expected and item.filename not in names and not item.flag_bits & 1,
                        'unexpected/duplicate/encrypted entry')
                names.add(item.filename)
                require(digest(z.read(item)) == expected[item.filename], 'archived file hash mismatch')
            require(names == set(expected), 'missing archived record')
        copies.append(digest(archive.read_bytes()))
    require(copies[0] == copies[1], 'ZIP copies differ')
    return {**receipt, 'zip_sha256': copies[0], 'two_copies_readback_verified': True,
            'physical_storage_independence': 'requires owner verification'}


def extract_test_archive(archive, root, expected_manifest_hash):
    """Safely read only the seven known JSON records; never execute ZIP content."""
    names = {'invocation.json', 'authorization.json', 'test-scope.json', 'test-audit.json',
             'test-manifest.json', *('synthetic/' + i + '.json' for i in IDENTITIES)}
    require(not root.exists() and not any(p.is_symlink() for p in root.parents), 'new extraction directory required')
    records = {}
    with zipfile.ZipFile(archive) as z:
        entries = z.infolist()
        require(len(entries) == len(names) and sum(i.file_size for i in entries) <= 1_000_000,
                'unexpected archive size/count')
        for item in entries:
            require(item.filename in names and item.filename not in records and not item.flag_bits & 1 and
                    (item.external_attr >> 16) & 0o170000 not in (0o120000, 0o040000),
                    'unsafe archive entry')
            data = z.read(item)
            require(len(data) <= 100_000, 'oversized archive record')
            safe(data)
            parse(data)
            records[item.filename] = data
    require(set(records) == names and digest(records['test-manifest.json']) == expected_manifest_hash,
            'missing records or wrong manifest')
    for name, data in records.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
    return verify(root, expected_manifest_hash)


def main():
    global DIAGNOSTIC_STAGE
    parser = argparse.ArgumentParser(description='SYN storage-only integration; zero model access')
    parser.add_argument('command', choices=('handshake', 'verify', 'archives', 'extract'))
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--manifest-sha256')
    parser.add_argument('--copy-a', type=Path)
    parser.add_argument('--copy-b', type=Path)
    parser.add_argument('--archive', type=Path)
    args = parser.parse_args()
    if args.command == 'handshake':
        evidence, binding = wait_for_owner(args.root)
        DIAGNOSTIC_STAGE = 'synthetic_storage'
        receipt = synthetic_execute(args.root, evidence, binding)
        with Path(os.environ['GITHUB_OUTPUT']).open('a') as stream:
            stream.write('manifest_sha256=' + receipt['manifest_sha256'] + '\n')
    elif args.command == 'verify':
        DIAGNOSTIC_STAGE = 'artifact_readback'
        receipt = verify(args.root, args.manifest_sha256)
    elif args.command == 'extract':
        DIAGNOSTIC_STAGE = 'safe_archive_extraction'
        receipt = extract_test_archive(args.archive, args.root, args.manifest_sha256)
    else:
        DIAGNOSTIC_STAGE = 'dual_archive_readback'
        receipt = archive_copies(args.root, args.copy_a, args.copy_b, args.manifest_sha256)
    print(encode(receipt).decode())


if __name__ == '__main__':
    try:
        main()
    except (ValueError, TypeError, KeyError, OSError, zipfile.BadZipFile) as error:
        report_failure(error)
        raise SystemExit('Storage-only test stopped; no model access or production authorization.') from None
