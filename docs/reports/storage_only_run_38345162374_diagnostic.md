# Storage-only run 38345162374: authorization diagnostic

## Findings

Two independently confirmed defects make the stored authorization unacceptable:
its scope hash differs from the published helper's scope hash, and its approval
timestamp is a JSON string rather than a JSON number. The scope mismatch is the
first validation failure; correcting only that in an offline in-memory copy
reveals the timestamp-type failure. The existing file was not edited or deleted.

This establishes a concrete rejection cause if the waiting job received this
file. The exact terminal failure cannot be independently confirmed because the
Actions job/log API remains Forbidden in Codex Cloud. That Cloud access denial
does not establish a GitHub Actions runner API failure.

## Evidence retrieved through read-only Git

`git fetch origin main` retrieved the web-created authorization at
`checkpoints/storage_tests/authorizations/run-38345162374.json` without merging,
checking it out, or changing the local authorization namespace.

- Introduction commit: `d4b5b88973ee7f39c9d9650626fb9ef3d175c2fa`.
- Committer timestamp: **2026-10-13 04:18:54 UTC / 00:18:54 EDT**.
- File SHA-256: `3f93421f730347fe11bb284f57f879dfef802895938a1965132f00bb0ef8ff5d`.
- File history contains one introduction commit, not an edit/reuse history.
- Execution commit recorded in the JSON: `028a07a1b0f3fbb58756181efd38e42673b1ee96`,
  the published storage-only implementation; that Git object is available locally.
- The web commit records GitHub as committer; this is not a validation gate in
  the existing storage handshake and must not be confused with the rejection cause.

## Timing comparison

The waiting-start and failure times below are supplied by the owner; the commit
time is independently available in the fetched Git object. All are October 13,
2026. UTC values preserve the original run evidence; EDT is the owner's timezone.

| Event | UTC | EDT | Relative to waiting start |
| --- | --- | --- | --- |
| Reported waiting start | 04:10:33 | 00:10:33 | 0 seconds |
| Approval value interpreted numerically for diagnosis only | 04:17:04 | 00:17:04 | 391 seconds |
| Authorization commit timestamp | 04:18:54 | 00:18:54 | 501 seconds |
| Reported handshake failure | 04:18:57 | 00:18:57 | 504 seconds |
| Ten-minute deadline derived from reported waiting start | 04:20:33 | 00:20:33 | 600 seconds |

The commit time is inside the reported waiting window, not after it. Interpreted
as a number, the approval timestamp would be 113 seconds old at failure, inside
the required 0–300-second age interval. Its actual type is nevertheless invalid.
The observed failure at 504 seconds is earlier than the helper's normal
600-second timeout. Commit timestamps do not independently prove when the
Actions Contents API first made the file visible or when the poll fetched it.

## Field audit

| Field | Fetched value or check | Assessment |
| --- | --- | --- |
| approved_at_epoch | `"1791865024"` | Invalid string; must be unquoted JSON number |
| storage_only_approved | `true`, boolean | Correct type/value |
| scope_hash | `e16a2973cebe0c567c5acfd68690742615007c5a35b3e4290f2fa834c12df60b` | Incorrect; transposed characters near beginning |
| Expected published scope hash | `e16a2973ecbe0c567c5acfd68690742615007c5a35b3e4290f2fa834c12df60b` | Independently reconstructed from unchanged synthetic scope |
| repository | `ankitpanda226/revocable-flow` | Matches expected repository |
| run_id | `38345162374`, integer | Matches the requested run |
| run_attempt | `1`, integer | Correct allowed attempt |
| job_id | `115124755428`, integer | Valid format; actual service binding unverified |
| runner_id | `100000015`, integer | Valid format; actual service binding unverified |
| execution_commit | `028a07a1b0f3fbb58756181efd38e42673b1ee96` | Valid known commit; actual run head unverified |
| invocation_nonce | `storage-only-v1:` plus 64 hexadecimal characters | Correct format; cannot verify exact printed nonce without log |
| version | `SYN-STORAGE-ONLY-v1` | Matches test-only namespace |
| workflow_path | `.github/workflows/storage-only-integration.yml` | Matches storage workflow |

Top-level keys and JSON parsing are otherwise valid. The malformed timestamp is
not a JSON syntax error; it is an authorization schema/type violation.

## Offline reproduction

The original published validator rejects the fetched record with its combined
`wrong or missing storage-only authorization` error at the scope check. The
prepared diagnostic version identifies the same gate as
`authorization scope hash mismatch`.

In temporary Python objects only:

1. Fetched record unchanged: scope hash mismatch.
2. Correct only scope: `approved_at_epoch must be an unquoted JSON number`.
3. Correct both defects: self-consistent validation passes at the reported
   failure time, using the binding from the record itself. This does **not**
   authenticate that binding against the unavailable live service/log template.

All original fetched bytes and their SHA-256 remained unchanged. No file or
commit was created from these diagnostic copies, and no expired approval is valid
for a new run.

## Polling/error-handling review and prepared logging changes

The helper polls about every fifteen seconds for up to ten minutes. A 404 means
the approval file is not yet available. Non-404 HTTP errors, network failures,
bad content/history, or validation failures stop immediately without retries.
Previously HTTP status and the specific validation reason were replaced by
generic errors; the CLI then discarded even those messages and printed only
`Storage-only test stopped`. Consequently failure logs did not identify the gate.

Prepared, uncommitted test-only diagnostics now report:

- Waiting, periodic file-not-found, file-found and timeout events with elapsed
  seconds and poll counts.
- Authorization-check stage, timestamp type and numeric age where applicable.
- Separate scope, binding, namespace, approval flag and timestamp rejection reasons.
- Explicit expired-approval and missing-approval-at-deadline messages, separate
  from future-dated timestamps.
- GitHub HTTP status and exception class, without headers, response bodies,
  arbitrary exception messages or credential values.
- Synthetic-storage versus artifact-readback stages on subsequent failures.

The changes retain strict validation, freshness and the ten-minute deadline.
They do not coerce strings, ignore scope mismatches, retry calls or alter any
production/research protocol. Log records pass the existing test helper's secret
filter. All network behavior in new tests is mocked.
Full invocation nonces are suppressed from the added diagnostic entries. The
existing owner template display is a separate, deliberate handshake output and
remains necessary to copy the exact run binding; it was not added by diagnostics.

## Smallest safe correction and unresolved evidence

Do not repair/delete the existing authorization or rerun either failed workflow.
For a future separately approved fresh storage test, copy the new template in
full, preserve its scope/binding verbatim, replace the timestamp placeholder
including its quotation marks with an actual numeric Unix timestamp, and change
only the approval flag. Check JSON field types and compare the scope/binding to
the printed template before committing. The diagnostic logging improvement is
prepared for review before considering another test.

Missing evidence for a definitive Actions terminal-error attribution: the exact
handshake template, run/job metadata, final error lines, Contents/commit-history
poll results and the time the job first observed the approval. Owner-downloaded
logs can provide these without Codex API access. A waiting-window extension or
permission change is not justified by the currently available evidence.

## Validation and boundaries

**Eleven focused offline tests passed**, including the three new diagnostic
cases for the two field defects, sanitized HTTP/network errors and safe CLI
failure reporting. Scope/type checks remain strict; credential-bearing arbitrary
exception text is not emitted. Production policy and workflow remain disabled,
and all frozen scientific definitions/results are unchanged. No authorization
file was edited, no workflow was run, and no Gemini call, commit or push occurred.

Publication review subsequently passed the complete **256-test offline suite**,
benchmark validation, actual predecessor provenance/preservation checks and a
130-file credential/generated-output/whitespace scan with no findings. The
existing failed authorization is byte-identical to its fetched Git blob and
recorded SHA-256. Publication of only the diagnostic helper changes, tests and
this report was separately authorized; it does not authorize a new test or any
authorization record.
