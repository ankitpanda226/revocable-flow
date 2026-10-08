"""Inspect an untrusted downloaded diagnostic; preserve bytes, never execute it."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

from revocable_flow.artifact_safety import TOKEN_PATTERN, _inspect_json, _secret_material
from revocable_flow.schema import ValidationError, parse_json

RUN_ID = 37854150199
MODEL = 'models/gemini-3.5-flash-lite'
COMMIT = '712193f0f48d4154e9fd087ae35a6f869f4e6438'
URL = f'https://github.com/ankitpanda226/revocable-flow/actions/runs/{RUN_ID}'


def preserve(source, metadata, destination):
    source, metadata, destination = map(lambda p: Path(p).absolute(), (source, metadata, destination))
    for path in (source, metadata, destination):
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValidationError('symlinks forbidden')
    if destination.exists():
        raise ValidationError('destination must be new')
    files = list(source.rglob('*'))
    if len(files) != 1 or files[0].is_symlink() or files[0].name != 'flash-lite-availability.json' or not files[0].is_file():
        raise ValidationError('unexpected downloaded artifact contents')
    raw = files[0].read_bytes()
    meta_bytes = metadata.read_bytes()
    if len(raw) > 2_000_000 or len(meta_bytes) > 10_000:
        raise ValidationError('oversized diagnostic/provenance')
    for data in (raw, meta_bytes):
        text = data.decode('utf-8')
        if TOKEN_PATTERN.search(text) or any(secret in text for secret in _secret_material()):
            raise ValidationError('credential-like material forbidden')
    report, provenance = parse_json(raw.decode()), parse_json(meta_bytes.decode())
    _inspect_json(report); _inspect_json(provenance)
    keys = {'status', 'http_status', 'requests_attempted', 'requested_model', 'models',
            'list_complete', 'target_listed', 'target_supports_generateContent'}
    if (not isinstance(report, dict) or set(report) != keys or report['status'] != 'success'
            or type(report['http_status']) is not int or report['http_status'] != 200
            or type(report['requests_attempted']) is not int or report['requests_attempted'] != 1
            or report['requested_model'] != MODEL or report['target_listed'] is not True
            or report['target_supports_generateContent'] is not True
            or type(report['list_complete']) is not bool or not isinstance(report['models'], list)):
        raise ValidationError('diagnostic does not verify candidate')
    matches = []
    for model in report['models']:
        if (not isinstance(model, dict) or set(model) != {'name', 'supported_methods'}
                or not isinstance(model['name'], str) or not re.fullmatch(r'models/[A-Za-z0-9._-]+', model['name'])
                or not isinstance(model['supported_methods'], list)
                or any(not isinstance(m, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9]*', m) for m in model['supported_methods'])):
            raise ValidationError('invalid model metadata')
        if model['name'] == MODEL: matches.append(model)
    if len(matches) != 1 or 'generateContent' not in matches[0]['supported_methods']:
        raise ValidationError('candidate method evidence missing')
    expected = {'source_run_id': RUN_ID, 'source_run_url': URL, 'source_head_sha': COMMIT,
                'source_run_attempt': 1, 'source_workflow': '.github/workflows/flash-lite-availability.yml',
                'source_event': 'workflow_dispatch', 'source_branch': 'main', 'source_conclusion': 'success'}
    if (not isinstance(provenance, dict) or set(provenance) != set(expected) | {'source_created_at'}
            or any(provenance.get(k) != v for k, v in expected.items())
            or not isinstance(provenance['source_created_at'], str)
            or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', provenance['source_created_at'])):
        raise ValidationError('source run provenance mismatch')
    destination.mkdir(parents=True, exist_ok=False)
    with (destination / 'flash-lite-availability.json').open('xb') as stream: stream.write(raw)
    with (destination / 'source-run.json').open('xb') as stream: stream.write(meta_bytes)
    manifest = {**provenance, 'diagnostic_sha256': sha256(raw).hexdigest(),
                'source_metadata_sha256': sha256(meta_bytes).hexdigest(), 'generation_requests_made': 0}
    with (destination / 'preservation-manifest.json').open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('source', 'metadata', 'destination'): parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    try:
        preserve(args.source, args.metadata, args.destination)
    except (ValueError, OSError, KeyError, TypeError, UnicodeError):
        raise SystemExit('Diagnostic preservation failed; upload not authorized.') from None
    print('safe=true')
